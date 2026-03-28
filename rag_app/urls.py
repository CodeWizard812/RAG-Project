from django.urls import path
from rag_app.views import (
    HealthView,
    QueryView,
    ChatView,
    ClearSessionView,
    SessionHistoryView,
)

urlpatterns = [
    # System
    path("health/",          HealthView.as_view(),         name="health"),

    # Stateless single query
    path("query/",           QueryView.as_view(),           name="query"),

    # Stateful multi-turn chat
    path("chat/",            ChatView.as_view(),            name="chat"),
    path("chat/clear/",      ClearSessionView.as_view(),    name="chat-clear"),
    path("chat/history/",    SessionHistoryView.as_view(),  name="chat-history"),
]