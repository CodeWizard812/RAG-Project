import pytest


@pytest.mark.django_db
class TestSQLToolAccuracy:
    """
    Tests that the agent retrieves correct numerical facts from PostgreSQL.
    Each test has a known ground-truth answer from seed_sql.py.
    """

    def ask(self, auth_client, question):
        r = auth_client.post("/api/query/",
            {"question": question}, format="json")
        assert r.status_code == 200
        return r.json()

    def test_athr_revenue_q2_2025(self, auth_client):
        """ATHR Q2 2025 revenue is seeded as 4,750,000,000."""
        result = self.ask(auth_client, "What was Aether Technologies revenue in Q2 2025?")
        answer = result["answer"]
        # Accept any representation: 4750000000 or 4.75B or 4,750,000,000
        assert any(x in answer for x in ["4750000000", "4.75", "4,750"]), \
            f"Expected ATHR Q2 2025 revenue ~4.75B in: {answer}"

    def test_grhe_latest_de_ratio(self, auth_client):
        """GRHE latest D/E is seeded as 1.48 (Q2 2025)."""
        result = self.ask(auth_client,
            "What is GreenHorizon Energy's most recent debt-to-equity ratio?")
        answer = result["answer"]
        assert "1.48" in answer, \
            f"Expected D/E ratio 1.48 in answer: {answer}"

    def test_pfgp_sector(self, auth_client):
        """Pinnacle Financial Group sector is seeded as 'Financial Services'."""
        result = self.ask(auth_client,
            "What sector is Pinnacle Financial Group in?")
        answer = result["answer"].lower()
        assert "financial" in answer, \
            f"Expected 'financial' in sector answer: {answer}"

    def test_highest_market_cap_company(self, auth_client):
        """ATHR has the highest market cap at 45B — higher than PFGP at 31B."""
        result = self.ask(auth_client,
            "Which company has the highest market capitalisation?")
        answer = result["answer"]
        assert "Aether" in answer or "ATHR" in answer, \
            f"Expected Aether Technologies to have highest market cap: {answer}"

    def test_sql_tool_was_called(self, auth_client):
        """Quantitative question must route to the SQL tool, not vector tool."""
        result = self.ask(auth_client,
            "What was GRHE net income in Q1 2024?")
        tools_used = [t["tool"] for t in result["tool_calls"]]
        assert "financial_database_query" in tools_used, \
            f"Expected SQL tool to be called. Tools used: {tools_used}"

    def test_nvmd_all_quarters_positive_net_income(self, auth_client):
        """All 6 NovaMed quarters have positive net income in seeded data."""
        result = self.ask(auth_client,
            "Did NovaMed Pharma report positive net income in all quarters?")
        answer = result["answer"].lower()
        assert any(w in answer for w in ["positive", "yes", "all", "profit"]), \
            f"Expected positive net income confirmation: {answer}"


@pytest.mark.django_db
class TestVectorToolAccuracy:
    """
    Tests that the agent retrieves correct qualitative facts from ChromaDB.
    """

    def ask(self, auth_client, question):
        r = auth_client.post("/api/query/",
            {"question": question}, format="json")
        assert r.status_code == 200
        return r.json()

    def test_sebi_de_limit_for_tech(self, auth_client):
        """SEBI circular states D/E must not exceed 2.0 for tech companies."""
        result = self.ask(auth_client,
            "What is the SEBI debt-to-equity limit for technology companies?")
        answer = result["answer"]
        assert "2.0" in answer or "2" in answer, \
            f"Expected D/E limit of 2.0 in answer: {answer}"

    def test_sebi_profitability_requirement(self, auth_client):
        """SEBI requires positive net income in 3 of 4 quarters."""
        result = self.ask(auth_client,
            "How many quarters of profitability does SEBI require for investment eligibility?")
        answer = result["answer"]
        assert "3" in answer, \
            f"Expected '3 of 4 quarters' in answer: {answer}"

    def test_aether_ai_strategy_mentioned(self, auth_client):
        """Earnings transcript mentions AetherMind and AI pivot."""
        result = self.ask(auth_client,
            "What is Aether Technologies' strategic direction according to their earnings call?")
        answer = result["answer"].lower()
        assert any(w in answer for w in ["ai", "aethermind", "artificial intelligence", "pivot"]), \
            f"Expected AI strategy mention: {answer}"

    def test_grhe_esg_certification_body(self, auth_client):
        """ESG report states KPMG ESG Advisory issued the certificate."""
        result = self.ask(auth_client,
            "Which firm certified GreenHorizon Energy's ESG compliance?")
        answer = result["answer"]
        assert "KPMG" in answer, \
            f"Expected KPMG in ESG certification answer: {answer}"

    def test_vector_tool_was_called(self, auth_client):
        """Regulatory question must route to vector tool, not SQL."""
        result = self.ask(auth_client,
            "What are the SEBI disclosure requirements for large-cap companies?")
        tools_used = [t["tool"] for t in result["tool_calls"]]
        assert "regulatory_knowledge_search" in tools_used, \
            f"Expected vector tool to be called. Tools used: {tools_used}"


@pytest.mark.django_db
class TestCrossReferenceAccuracy:
    """
    Tests the most important capability — using BOTH tools together.
    """

    def ask(self, auth_client, question):
        r = auth_client.post("/api/query/",
            {"question": question}, format="json")
        assert r.status_code == 200
        return r.json()

    def test_both_tools_called_for_eligibility(self, auth_client):
        """Eligibility question requires both DB (financials) and vector (SEBI rules)."""
        result = self.ask(auth_client,
            "Is GreenHorizon Energy eligible for institutional investment under SEBI rules?")
        tools_used = [t["tool"] for t in result["tool_calls"]]
        assert "financial_database_query" in tools_used, \
            f"SQL tool not called: {tools_used}"
        assert "regulatory_knowledge_search" in tools_used, \
            f"Vector tool not called: {tools_used}"

    def test_eligibility_answer_mentions_de_ratio(self, auth_client):
        """Cross-reference answer must reference actual D/E figures."""
        result = self.ask(auth_client,
            "Is GreenHorizon Energy eligible for institutional investment under SEBI rules?")
        answer = result["answer"]
        assert any(x in answer for x in ["1.48", "1.82", "D/E", "debt"]), \
            f"Expected D/E ratio data in cross-reference answer: {answer}"

    def test_comparison_uses_both_tools(self, auth_client):
        """The flagship demo query — compare two companies."""
        result = self.ask(auth_client,
            "Compare Aether Technologies and GreenHorizon Energy for SEBI investment eligibility.")
        tools_used = [t["tool"] for t in result["tool_calls"]]
        answer = result["answer"]
        assert "financial_database_query" in tools_used
        assert "regulatory_knowledge_search" in tools_used
        assert "Aether" in answer or "ATHR" in answer
        assert "GreenHorizon" in answer or "GRHE" in answer