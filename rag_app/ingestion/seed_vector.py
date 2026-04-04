import os
import sys
import django

# ── Django bootstrap ──────────────────────────────────────────────────────────
PROJECT_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
sys.path.insert(0, PROJECT_ROOT)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "rag_project.settings")
django.setup()
# ─────────────────────────────────────────────────────────────────────────────

import chromadb
from rag_app.utils.embeddings import GeminiEmbeddingFunction

CHROMA_PATH     = os.getenv("CHROMA_PATH", "./chroma_store")
COLLECTION_NAME = "financial_regulatory_kb"

# ── Document corpus ───────────────────────────────────────────────────────────
DOCUMENTS = [
    # ── Doc 1: SEBI Investment Eligibility ───────────────────────────────────
    {
        "id": "reg_sebi_001",
        "content": (
            "SEBI Investment Eligibility Framework — Circular REG/2024/007\n\n"
            "Pursuant to SEBI (Securities and Exchange Board of India) guidelines, the following "
            "criteria must be met for a company to qualify for institutional investment eligibility "
            "under Category A:\n\n"
            "1. Minimum Market Capitalisation: The entity must maintain a minimum market "
            "capitalisation of INR 500 crore (approx. USD 60 million) for at least 12 consecutive "
            "months prior to the investment date.\n\n"
            "2. Debt-to-Equity Ratio: The consolidated Debt-to-Equity (D/E) ratio must not exceed "
            "2.0 for manufacturing and technology companies. For financial services entities, a D/E "
            "ratio up to 4.0 is permissible given the nature of their leveraged business models.\n\n"
            "3. Profitability Requirement: The company must have reported positive net income in at "
            "least 3 of the last 4 consecutive quarters prior to evaluation.\n\n"
            "4. Sector Restrictions: Companies operating in sectors flagged under the SEBI "
            "High-Risk Sector Watch List — including certain speculative energy ventures — must "
            "provide an additional ESG compliance certificate from a SEBI-registered audit firm "
            "before institutional funds can be deployed.\n\n"
            "5. Disclosure Compliance: Entities must be fully compliant with SEBI (LODR) "
            "Regulations 2015, with no pending enforcement actions."
        ),
        "metadata": {
            "source":          "SEBI Circular REG/2024/007",
            "category":        "Regulatory",
            "document_type":   "Investment Eligibility",
            "jurisdiction":    "India",
            "effective_date":  "2024-04-01",
        },
    },

    # ── Doc 2: Quarterly Disclosure Requirements ──────────────────────────────
    {
        "id": "reg_disclosure_002",
        "content": (
            "Quarterly Disclosure Requirements — Financial Reporting Standards (FRS-Q/2024)\n\n"
            "As per the revised Financial Reporting Standards effective Q1 2024, all publicly "
            "listed entities are mandated to comply with the following quarterly disclosure "
            "obligations:\n\n"
            "1. Revenue Segmentation: Companies with revenue exceeding USD 500 million per quarter "
            "must provide segment-wise revenue breakdown within 45 days of quarter close.\n\n"
            "2. Related-Party Transactions: Any related-party transaction exceeding 1% of annual "
            "turnover must be disclosed in the quarterly filing with full counterparty details.\n\n"
            "3. Debt Covenant Disclosures: Entities must disclose any breach or waiver of "
            "financial covenants on debt instruments, along with corrective measures, in the same "
            "quarter of occurrence.\n\n"
            "4. Material Events: The following qualify as material events requiring immediate "
            "(T+1) disclosure: CEO/CFO changes, regulatory investigations, impairment charges "
            "exceeding 5% of total assets, and any force majeure events impacting over 20% of "
            "operations.\n\n"
            "5. Forward-Looking Statements: Any guidance issued in quarterly earnings calls must "
            "include a Safe Harbor disclaimer. Failure to include this disclaimer may attract "
            "regulatory scrutiny under the securities fraud prevention framework.\n\n"
            "6. ESG Metrics: Beginning Q3 2024, large-cap companies (market cap > USD 1 billion) "
            "are required to include Scope 1 and Scope 2 carbon emission data in their "
            "quarterly reports."
        ),
        "metadata": {
            "source":          "Financial Reporting Standards FRS-Q/2024",
            "category":        "Regulatory",
            "document_type":   "Disclosure Requirements",
            "jurisdiction":    "Global",
            "effective_date":  "2024-01-01",
        },
    },

    # ── Doc 3: Aether Technologies Earnings Transcript ────────────────────────
    {
        "id": "transcript_athr_q2_2025",
        "content": (
            "Aether Technologies Inc. — Q2 FY2025 Earnings Call Transcript (Excerpt)\n\n"
            "[CEO — Mr. Rohan Mehta]:\n\n"
            "Thank you, Sarah. I'd like to speak directly to our strategic pivot to Artificial "
            "Intelligence, which is the centrepiece of our FY2025 vision.\n\n"
            "In Q2 FY2025, we deployed approximately USD 280 million into AI infrastructure — "
            "a 34% increase from the prior quarter. This includes our new sovereign AI data centre "
            "in Hyderabad and our partnership with three Tier-1 cloud providers to host "
            "ATHR-Intelligence, our proprietary foundation model.\n\n"
            "The early returns are encouraging. Our AI-driven SaaS product line, branded "
            "'AetherMind,' saw a 62% quarter-over-quarter increase in enterprise client "
            "onboarding. We currently have 140 enterprise clients on AetherMind's waitlist, "
            "representing a pipeline of approximately USD 380 million in ARR.\n\n"
            "However — and I want to be transparent about this — this pivot carries execution "
            "risk. We are accelerating capex in a period where macroeconomic headwinds are real. "
            "Our D/E ratio has compressed from 0.45 in Q1 FY2024 to 0.35 in Q2 FY2025, "
            "reflecting disciplined balance sheet management. But the pace of AI investment will "
            "require us to revisit our capital allocation framework in Q3.\n\n"
            "In terms of regulatory exposure: we are in active dialogue with SEBI and the Ministry "
            "of Electronics and IT (MeitY) regarding data localisation requirements for "
            "ATHR-Intelligence. We expect full compliance certification by Q4 FY2025.\n\n"
            "Guidance: We are raising our FY2025 full-year revenue guidance to USD 19.2 billion, "
            "up from our earlier estimate of USD 18.5 billion, reflecting strong AI segment "
            "performance. [Safe Harbor: Forward-looking statements are subject to risks and "
            "uncertainties and actual results may differ materially.]"
        ),
        "metadata": {
            "source":           "Aether Technologies Q2 FY2025 Earnings Call",
            "category":         "Transcript",
            "document_type":    "Earnings Transcript",
            "company_ticker":   "ATHR",
            "company_name":     "Aether Technologies",
            "quarter":          "Q2",
            "year":             "2025",
        },
    },

    # ── Doc 4: GreenHorizon ESG Compliance Report ─────────────────────────────
    {
        "id": "esg_grhe_fy2024",
        "content": (
            "GreenHorizon Energy — ESG Compliance & Risk Disclosure Report (FY2024 Annual)\n\n"
            "GreenHorizon Energy (GRHE) presents this ESG Compliance Report in accordance with "
            "SEBI's High-Risk Sector Watch List requirements for clean energy enterprises.\n\n"
            "Environmental Risk Profile:\n"
            "GRHE operates 14 solar farms and 3 offshore wind installations. The company's Scope 1 "
            "emissions for FY2024 totalled 18,400 tonnes CO2e — a 22% reduction from FY2023, "
            "attributable to the decommissioning of two legacy gas-peaker plants.\n\n"
            "Regulatory Compliance Status:\n"
            "GRHE has obtained ESG compliance certification from KPMG ESG Advisory (SEBI-registered) "
            "for FY2024, satisfying the additional disclosure requirement under SEBI Circular "
            "REG/2024/007 for high-risk sector entities.\n\n"
            "Debt Profile & Covenant Status:\n"
            "The company's elevated D/E ratio (1.82 in Q1 FY2024, improving to 1.48 in Q2 FY2025) "
            "is consistent with capital-intensive renewable infrastructure buildouts. All existing "
            "debt covenants have been met. A USD 400 million green bond issuance is planned for "
            "Q3 FY2025 to refinance legacy project debt at lower rates.\n\n"
            "Investment Eligibility Note:\n"
            "As a clean energy entity under SEBI's High-Risk Sector Watch List, institutional "
            "investors must verify GRHE's ESG certification before deploying Category A institutional "
            "funds. This certificate is valid through March 31, 2025, and renewal is in progress."
        ),
        "metadata": {
            "source":           "GreenHorizon Energy ESG Report FY2024",
            "category":         "Regulatory",
            "document_type":    "ESG Compliance Report",
            "company_ticker":   "GRHE",
            "company_name":     "GreenHorizon Energy",
            "year":             "2024",
        },
    },
]


