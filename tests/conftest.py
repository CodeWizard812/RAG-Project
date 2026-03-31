# tests/conftest.py

import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken


@pytest.fixture(scope="session")
def django_db_setup():
    """Use the real database — tests run against actual seeded data."""
    pass


@pytest.fixture
def api_client():
    """Unauthenticated DRF test client."""
    return APIClient()


@pytest.fixture
def test_user(db):
    """Creates a test user and tears it down after the test."""
    user = User.objects.create_user(
        username="testuser",
        password="TestPass@123",
        email="test@ragproject.com",
    )
    yield user
    user.delete()


@pytest.fixture
def auth_client(test_user):
    """
    Authenticated DRF client with a valid JWT Bearer token.
    Use this for any endpoint that requires IsAuthenticated.
    """
    client = APIClient()
    refresh = RefreshToken.for_user(test_user)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {str(refresh.access_token)}")
    return client


@pytest.fixture
def base_url():
    return "http://127.0.0.1:8000"