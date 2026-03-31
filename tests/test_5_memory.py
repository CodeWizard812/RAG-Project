# tests/test_5_memory.py

import pytest
import uuid


@pytest.mark.django_db
class TestSessionMemory:

    def unique_session(self):
        """Generate a unique session ID per test to avoid state bleed."""
        return f"mem-test-{uuid.uuid4().hex[:8]}"

    def chat(self, auth_client, question, session_id):
        r = auth_client.post("/api/chat/",
            {"question": question, "session_id": session_id},
            format="json")
        assert r.status_code == 200
        return r.json()

    def test_history_grows_with_turns(self, auth_client):
        sid = self.unique_session()
        r1 = self.chat(auth_client, "What is ATHR's sector?", sid)
        assert r1["history_length"] == 2

        r2 = self.chat(auth_client, "And what about GRHE?", sid)
        assert r2["history_length"] == 4

    def test_follow_up_references_prior_context(self, auth_client):
        """
        The agent should answer a pronoun follow-up ('their') correctly
        because it has the prior turn in memory.
        """
        sid = self.unique_session()
        self.chat(auth_client, "What is Aether Technologies' market cap?", sid)

        follow_up = self.chat(auth_client,
            "What sector are they in?", sid)
        answer = follow_up["answer"].lower()
        # Should answer "Technology" because it remembers ATHR from turn 1
        assert "technology" in answer, \
            f"Expected 'technology' sector in follow-up: {answer}"

    def test_clear_session_resets_history(self, auth_client):
        sid = self.unique_session()
        self.chat(auth_client, "Tell me about ATHR.", sid)

        auth_client.post("/api/chat/clear/",
            {"session_id": sid}, format="json")

        r = auth_client.get(f"/api/chat/history/?session_id={sid}")
        assert r.json()["turn_count"] == 0

    def test_sessions_are_isolated(self, auth_client):
        """Two different session IDs must not share memory."""
        sid_a = self.unique_session()
        sid_b = self.unique_session()

        self.chat(auth_client, "Remember: the magic word is 'pineapple'.", sid_a)
        result_b = self.chat(auth_client,
            "What magic word did I tell you earlier?", sid_b)

        answer = result_b["answer"].lower()
        assert "pineapple" not in answer, \
            f"Session B should not know session A's context: {answer}"

    def test_history_endpoint_shows_correct_roles(self, auth_client):
        sid = self.unique_session()
        self.chat(auth_client, "What is PFGP's ticker?", sid)

        r = auth_client.get(f"/api/chat/history/?session_id={sid}")
        messages = r.json()["messages"]
        assert messages[0]["role"] == "human"
        assert messages[1]["role"] == "ai"
        assert "PFGP" in messages[0]["content"]