# tests/test_3_api.py

import pytest


@pytest.mark.django_db
class TestHealthEndpoint:

    def test_health_returns_200(self, api_client):
        r = api_client.get("/api/health/")
        assert r.status_code == 200

    def test_health_schema(self, api_client):
        data = api_client.get("/api/health/").json()
        assert data["status"] == "operational"
        assert "model" in data
        assert data["postgresql"]["status"] == "ok"
        assert data["chromadb"]["status"] == "ok"
        assert data["postgresql"]["companies"] == 4
        assert data["postgresql"]["financials"] == 24
        assert data["chromadb"]["documents"] >= 4

    def test_health_postgresql_counts_accurate(self, api_client):
        data = api_client.get("/api/health/").json()
        assert data["postgresql"]["companies"] == 4
        assert data["postgresql"]["financials"] == 24


@pytest.mark.django_db
class TestDocumentsEndpoint:

    def test_list_documents_returns_200(self, auth_client):
        r = auth_client.get("/api/documents/")
        assert r.status_code == 200

    def test_list_documents_schema(self, auth_client):
        data = auth_client.get("/api/documents/").json()
        assert "count" in data
        assert "documents" in data
        assert data["count"] >= 4

    def test_document_record_has_required_fields(self, auth_client):
        data = auth_client.get("/api/documents/").json()
        for doc in data["documents"]:
            assert "source_name" in doc
            assert "category" in doc
            assert "chunk_count" in doc

    def test_delete_nonexistent_doc_returns_404(self, auth_client):
        r = auth_client.delete("/api/documents/nonexistent-uuid-0000/")
        assert r.status_code == 404


@pytest.mark.django_db
class TestQueryEndpoint:

    def test_empty_question_rejected(self, auth_client):
        r = auth_client.post("/api/query/", {"question": ""}, format="json")
        assert r.status_code == 400

    def test_missing_question_rejected(self, auth_client):
        r = auth_client.post("/api/query/", {}, format="json")
        assert r.status_code == 400

    def test_valid_request_returns_200(self, auth_client):
        r = auth_client.post("/api/query/",
            {"question": "How many companies are in the database?"},
            format="json")
        assert r.status_code == 200

    def test_response_schema(self, auth_client):
        r = auth_client.post("/api/query/",
            {"question": "How many companies are in the database?"},
            format="json")
        data = r.json()
        assert "answer" in data
        assert "tool_calls" in data
        assert "session_id" in data
        assert isinstance(data["answer"], str)
        assert len(data["answer"]) > 0

    def test_answer_is_not_error_string(self, auth_client):
        r = auth_client.post("/api/query/",
            {"question": "What sector is Aether Technologies in?"},
            format="json")
        answer = r.json()["answer"].lower()
        assert "agent error" not in answer
        assert "exception" not in answer


@pytest.mark.django_db
class TestChatEndpoint:

    def test_missing_session_id_uses_default(self, auth_client):
        r = auth_client.post("/api/chat/",
            {"question": "Hello"},
            format="json")
        assert r.status_code == 200

    def test_response_contains_session_id(self, auth_client):
        r = auth_client.post("/api/chat/",
            {"question": "Hello", "session_id": "test-schema"},
            format="json")
        data = r.json()
        assert "session_id" in data
        assert "history_length" in data
        assert data["history_length"] >= 2

    def test_clear_session_works(self, auth_client, test_user):
        auth_client.post("/api/chat/",
            {"question": "Hello", "session_id": "clear-test"},
            format="json")
        r = auth_client.post("/api/chat/clear/",
            {"session_id": "clear-test"},
            format="json")
        assert r.status_code == 200
        assert r.json()["status"] == "cleared"

    def test_history_endpoint_returns_messages(self, auth_client, test_user):
        scoped_id = f"{test_user.id}:history-test"
        auth_client.post("/api/chat/",
            {"question": "What is ATHR?", "session_id": "history-test"},
            format="json")
        r = auth_client.get("/api/chat/history/?session_id=history-test")
        assert r.status_code == 200
        data = r.json()
        assert data["turn_count"] >= 1
        assert len(data["messages"]) >= 2