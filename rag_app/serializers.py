from rest_framework import serializers


class QueryRequestSerializer(serializers.Serializer):
    """Validates the body of POST /api/query/ (stateless, no memory)."""
    question = serializers.CharField(
        min_length=3,
        max_length=2000,
        trim_whitespace=True,
        error_messages={
            "blank":     "Question cannot be blank.",
            "min_length": "Question must be at least 3 characters.",
        }
    )


class ChatRequestSerializer(serializers.Serializer):
    """Validates the body of POST /api/chat/ (stateful, session memory)."""
    question = serializers.CharField(
        min_length=3,
        max_length=2000,
        trim_whitespace=True,
    )
    session_id = serializers.CharField(
        max_length=128,
        default="default",
        trim_whitespace=True,
        help_text="Unique identifier for the conversation thread.",
    )


class ClearSessionRequestSerializer(serializers.Serializer):
    """Validates the body of POST /api/chat/clear/."""
    session_id = serializers.CharField(
        max_length=128,
        trim_whitespace=True,
    )


class ToolCallSerializer(serializers.Serializer):
    """Read-only serializer for a single tool invocation in the response."""
    tool  = serializers.CharField()
    input = serializers.JSONField()


class AgentResponseSerializer(serializers.Serializer):
    """Shapes the outgoing JSON response from the agent."""
    answer         = serializers.CharField()
    session_id     = serializers.CharField()
    tool_calls     = ToolCallSerializer(many=True)
    history_length = serializers.IntegerField()

# rag_app/serializers.py  — ADD to bottom of existing file

class IngestRequestSerializer(serializers.Serializer):
    """Validates the multipart form fields for POST /api/ingest/."""
    file          = serializers.FileField()
    source_name   = serializers.CharField(max_length=255)
    category      = serializers.ChoiceField(choices=[
        "Regulatory", "Transcript", "ESG", "Research", "Other"
    ])
    document_type = serializers.CharField(max_length=255)
    # Optional extra metadata as a JSON string
    # e.g. '{"company_ticker": "ATHR", "year": "2025"}'
    extra_metadata = serializers.CharField(
        required=False,
        allow_blank=True,
        default="{}",
        help_text="Optional JSON string of extra metadata fields.",
    )


class DocumentSerializer(serializers.Serializer):
    """Shapes one document record in the /api/documents/ response."""
    doc_uuid      = serializers.CharField(allow_null=True)
    source_name   = serializers.CharField()
    category      = serializers.CharField()
    document_type = serializers.CharField()
    file_name     = serializers.CharField()
    chunk_count   = serializers.IntegerField()