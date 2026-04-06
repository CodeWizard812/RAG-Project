import os
import json
import logging
import tempfile
import queue
import threading
from django.http import StreamingHttpResponse
from langchain_classic.callbacks.base import BaseCallbackHandler
from django.contrib.auth.models import User
from rest_framework.permissions import AllowAny
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

        # Key pool status
        try:
            from rag_app.utils.key_pool import get_key_pool
            pool_status = get_key_pool().status()
        except Exception as e:
            pool_status = {"error": str(e)}

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
            "key_pool":   pool_status,
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
    

def _run_agent_with_streaming(
    question: str,
    session_id: str,
    event_queue: queue.Queue,
) -> None:
    """
    Runs the agent in a background thread, emitting SSE events into
    the queue as tools are called and the answer is produced.
    Called by StreamingChatView — never directly.
    """
    from rag_app.agent import _get_executor, _get_memory_history, _extract_text

    class _SSECallbackHandler(BaseCallbackHandler):
        """Intercepts LangChain agent lifecycle events and queues SSE payloads."""

        def on_tool_start(self, serialized, input_str, **kwargs):
            event_queue.put({
                "event": "tool_start",
                "tool":  serialized.get("name", "unknown"),
                "input": str(input_str)[:300],
            })

        def on_tool_end(self, output, **kwargs):
            event_queue.put({
                "event":          "tool_end",
                "output_preview": str(output)[:400],
            })

        def on_llm_error(self, error, **kwargs):
            event_queue.put({
                "event":   "error",
                "message": str(error),
            })

    try:
        memory   = _get_memory_history(session_id)
        history  = memory.messages
        executor = _get_executor()

        result = executor.invoke(
            {"input": question, "chat_history": history},
            config={"callbacks": [_SSECallbackHandler()]},
        )

        answer   = _extract_text(result.get("output", ""))
        contexts = []
        tool_calls = []

        for step in result.get("intermediate_steps", []):
            action, tool_output = step
            tool_calls.append({
                "tool":  getattr(action, "tool", "unknown"),
                "input": getattr(action, "tool_input", {}),
            })
            if isinstance(tool_output, str) and tool_output.strip():
                contexts.append(tool_output)

        if not answer.strip():
            answer = "Agent completed but returned an empty response."

        memory.add_user_message(question)
        memory.add_ai_message(answer)

        event_queue.put({
            "event":          "done",
            "answer":         answer,
            "tool_calls":     tool_calls,
            "contexts":       contexts,
            "history_length": len(memory.messages),
        })

    except Exception as e:
        logger.exception("[StreamingChat] Agent thread error")
        event_queue.put({"event": "error", "message": str(e)})
    finally:
        event_queue.put(None)   # sentinel — tells generator to stop


class StreamingChatView(APIView):
    """
    POST /api/chat/stream/

    Streams agent execution as Server-Sent Events so the frontend
    can show tool call progress in real time.

    SSE event types:
      tool_start  — agent called a tool  { tool, input }
      tool_end    — tool returned         { output_preview }
      done        — agent finished        { answer, tool_calls, contexts, history_length }
      error       — something failed      { message }
      keepalive   — heartbeat every 15s  {}
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        question   = request.data.get("question", "").strip()
        session_id = request.data.get("session_id", "default")
        model_type = request.data.get("model_type", None)

        if not question:
            return Response({"error": "question is required."}, status=400)
        if len(question) > 2000:
            return Response({"error": "question exceeds 2000 characters."}, status=400)

        # Override model for this request if frontend sends one
        if model_type:
            os.environ["LLM_MODEL_TYPE"] = model_type

        scoped_session_id = f"{request.user.id}:{session_id}"

        event_queue: queue.Queue = queue.Queue()

        thread = threading.Thread(
            target=_run_agent_with_streaming,
            args=(question, scoped_session_id, event_queue),
            daemon=True,
        )
        thread.start()

        def event_stream():
            while True:
                try:
                    event = event_queue.get(timeout=15)
                    if event is None:   # sentinel — agent finished
                        break
                    yield f"data: {json.dumps(event)}\n\n"
                except queue.Empty:
                    # Send keepalive so the connection stays open
                    yield 'data: {"event": "keepalive"}\n\n'

        response = StreamingHttpResponse(
            streaming_content=event_stream(),
            content_type="text/event-stream",
        )
        response["Cache-Control"]     = "no-cache"
        response["X-Accel-Buffering"] = "no"
        return response
    

class RegisterView(APIView):
    """
    POST /api/auth/register/
    Public endpoint — no token required.
    Creates a new active (non-superuser) user.

    Body: { "username": "...", "password": "...", "email": "..." }
    """
    permission_classes = [AllowAny]

    def post(self, request):
        username = request.data.get("username", "").strip()
        password = request.data.get("password", "")
        email    = request.data.get("email", "").strip()

        if not username or not password:
            return Response(
                {"error": "username and password are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if len(password) < 8:
            return Response(
                {"error": "password must be at least 8 characters."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if User.objects.filter(username=username).exists():
            return Response(
                {"error": "username already taken."},
                status=status.HTTP_409_CONFLICT,
            )

        user = User.objects.create_user(
            username=username,
            password=password,
            email=email,
            is_staff=False,
            is_superuser=False,
        )
        logger.info(f"[RegisterView] New user created: {username}")
        return Response(
            {"status": "registered", "username": user.username},
            status=status.HTTP_201_CREATED,
        )
