# test_suite.py
import os
import django
from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv()

# Setup Django environment for tests that touch the DB or DRF
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "rag_project.settings")
try:
    django.setup()
except Exception as e:
    print(f"Django Setup Error: {e}")

def test_env_vars():
    print("\n=== TEST 1: Environment Variables ===")
    required = ["GEMINI_API_KEY", "SECRET_KEY", "DB_PASSWORD"]
    missing = []
    
    for key in required:
        val = os.getenv(key)
        if not val:
            missing.append(key)
        else:
            # Masking for security in logs
            masked = (val[:4] + "*" * 8) if val else "MISSING"
            print(f"  [OK] {key}: {masked}")
    
    if missing:
        raise Exception(f"Missing required .env variables: {missing}")
    print("  PASSED")

def test_gemini_25_flash():
    print("\n=== TEST 2: Gemini 2.5 Flash ===")
    from langchain_google_genai import ChatGoogleGenerativeAI
    
    llm = ChatGoogleGenerativeAI(
        model="gemini-2.5-flash",
        google_api_key=os.getenv("GEMINI_API_KEY"),
        temperature=0
    )
    response = llm.invoke("Reply with exactly: GEMINI_2.5_FLASH_OK")
    if "GEMINI_2.5_FLASH_OK" in response.content:
        print(f"  Response: {response.content.strip()}")
        print("  PASSED")
    else:
        raise Exception(f"Unexpected response: {response.content}")

def test_chromadb_embeddings():
    print("\n=== TEST 3: ChromaDB + Sentence Embeddings ===")
    import chromadb
    from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction

    # This might take a moment on the first run to download the model (~90MB)
    ef = SentenceTransformerEmbeddingFunction(model_name="all-MiniLM-L6-v2")
    client = chromadb.EphemeralClient() 
    collection = client.create_collection("test_col", embedding_function=ef)

    collection.add(
        documents=["LangChain helps build LLM-powered applications."],
        ids=["doc1"]
    )

    results = collection.query(query_texts=["What is LangChain?"], n_results=1)
    if len(results["documents"][0]) > 0:
        print(f"  Retrieved: '{results['documents'][0][0][:50]}...'")
        print("  PASSED")
    else:
        raise Exception("No results returned from ChromaDB")

def test_postgres_readwrite():
    print("\n=== TEST 4: PostgreSQL Read/Write ===")
    from django.db import connection
    with connection.cursor() as cursor:
        cursor.execute("CREATE TABLE IF NOT EXISTS test_phase1 (id SERIAL, msg TEXT);")
        cursor.execute("INSERT INTO test_phase1 (msg) VALUES (%s)", ["phase1_ok"])
        cursor.execute("SELECT msg FROM test_phase1 WHERE msg = 'phase1_ok'")
        row = cursor.fetchone()
        cursor.execute("DROP TABLE test_phase1")
    
    if row and row[0] == "phase1_ok":
        print(f"  DB Write/Read: SUCCESS")
        print("  PASSED")
    else:
        raise Exception("PostgreSQL read/write failed")

def test_django_drf():
    print("\n=== TEST 5: Django + DRF Setup ===")
    from rest_framework.response import Response
    from rest_framework.views import APIView
    from rest_framework.test import APIRequestFactory

    factory = APIRequestFactory()
    request = factory.get("/ping/")

    class PingView(APIView):
        def get(self, request):
            return Response({"status": "ok"})

    view = PingView.as_view()
    response = view(request)
    if response.data["status"] == "ok":
        print(f"  DRF response: {response.data}")
        print("  PASSED")
    else:
        raise Exception("DRF View failed to respond")

def test_all_imports():
    print("\n=== TEST 6: Phase 2 Import Check ===")
    
    # 1. First, try the new 2026 'Classic' path (Highest probability)
    # 2. Then, try the legacy sub-module path
    # 3. Finally, try the top-level path
    
    import_paths = [
        "langchain_classic.agents",
        "langchain.agents.agent",
        "langchain.agents"
    ]
    
    executor_found = False
    for path in import_paths:
        try:
            mod = __import__(path, fromlist=["AgentExecutor"])
            if hasattr(mod, "AgentExecutor"):
                print(f"  [OK] Found AgentExecutor in: {path}")
                executor_found = True
                break
        except ImportError:
            continue

    if not executor_found:
        print("  [!] AgentExecutor not found in standard paths.")
        print("  [ACTION] Running: pip install langchain-classic")
        os.system("pip install langchain-classic")
        # Try one last time after install
        from langchain_classic.agents import AgentExecutor
        print("  [OK] Found AgentExecutor in: langchain_classic.agents")

    # Check the rest of the Phase 2 essentials
    other_essentials = [
        ("langchain_google_genai", "ChatGoogleGenerativeAI"),
        ("langchain_community.utilities", "SQLDatabase"),
        ("chromadb", "PersistentClient"),
        ("sentence_transformers", "SentenceTransformer"),
    ]
    
    for module, attr in other_essentials:
        try:
            mod = __import__(module, fromlist=[attr])
            getattr(mod, attr)
            print(f"  [OK] {module}.{attr}")
        except Exception as e:
            print(f"  [FAIL] {module}.{attr} — {e}")
            raise
            
    print("  PASSED")

if __name__ == "__main__":
    tests = [
        test_env_vars,
        test_gemini_25_flash,
        test_chromadb_embeddings,
        test_postgres_readwrite,
        test_django_drf,
        test_all_imports,
    ]
    
    passed_count = 0
    failed_list = []
    
    print("Starting Agentic RAG Phase 1 Test Suite...")
    print("="*40)

    for test in tests:
        try:
            test()
            passed_count += 1
        except Exception as e:
            print(f"  [FAILED] {test.__name__}: {e}")
            failed_list.append(test.__name__)
    
    print(f"\n{'='*40}")
    print(f"OVERALL RESULTS: {passed_count}/{len(tests)} PASSED")
    
    if not failed_list:
        print("🎉 All systems go! You are ready for Phase 2: Building the Agent logic.")
    else:
        print(f"❌ Issues found in: {', '.join(failed_list)}")
        print("Fix the errors above before moving to Phase 2.")