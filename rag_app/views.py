import os
import logging
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from rag_app.agent import run_agent, clear_session, get_session_history
from rag_app.serializers import (
    QueryRequestSerializer,
    ChatRequestSerializer,
    ClearSessionRequestSerializer,
)

logger = logging.getLogger(__name__)


class HealthView(APIView):
    """GET /api/health/"""
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


class QueryView(APIView):
    """
    POST /api/query/
    Stateless single-shot query — no memory retained between calls.
    """
    def post(self, request):
        serializer = QueryRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        question = serializer.validated_data["question"]
        logger.info(f"[QueryView] question='{question[:80]}'")

        result = run_agent(question=question, session_id="__stateless__")
        clear_session("__stateless__")

        # Return the dict from run_agent directly — no outbound serializer
        return Response(result, status=status.HTTP_200_OK)


class ChatView(APIView):
    """
    POST /api/chat/
    Stateful multi-turn chat with per session_id memory.
    """
    def post(self, request):
        serializer = ChatRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        question   = serializer.validated_data["question"]
        session_id = serializer.validated_data["session_id"]
        logger.info(f"[ChatView] session='{session_id}' question='{question[:80]}'")

        result = run_agent(question=question, session_id=session_id)

        return Response(result, status=status.HTTP_200_OK)


class ClearSessionView(APIView):
    """POST /api/chat/clear/"""
    def post(self, request):
        serializer = ClearSessionRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        session_id = serializer.validated_data["session_id"]
        clear_session(session_id)

        return Response({"status": "cleared", "session_id": session_id})


class SessionHistoryView(APIView):
    """GET /api/chat/history/?session_id=..."""
    def get(self, request):
        session_id = request.query_params.get("session_id", "default")
        history    = get_session_history(session_id)

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