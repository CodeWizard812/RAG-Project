<div align="center">

# FinIntel Agent

### A production-grade Agentic RAG system that cross-references live financial metrics with regulatory guidelines — answering questions no single database can.

[![Django](https://img.shields.io/badge/Django-6.x-092E20?style=flat-square&logo=django&logoColor=white)](https://www.djangoproject.com/)
[![Next.js](https://img.shields.io/badge/Next.js-15-000000?style=flat-square&logo=next.js&logoColor=white)](https://nextjs.org/)
[![LangChain](https://img.shields.io/badge/LangChain-0.3-1C3C3C?style=flat-square&logo=langchain&logoColor=white)](https://langchain.com/)
[![Gemini](https://img.shields.io/badge/Gemini-2.5-4285F4?style=flat-square&logo=google&logoColor=white)](https://ai.google.dev/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=flat-square)](LICENSE)

[Live Demo](https://finintel-agent.vercel.app) · [Backend API](https://finintel-backend.onrender.com/api/health/) · [Report a Bug](https://github.com/CodeWizard812/RAG-Project/issues)

</div>

---

## What is FinIntel Agent?

FinIntel Agent is a **Financial and Regulatory Intelligence system** powered by an autonomous LangChain agent backed by Google Gemini 2.5. Unlike a standard chatbot, the agent *decides* which data source to query for each question — hitting PostgreSQL for hard numbers (revenue, D/E ratios, net income) and ChromaDB for unstructured regulatory documents (SEBI circulars, ESG reports, earnings transcripts). When a question spans both domains, it queries both simultaneously and synthesises a single coherent answer.

```
User: "Is GreenHorizon Energy eligible for SEBI institutional investment?"

Agent → [SQL]    GRHE market cap, D/E ratio, net income (4 quarters)
      → [Vector] SEBI Circular REG/2024/007, GreenHorizon ESG Report FY2024
      → Synthesises: "Yes — D/E of 1.48 is below SEBI's 2.0 limit. Market cap
                      of USD 12.5B exceeds the USD 60M minimum. KPMG ESG
                      certificate valid. Eligible."
```

---

## Key Features

### Hybrid Agentic Retrieval
The LangChain agent autonomously routes each query to the right tool:

| Question type | Tool invoked | Data source |
|---|---|---|
| Revenue, D/E ratios, net income | `financial_database_query` | PostgreSQL |
| SEBI rules, ESG mandates, transcripts | `regulatory_knowledge_search` | ChromaDB |
| Eligibility checks, comparisons | Both tools + synthesis | PostgreSQL + ChromaDB |

### Real-time Streaming via SSE
Agent execution is streamed token-by-token using Server-Sent Events. The frontend displays live tool-call indicators (`Querying PostgreSQL…`, `Searching regulations…`) while the answer is being assembled — giving users full visibility into the agent's reasoning process.

### PDF Knowledge Base Portal
Upload any regulatory filing, annual report, or earnings transcript directly from the UI. Documents are chunked intelligently, embedded via Google's `text-embedding-004` model, and stored in ChromaDB. The agent can answer questions about uploaded documents in the same session, immediately after upload.

### Production-grade Session Management
- Per-user session isolation — session IDs are namespaced by username in `localStorage`
- Chat history persisted in Upstash Redis with configurable TTL
- Sessions survive logout/login cycles and server restarts
- Inline session renaming and two-click delete with confirmation

### Multi-key API Rate Limit Handling
A thread-safe `GeminiKeyPool` rotates across up to 20 Gemini API keys on 429 errors. Each key's cooldown is tracked independently, distinguishing per-minute exhaustion from daily quota limits. Pool health is exposed at `/api/health/`.

### RAG Quality Evaluation
A RAGAS evaluation pipeline scores the agent on **faithfulness**, **answer relevancy**, **context recall**, and **context precision** against a curated golden dataset of 12 financial Q&A pairs.

---

## Tech Stack

| Layer | Technology |
|---|---|
| **Frontend** | Next.js 15, TypeScript, Tailwind CSS, React Markdown |
| **Backend** | Django 5, Django REST Framework, Gunicorn, WhiteNoise |
| **AI / LLM** | LangChain 0.3, Google Gemini 2.5 Flash / Pro, `text-embedding-004` |
| **Vector Store** | ChromaDB 0.5 (persistent, embedded) |
| **Relational DB** | PostgreSQL (Neon serverless in production) |
| **Session Cache** | Redis (Upstash serverless in production) |
| **Auth** | JWT via `djangorestframework-simplejwt` |
| **Evaluation** | RAGAS, Hugging Face Datasets |
| **Containerisation** | Docker, Docker Compose |
| **Deployment** | Render (backend), Vercel (frontend) |

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Next.js (Vercel)                     │
│  Login · Chat UI · Session sidebar · PDF upload modal   │
└────────────────────────┬────────────────────────────────┘
                         │ HTTPS / SSE
┌────────────────────────▼────────────────────────────────┐
│                  Django REST API (Render)                │
│  /auth/  /chat/stream/  /ingest/  /documents/  /health/ │
│                         │                               │
│          ┌──────────────▼──────────────┐               │
│          │     LangChain AgentExecutor  │               │
│          │   Gemini 2.5 Flash / Pro     │               │
│          └────────┬────────────┬────────┘               │
│                   │            │                        │
│     ┌─────────────▼──┐  ┌──────▼──────────┐            │
│     │  SQL Tool       │  │  Vector Tool    │            │
│     │  NL → SQL       │  │  Cosine search  │            │
│     └────────┬────────┘  └──────┬──────────┘            │
└──────────────│────────────────── │────────────────────── ┘
               │                  │
        ┌──────▼──────┐    ┌───────▼───────┐
        │  PostgreSQL  │    │   ChromaDB    │
        │  (Neon)      │    │  (Embedded)   │
        └─────────────┘    └───────────────┘
```

---

## Local Setup

### Prerequisites

- Python 3.11+
- Node.js 18+
- PostgreSQL running locally
- Redis running locally (or set `USE_REDIS=false` to skip)

### 1. Clone the repository

```bash
git clone https://github.com/CodeWizard812/RAG-Project.git
cd RAG-Project
```

### 2. Python environment

```bash
python -m venv venv

# macOS / Linux
source venv/bin/activate

# Windows
venv\Scripts\activate

pip install -r requirements.txt
pip install -r requirements-dev.txt   # eval + test packages
```

### 3. Environment variables

Create a `.env` file in the project root:

```bash
# Django
SECRET_KEY=your-secret-key-here
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1

# PostgreSQL (local)
DB_NAME=ragdb
DB_USER=postgres
DB_PASSWORD=yourpassword
DB_HOST=localhost
DB_PORT=5432

# Redis
REDIS_URL=redis://localhost:6379/0
USE_REDIS=true   # set to false to use in-memory fallback

# Gemini API keys — add as many as you have for rotation
GEMINI_API_KEY_1=AIzaSy...
GEMINI_API_KEY_2=AIzaSy...
GEMINI_API_KEY_3=AIzaSy...
GEMINI_API_KEY_4=AIzaSy...
GEMINI_API_KEY=AIzaSy...   # fallback for any code reading the single-key variable

# Model selection (flash = faster/free, pro = more capable)
LLM_MODEL_TYPE=gemini-2.5-flash

# Session config
SESSION_TTL_SECONDS=86400
MAX_HISTORY_TURNS=10

# ChromaDB path
CHROMA_PATH=./chroma_store

# JWT
JWT_ACCESS_TOKEN_LIFETIME_MINUTES=60
JWT_REFRESH_TOKEN_LIFETIME_DAYS=7

# Superuser (used by entrypoint.sh)
DJANGO_SUPERUSER_USERNAME=admin
DJANGO_SUPERUSER_PASSWORD=changeme123
DJANGO_SUPERUSER_EMAIL=admin@example.com
```

### 4. Database initialisation

```bash
# Create the PostgreSQL database
psql -U postgres -c "CREATE DATABASE ragdb;"

# Run Django migrations
python manage.py migrate

# Create a superuser
python manage.py createsuperuser

# Seed the SQL database (4 companies, 24 quarterly records)
python rag_app/ingestion/seed_sql.py

# Seed the vector database (4 regulatory + transcript documents)
python rag_app/ingestion/seed_vector.py
```

### 5. Start the backend

```bash
python manage.py runserver
# API available at http://127.0.0.1:8000
```

### 6. Frontend setup

```bash
cd frontend
npm install
```

Create `frontend/.env.local`:

```bash
NEXT_PUBLIC_API_URL=http://127.0.0.1:8000
```

```bash
npm run dev
# UI available at http://localhost:3000
```

---

## Docker Setup

The entire stack (Django, PostgreSQL, Redis) can be started with a single command.

```bash
# Build and start all services
docker-compose up --build

# The entrypoint.sh script automatically:
# 1. Waits for PostgreSQL to be healthy
# 2. Runs migrations
# 3. Creates the superuser
# 4. Seeds SQL and vector data (skips if already present)
# 5. Starts Gunicorn

# In a separate terminal — verify everything is running
curl http://localhost:8000/api/health/
```

To tear down and remove volumes:

```bash
docker-compose down -v
```

### Services

| Service | Port | Description |
|---|---|---|
| `rag_web` | 8000 | Django + Gunicorn |
| `rag_postgres` | 5432 | PostgreSQL 15 |
| `rag_redis` | 6379 | Redis 7 |

---

## Deployment

### Backend — Render

The project includes a `render.yaml` for one-click deployment.

**Manual setup:**

1. Create a new **Web Service** on [render.com](https://render.com)
2. Connect `CodeWizard812/RAG-Project`
3. Runtime: **Python 3**, Root: `/`
4. Build command: `pip install -r requirements.txt && python manage.py collectstatic --noinput`
5. Start command: `sh entrypoint.sh`

**Required environment variables on Render:**

```
DATABASE_URL       → Neon connection string (postgresql://...)
REDIS_URL          → Upstash connection string (rediss://...)
SECRET_KEY         → generate a random 50-char string
DEBUG              → False
USE_REDIS          → true
CHROMA_PATH        → /opt/render/project/src/chroma_store
LLM_MODEL_TYPE     → gemini-2.5-flash
GEMINI_API_KEY_1   → your first Gemini key
GEMINI_API_KEY_2   → your second Gemini key
ALLOWED_HOSTS      → your-app.onrender.com
CORS_ALLOWED_ORIGINS → https://your-app.vercel.app
DJANGO_SUPERUSER_USERNAME → admin
DJANGO_SUPERUSER_PASSWORD → (strong password)
```

### Frontend — Vercel

1. Import the repository on [vercel.com](https://vercel.com)
2. Set **Root Directory** to `frontend`
3. Framework: Next.js (auto-detected)
4. Add environment variable: `NEXT_PUBLIC_API_URL=https://your-backend.onrender.com`

### Keeping the Server Warm (Cold Start Prevention)

Render's free tier spins down services after 15 minutes of inactivity, causing a ~60-second cold start on the next request. This project uses **UptimeRobot** to prevent idle spin-downs.

**Setup:**

1. Create a free account at [uptimerobot.com](https://uptimerobot.com)
2. Add a new monitor:
   - **Type:** HTTP(s)
   - **URL:** `https://your-backend.onrender.com/api/health/`
   - **Interval:** Every 12 minutes
3. UptimeRobot pings the public `/api/health/` endpoint every 12 minutes, keeping the Render dyno active continuously

The `/api/health/` endpoint is `AllowAny` (no authentication required) and returns a lightweight JSON response confirming PostgreSQL, ChromaDB, and the Gemini key pool status — making it an ideal ping target.

---

## RAG Evaluation

The project includes a RAGAS evaluation pipeline to measure answer quality objectively.

### Golden Dataset

`eval/golden_dataset.json` contains 12 hand-curated question/answer pairs across three categories:

| Category | Count | Tests |
|---|---|---|
| `sql_only` | 5 | Revenue figures, D/E ratios, sector queries |
| `vector_only` | 4 | SEBI rules, ESG certification, AI strategy |
| `cross_reference` | 3 | Eligibility checks requiring both tools |

### Running the Evaluation

```bash
# Full evaluation — all 12 questions (~3-4 minutes)
python eval/run_ragas.py

# Single category
python eval/run_ragas.py --category cross_reference

# Single question by ID
python eval/run_ragas.py --id sql_001

# Skip saving the JSON report
python eval/run_ragas.py --no-save
```

### Metrics Explained

| Metric | What it measures | Target |
|---|---|---|
| **Faithfulness** | Does the answer only use facts from retrieved context? | > 0.80 |
| **Answer relevancy** | Does the answer directly address the question? | > 0.85 |
| **Context recall** | Did retrieval find all necessary information? | > 0.70 |
| **Context precision** | Is the retrieved context focused, not noisy? | > 0.65 |

Results are saved to `eval/eval_report.json` and printed to the terminal as a formatted report with per-question breakdown.

---

## API Reference

All endpoints except `/api/health/` and `/api/auth/*` require a JWT Bearer token.

### Authentication

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/auth/register/` | Create a new user account |
| `POST` | `/api/auth/token/` | Obtain access + refresh tokens |
| `POST` | `/api/auth/token/refresh/` | Refresh an expired access token |

### Agent

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/chat/stream/` | **Primary endpoint.** Streams agent execution as SSE events (`tool_start`, `tool_end`, `done`, `error`) |
| `POST` | `/api/query/` | Stateless single-shot query (no memory) |
| `POST` | `/api/chat/` | Stateful query (with session memory) |
| `POST` | `/api/chat/clear/` | Clear a session's message history |
| `GET` | `/api/chat/history/` | Retrieve raw session messages |

### Knowledge Base

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/ingest/` | Upload a PDF — chunks, embeds, and stores it in ChromaDB |
| `GET` | `/api/documents/` | List all documents in the knowledge base |
| `DELETE` | `/api/documents/<doc_uuid>/` | Delete a document and all its chunks |

### System

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/health/` | System status — PostgreSQL, ChromaDB, Gemini key pool. **No auth required.** Used by UptimeRobot for keep-alive pings. |

### Streaming Chat — SSE Event Types

```
POST /api/chat/stream/
Body: { "question": "...", "session_id": "...", "model_type": "gemini-2.5-flash" }

Events:
  data: {"event": "tool_start", "tool": "financial_database_query", "input": "..."}
  data: {"event": "tool_end",   "output_preview": "[(4750000000,)]"}
  data: {"event": "done",       "answer": "...", "tool_calls": [...], "contexts": [...]}
  data: {"event": "error",      "message": "..."}
  data: {"event": "keepalive"}
```

---

## Project Structure

```
RAG-Project/
├── rag_project/              # Django project settings
│   ├── settings.py
│   ├── urls.py
│   └── wsgi.py
├── rag_app/
│   ├── models.py             # Company, QuarterlyFinancials
│   ├── views.py              # All API views
│   ├── serializers.py
│   ├── urls.py
│   ├── agent.py              # LangChain AgentExecutor (lazy singleton)
│   ├── ingestion/
│   │   ├── seed_sql.py       # PostgreSQL seeder
│   │   ├── seed_vector.py    # ChromaDB seeder
│   │   └── pdf_processor.py  # PDF chunking + embedding pipeline
│   ├── tools/
│   │   ├── sql_tool.py       # NL → SQL → PostgreSQL
│   │   └── vector_tool.py    # Cosine search → ChromaDB
│   └── utils/
│       ├── llm_factory.py    # RotatingLLM with key pool
│       ├── key_pool.py       # GeminiKeyPool (thread-safe rotation)
│       └── embeddings.py     # GeminiEmbeddingFunction
├── eval/
│   ├── golden_dataset.json   # 12 ground-truth Q&A pairs
│   └── run_ragas.py          # RAGAS evaluation script
├── tests/
│   ├── conftest.py
│   ├── test_1_infrastructure.py
│   ├── test_2_auth.py
│   ├── test_3_api.py
│   ├── test_4_agent_accuracy.py
│   └── test_5_memory.py
├── frontend/                 # Next.js application
│   ├── app/
│   │   ├── page.tsx          # Login / register page
│   │   └── chat/
│   │       └── page.tsx      # Main chat interface
│   ├── components/
│   │   └── PDFIngestModal.tsx
│   ├── lib/
│   │   ├── api.ts            # All API calls + localStorage helpers
│   │   └── types.ts
│   └── hooks/
├── Dockerfile
├── docker-compose.yml
├── entrypoint.sh             # Production startup script
├── render.yaml               # Render deployment config
├── runtime.txt               # Python 3.11.9
├── requirements.txt          # Production dependencies
├── requirements-dev.txt      # Eval + test dependencies
└── pytest.ini
```

---

## Testing

```bash
# Run full test suite
pytest tests/ -v

# Run by category
pytest tests/test_1_infrastructure.py -v   # DB + ChromaDB + Redis
pytest tests/test_2_auth.py -v             # JWT token flow
pytest tests/test_3_api.py -v             # Endpoint contracts
pytest tests/test_4_agent_accuracy.py -v  # Agent answer correctness
pytest tests/test_5_memory.py -v          # Session memory isolation

# With coverage report
pytest tests/ --cov=rag_app --cov-report=term-missing

# Skip agent tests (no Gemini API calls)
pytest tests/test_1_infrastructure.py tests/test_2_auth.py tests/test_3_api.py -v
```

The test suite includes **agent accuracy tests** that assert correct numerical values (e.g. ATHR Q2 2025 revenue = USD 4.75B) against ground-truth seeded data — verifying the full pipeline from question to SQL to answer.

---

## Seeded Data

Four fictional mid-cap and large-cap companies are pre-seeded for demonstration:

| Company | Ticker | Sector | Market Cap | Quarters |
|---|---|---|---|---|
| Aether Technologies | ATHR | Technology | USD 45B | Q1 FY24 – Q2 FY25 |
| GreenHorizon Energy | GRHE | Clean Energy | USD 12.5B | Q1 FY24 – Q2 FY25 |
| NovaMed Pharma | NVMD | Pharmaceuticals | USD 8.2B | Q1 FY24 – Q2 FY25 |
| Pinnacle Financial Group | PFGP | Financial Services | USD 31B | Q1 FY24 – Q2 FY25 |

Four regulatory documents are pre-seeded in ChromaDB:

- **SEBI Circular REG/2024/007** — Investment Eligibility Framework
- **FRS-Q/2024** — Quarterly Disclosure Requirements
- **Aether Technologies Q2 FY2025 Earnings Transcript** — AI strategic pivot
- **GreenHorizon Energy ESG Report FY2024** — ESG compliance & debt profile

---

## Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/your-feature`
3. Commit your changes: `git commit -m "feat: add your feature"`
4. Push to the branch: `git push origin feature/your-feature`
5. Open a Pull Request

---

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.

---

<div align="center">
  Built by <a href="https://github.com/CodeWizard812">CodeWizard812</a>
</div>
