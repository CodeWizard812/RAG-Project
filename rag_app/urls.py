from django.urls import path
from rag_app.views import (
    HealthView,
    QueryView,
    ChatView,
    ClearSessionView,
    SessionHistoryView,
    IngestView,
    DocumentListView,
)

urlpatterns = [
    # System
    path("health/",                        HealthView.as_view(),        name="health"),

    # Agent endpoints
    path("query/",                         QueryView.as_view(),          name="query"),
    path("chat/",                          ChatView.as_view(),           name="chat"),
    path("chat/clear/",                    ClearSessionView.as_view(),   name="chat-clear"),
    path("chat/history/",                  SessionHistoryView.as_view(), name="chat-history"),

    # Knowledge base management
    path("ingest/",                        IngestView.as_view(),         name="ingest"),
    path("documents/",                     DocumentListView.as_view(),   name="documents"),
    path("documents/<str:doc_uuid>/",      DocumentListView.as_view(),   name="document-delete"),
]