def get_collection():
    client = chromadb.PersistentClient(path=CHROMA_PATH)
    ef     = GeminiEmbeddingFunction()
    collection = client.get_or_create_collection(
        name=COLLECTION_NAME,
        embedding_function=ef,
        metadata={"hnsw:space": "cosine"},
    )
    return client, collection


def run():
    print("\n── Vector Seeder: Financial & Regulatory Intelligence Agent ──")
    print(f"  Collection      : {COLLECTION_NAME}")
    print(f"  Chroma path     : {CHROMA_PATH}\n")

    _, collection = get_collection()

    # Clear existing documents to avoid duplicates
    existing = collection.get()
    if existing["ids"]:
        collection.delete(ids=existing["ids"])
        print(f"[1/2] Cleared {len(existing['ids'])} existing document(s).\n")
    else:
        print("[1/2] Collection is empty — no clearing needed.\n")

    # Add all documents
    collection.add(
        ids       = [doc["id"]       for doc in DOCUMENTS],
        documents = [doc["content"]  for doc in DOCUMENTS],
        metadatas = [doc["metadata"] for doc in DOCUMENTS],
    )

    print(f"[2/2] Seeded {len(DOCUMENTS)} documents:\n")
    for doc in DOCUMENTS:
        print(f"  [{doc['metadata']['category']:12s}]  "
              f"{doc['id']}  —  {doc['metadata']['source'][:55]}...")

    print(f"\n✅ ChromaDB ready. Total documents: {collection.count()}\n")


if __name__ == "__main__":
    run()