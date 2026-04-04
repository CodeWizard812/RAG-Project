# tests/test_1_infrastructure.py

import pytest
import os


@pytest.mark.django_db
class TestPostgreSQL:
    """Verifies the database is seeded correctly."""

    def test_companies_exist(self):
        from rag_app.models import Company
        count = Company.objects.count()
        assert count == 4, f"Expected 4 companies, found {count}"

    def test_expected_tickers_present(self):
        from rag_app.models import Company
        tickers = set(Company.objects.values_list("ticker", flat=True))
        assert tickers == {"ATHR", "GRHE", "NVMD", "PFGP"}

    def test_financials_count(self):
        from rag_app.models import QuarterlyFinancials
        count = QuarterlyFinancials.objects.count()
        assert count == 24, f"Expected 24 quarterly records, found {count}"

    def test_athr_market_cap(self):
        from rag_app.models import Company
        athr = Company.objects.get(ticker="ATHR")
        assert athr.market_cap == 45_000_000_000

    def test_grhe_has_6_quarters(self):
        from rag_app.models import Company, QuarterlyFinancials
        grhe = Company.objects.get(ticker="GRHE")
        count = QuarterlyFinancials.objects.filter(company=grhe).count()
        assert count == 6, f"Expected 6 quarters for GRHE, found {count}"

    def test_debt_to_equity_is_decimal(self):
        from rag_app.models import QuarterlyFinancials
        from decimal import Decimal
        record = QuarterlyFinancials.objects.filter(company__ticker="GRHE").first()
        assert isinstance(record.debt_to_equity, Decimal)
        assert record.debt_to_equity > 0

    def test_net_margin_property(self):
        from rag_app.models import QuarterlyFinancials
        record = QuarterlyFinancials.objects.filter(company__ticker="ATHR").first()
        margin = record.net_margin
        assert 0 < margin < 100, f"Net margin {margin}% looks wrong"


@pytest.mark.django_db
class TestChromaDB:
    """Verifies the vector store is seeded and queryable."""

    def get_collection(self):
        import chromadb
        from chromadb.utils import embedding_functions
        client = chromadb.PersistentClient(path="./chroma_store")
        ef = embedding_functions.SentenceTransformerEmbeddingFunction("all-MiniLM-L6-v2")
        return client.get_or_create_collection(
            "financial_regulatory_kb", embedding_function=ef
        )

    def test_collection_exists(self):
        import chromadb
        client = chromadb.PersistentClient(path="./chroma_store")
        collections = [c.name for c in client.list_collections()]
        assert "financial_regulatory_kb" in collections

    def test_document_count(self):
        col = self.get_collection()
        assert col.count() >= 4, f"Expected at least 4 docs, found {col.count()}"

    def test_sebi_document_retrievable(self):
        col = self.get_collection()
        results = col.query(
            query_texts=["SEBI investment eligibility debt-to-equity"],
            n_results=1,
        )
        docs = results["documents"][0]
        assert len(docs) > 0
        assert "SEBI" in docs[0] or "debt" in docs[0].lower()

    def test_metadata_has_required_fields(self):
        col = self.get_collection()
        results = col.get(limit=4, include=["metadatas"])
        for meta in results["metadatas"]:
            assert "source" in meta,   f"Missing 'source' in metadata: {meta}"
            assert "category" in meta, f"Missing 'category' in metadata: {meta}"

    def test_similarity_search_returns_relevant_result(self):
        col = self.get_collection()
        results = col.query(
            query_texts=["Aether Technologies AI strategy pivot"],
            n_results=1,
        )
        top_doc = results["documents"][0][0]
        assert "Aether" in top_doc or "AI" in top_doc or "AetherMind" in top_doc


class TestRedis:
    """Verifies Redis connectivity."""

    def test_redis_ping(self):
        import redis
        url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        if os.getenv("USE_REDIS", "true").lower() == "false":
            pytest.skip("USE_REDIS=false — Redis test skipped")
        r = redis.from_url(url)
        assert r.ping() is True

    def test_redis_set_get(self):
        import redis
        url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        if os.getenv("USE_REDIS", "true").lower() == "false":
            pytest.skip("USE_REDIS=false — Redis test skipped")
        r = redis.from_url(url)
        r.set("rag_test_key", "working", ex=10)
        val = r.get("rag_test_key")
        assert val.decode() == "working"

class TestKeyPool:
    """Verifies key pool loads and rotates correctly."""

    def test_pool_loads_at_least_one_key(self):
        from rag_app.utils.key_pool import get_key_pool
        pool = get_key_pool()
        status = pool.status()
        assert status["total_keys"] >= 1, \
            "No API keys found — check GEMINI_API_KEY_1 in .env"

    def test_pool_status_schema(self):
        from rag_app.utils.key_pool import get_key_pool
        status = get_key_pool().status()
        assert "total_keys"     in status
        assert "available_keys" in status
        assert "exhausted_keys" in status
        assert status["available_keys"] <= status["total_keys"]

    def test_mark_exhausted_reduces_available(self):
        from rag_app.utils.key_pool import GeminiKeyPool
        # Test with a fresh pool instance so we don't affect the singleton
        import unittest.mock as mock
        with mock.patch.dict("os.environ", {
            "GEMINI_API_KEY_1": "fake_key_aaa",
            "GEMINI_API_KEY_2": "fake_key_bbb",
        }):
            pool = GeminiKeyPool()
            assert pool.status()["available_keys"] == 2
            pool.mark_exhausted("fake_key_aaa")
            assert pool.status()["available_keys"] == 1

    def test_exhausted_key_recovers_after_cooldown(self):
        from rag_app.utils.key_pool import GeminiKeyPool
        import unittest.mock as mock
        with mock.patch.dict("os.environ", {
            "GEMINI_API_KEY_1": "fake_key_ccc",
        }):
            pool = GeminiKeyPool()
            pool.mark_exhausted("fake_key_ccc")
            assert pool.status()["available_keys"] == 0
            # Manually expire the cooldown
            pool._exhausted["fake_key_ccc"] = 0   # set reset time to past
            key = pool.get_available_key()
            assert key == "fake_key_ccc"