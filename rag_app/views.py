import os
import json
import logging
import tempfile

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.permissions import IsAuthenticated, AllowAny
from django_ratelimit.decorators import ratelimit
from django.utils.decorators import method_decorator

from rag_app.agent import run_agent, clear_session, get_session_history
from rag_app.serializers import (
    QueryRequestSerializer,
    ChatRequestSerializer,
    ClearSessionRequestSerializer,
    IngestRequestSerializer,
    DocumentSerializer,
)
from rag_app.ingestion.pdf_processor import ingest_pdf, list_documents, delete_document

logger = logging.getLogger(__name__)


class HealthView(APIView):
    """
    GET /api/health/
    Public endpoint — no auth required.
    """
    permission_classes = [AllowAny]

    def get(self, request):
        import chromadb
        from rag_app.models import Company, QuarterlyFinancials

        try:
            company_count    = Company.objects.count()
            financials_count = QuarterlyFinancials.objects.count()
            sql_status       = "ok"
        except Exception as e:
            company_count = financials_count = 0
            sql_status    = f"error: {str(e)}"

        try:
            client           = chromadb.PersistentClient(path="./chroma_store")
            collection       = client.get_collection("financial_regulatory_kb")
            vector_doc_count = collection.count()
            vector_status    = "ok"
        except Exception as e:
            vector_doc_count = 0
            vector_status    = f"error: {str(e)}"

        model_type = os.getenv("LLM_MODEL_TYPE", "gemini-2.5-flash")

        return Response({
            "status": "operational",
            "model":  model_type,
            "postgresql": {
                "status":     sql_status,
                "companies":  company_count,
                "financials": financials_count,
            },
            "chromadb": {
                "status":    vector_status,
                "documents": vector_doc_count,
            },
        })


@method_decorator(
    ratelimit(key="user", rate="30/m", method="POST", block=True),
    name="dispatch"
)
class QueryView(APIView):
    """
    POST /api/query/
    Stateless single-shot query.
    Rate limit: 30 requests/minute per user.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = QueryRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        question = serializer.validated_data["question"]
        logger.info(f"[QueryView] user={request.user} question='{question[:80]}'")

        result = run_agent(question=question, session_id="__stateless__")
        clear_session("__stateless__")
        return Response(result, status=status.HTTP_200_OK)


@method_decorator(
    ratelimit(key="user", rate="30/m", method="POST", block=True),
    name="dispatch"
)
class ChatView(APIView):
    """
    POST /api/chat/
    Stateful multi-turn chat.
    Rate limit: 30 requests/minute per user.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = ChatRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        question   = serializer.validated_data["question"]
        session_id = serializer.validated_data["session_id"]

        # Scope session to the authenticated user so sessions never bleed across users
        scoped_session_id = f"{request.user.id}:{session_id}"
        logger.info(f"[ChatView] user={request.user} session='{scoped_session_id}'")

        result = run_agent(question=question, session_id=scoped_session_id)
        return Response(result, status=status.HTTP_200_OK)


class ClearSessionView(APIView):
    """POST /api/chat/clear/"""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = ClearSessionRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        session_id        = serializer.validated_data["session_id"]
        scoped_session_id = f"{request.user.id}:{session_id}"
        clear_session(scoped_session_id)
        return Response({"status": "cleared", "session_id": session_id})


class SessionHistoryView(APIView):
    """GET /api/chat/history/?session_id=..."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        session_id        = request.query_params.get("session_id", "default")
        scoped_session_id = f"{request.user.id}:{session_id}"
        history           = get_session_history(scoped_session_id)

        messages = [
            {
                "role":    "human" if msg.__class__.__name__ == "HumanMessage" else "ai",
                "content": msg.content,
            }
            for msg in history
        ]

        return Response({
            "session_id": session_id,
            "turn_count": len(messages) // 2,
            "messages":   messages,
        })


@method_decorator(
    ratelimit(key="user", rate="10/m", method="POST", block=True),
    name="dispatch"
)
class IngestView(APIView):
    """
    POST /api/ingest/
    Rate limit: 10 uploads/minute per user (PDF processing is expensive).
    """
    permission_classes = [IsAuthenticated]
    parser_classes     = [MultiPartParser, FormParser]

    def post(self, request):
        serializer = IngestRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        validated   = serializer.validated_data
        uploaded    = validated["file"]
        source_name = validated["source_name"]
        category    = validated["category"]
        doc_type    = validated["document_type"]

        try:
            extra = json.loads(validated.get("extra_metadata") or "{}")
        except json.JSONDecodeError:
            return Response(
                {"extra_metadata": "Must be valid JSON or empty."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not uploaded.name.lower().endswith(".pdf"):
            return Response(
                {"file": "Only PDF files are supported."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Tag each document with the uploading user
        extra["uploaded_by"] = str(request.user)

        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                for chunk in uploaded.chunks():
                    tmp.write(chunk)
                tmp_path = tmp.name

            result = ingest_pdf(
                file_path     = tmp_path,
                source_name   = source_name,
                category      = category,
                document_type = doc_type,
                extra_metadata= extra,
            )
        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_422_UNPROCESSABLE_ENTITY)
        except Exception as e:
            logger.exception("[IngestView] Unexpected error during ingestion")
            return Response(
                {"error": f"Ingestion failed: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        finally:
            if tmp_path and os.path.exists(tmp_path):
                os.unlink(tmp_path)

        return Response({
            "status":      "ingested",
            "doc_uuid":    result["doc_uuid"],
            "source_name": result["source_name"],
            "chunk_count": result["chunk_count"],
            "char_count":  result["char_count"],
            "message": (
                f"Successfully ingested '{source_name}' "
                f"as {result['chunk_count']} searchable chunks."
            ),
        }, status=status.HTTP_201_CREATED)


class DocumentListView(APIView):
    """
    GET    /api/documents/
    DELETE /api/documents/<doc_uuid>/
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        docs       = list_documents()
        serializer = DocumentSerializer(data=docs, many=True)
        serializer.is_valid()
        return Response({"count": len(docs), "documents": serializer.data})

    def delete(self, request, doc_uuid: str):
        if not doc_uuid:
            return Response({"error": "doc_uuid is required."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            deleted_count = delete_document(doc_uuid)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        if deleted_count == 0:
            return Response(
                {"error": f"No document found with doc_uuid '{doc_uuid}'."},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response({"status": "deleted", "doc_uuid": doc_uuid, "chunks_deleted": deleted_count})