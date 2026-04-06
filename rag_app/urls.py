# rag_app/urls.py — full replacement

from django.urls import path
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
    TokenVerifyView,
)
from rag_app.views import (
    HealthView,
    QueryView,
    ChatView,
    ClearSessionView,
    SessionHistoryView,
    IngestView,
    DocumentListView,
    StreamingChatView,
    RegisterView,
    SimplePingView,
)

urlpatterns = [
    # System
    path("health/",                   HealthView.as_view(),         name="health"),
    path("ping/",                     SimplePingView.as_view(), name="simple-ping"),

    # Auth — all public
    path("auth/register/",            RegisterView.as_view(),        name="register"),
    path("auth/token/",               TokenObtainPairView.as_view(), name="token-obtain"),
    path("auth/token/refresh/",       TokenRefreshView.as_view(),    name="token-refresh"),
    path("auth/token/verify/",        TokenVerifyView.as_view(),     name="token-verify"),

    # Agent
    path("query/",                    QueryView.as_view(),           name="query"),
    path("chat/",                     ChatView.as_view(),            name="chat"),
    path("chat/stream/",              StreamingChatView.as_view(),   name="chat-stream"),
    path("chat/clear/",               ClearSessionView.as_view(),    name="chat-clear"),
    path("chat/history/",             SessionHistoryView.as_view(),  name="chat-history"),

    # Knowledge base
    path("ingest/",                   IngestView.as_view(),          name="ingest"),
    path("documents/",                DocumentListView.as_view(),    name="documents"),
    path("documents/<str:doc_uuid>/", DocumentListView.as_view(),    name="document-delete"),
]