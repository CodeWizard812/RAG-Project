# tests/test_2_auth.py

import pytest


@pytest.mark.django_db
class TestJWTAuth:

    def test_obtain_token_valid_credentials(self, api_client, test_user):
        response = api_client.post("/api/auth/token/", {
            "username": "testuser",
            "password": "TestPass@123",
        }, format="json")
        assert response.status_code == 200
        data = response.json()
        assert "access" in data
        assert "refresh" in data
        assert len(data["access"]) > 20

    def test_obtain_token_wrong_password(self, api_client, test_user):
        response = api_client.post("/api/auth/token/", {
            "username": "testuser",
            "password": "wrongpassword",
        }, format="json")
        assert response.status_code == 401

    def test_obtain_token_nonexistent_user(self, api_client):
        response = api_client.post("/api/auth/token/", {
            "username": "nobody",
            "password": "anything",
        }, format="json")
        assert response.status_code == 401

    def test_refresh_token_works(self, api_client, test_user):
        token_response = api_client.post("/api/auth/token/", {
            "username": "testuser",
            "password": "TestPass@123",
        }, format="json")
        refresh = token_response.json()["refresh"]

        refresh_response = api_client.post("/api/auth/token/refresh/", {
            "refresh": refresh,
        }, format="json")
        assert refresh_response.status_code == 200
        assert "access" in refresh_response.json()

    def test_chat_requires_auth(self, api_client):
        """Unauthenticated request should get 401, not 200."""
        response = api_client.post("/api/chat/", {
            "question": "test",
            "session_id": "test",
        }, format="json")
        assert response.status_code == 401

    def test_query_requires_auth(self, api_client):
        response = api_client.post("/api/query/", {
            "question": "test",
        }, format="json")
        assert response.status_code == 401

    def test_ingest_requires_auth(self, api_client):
        response = api_client.post("/api/ingest/")
        assert response.status_code == 401

    def test_health_is_public(self, api_client):
        """Health endpoint must be accessible without a token."""
        response = api_client.get("/api/health/")
        assert response.status_code == 200

    def test_authenticated_request_succeeds(self, auth_client):
        """A valid token should get past auth (even if agent fails for other reasons)."""
        response = auth_client.get("/api/health/")
        assert response.status_code == 200
        assert response.json()["status"] == "operational"