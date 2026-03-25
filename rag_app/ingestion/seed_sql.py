import os
import sys
import django

# ── Django bootstrap ──────────────────────────────────────────────────────────
# Resolves to the project root (3 levels up from this file)
PROJECT_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
sys.path.insert(0, PROJECT_ROOT)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "rag_project.settings")
django.setup()
# ─────────────────────────────────────────────────────────────────────────────

from rag_app.models import Company, QuarterlyFinancials


# ── Company seed data ─────────────────────────────────────────────────────────
COMPANIES = [
    {
        "name":        "Aether Technologies",
        "ticker":      "ATHR",
        "sector":      "Technology",
        "market_cap":  45_000_000_000,  # USD 45B — large cap
        "description": "Enterprise AI and cloud infrastructure company pivoting to "
                        "sovereign AI products under the AetherMind brand.",
    },
    {
        "name":        "GreenHorizon Energy",
        "ticker":      "GRHE",
        "sector":      "Clean Energy",
        "market_cap":  12_500_000_000,  # USD 12.5B — mid cap
        "description": "Renewable energy operator running 14 solar farms and "
                        "3 offshore wind installations across South and Southeast Asia.",
    },
    {
        "name":        "NovaMed Pharma",
        "ticker":      "NVMD",
        "sector":      "Pharmaceuticals",
        "market_cap":   8_200_000_000,  # USD 8.2B — mid cap
        "description": "Specialty pharmaceutical company focused on oncology and "
                        "rare disease therapeutics.",
    },
    {
        "name":        "Pinnacle Financial Group",
        "ticker":      "PFGP",
        "sector":      "Financial Services",
        "market_cap":  31_000_000_000,  # USD 31B — large cap
        "description": "Diversified financial services group offering retail banking, "
                        "asset management, and insurance products.",
    },
]

# ── Quarterly financials seed data ────────────────────────────────────────────
# Structure: (ticker, quarter, year, revenue, net_income, opex, d/e ratio)
FINANCIALS = [
    # ── Aether Technologies (ATHR) — strong revenue growth, improving D/E ──
    ("ATHR", 1, 2024, 3_200_000_000,   480_000_000, 2_100_000_000, "0.45"),
    ("ATHR", 2, 2024, 3_450_000_000,   520_000_000, 2_250_000_000, "0.43"),
    ("ATHR", 3, 2024, 3_800_000_000,   610_000_000, 2_400_000_000, "0.41"),
    ("ATHR", 4, 2024, 4_100_000_000,   690_000_000, 2_600_000_000, "0.39"),
    ("ATHR", 1, 2025, 4_400_000_000,   750_000_000, 2_800_000_000, "0.37"),
    ("ATHR", 2, 2025, 4_750_000_000,   820_000_000, 2_950_000_000, "0.35"),

    # ── GreenHorizon Energy (GRHE) — high D/E due to infra capex, improving ──
    ("GRHE", 1, 2024,   780_000_000,    62_000_000,   650_000_000, "1.82"),
    ("GRHE", 2, 2024,   820_000_000,    71_000_000,   680_000_000, "1.75"),
    ("GRHE", 3, 2024,   910_000_000,    88_000_000,   740_000_000, "1.68"),
    ("GRHE", 4, 2024,   950_000_000,    95_000_000,   770_000_000, "1.61"),
    ("GRHE", 1, 2025, 1_020_000_000,   110_000_000,   820_000_000, "1.55"),
    ("GRHE", 2, 2025, 1_080_000_000,   125_000_000,   855_000_000, "1.48"),

    # ── NovaMed Pharma (NVMD) — steady growth, healthy margins ──
    ("NVMD", 1, 2024,   520_000_000,   104_000_000,   370_000_000, "0.92"),
    ("NVMD", 2, 2024,   548_000_000,   112_000_000,   385_000_000, "0.88"),
    ("NVMD", 3, 2024,   575_000_000,   118_000_000,   400_000_000, "0.85"),
    ("NVMD", 4, 2024,   610_000_000,   130_000_000,   415_000_000, "0.81"),
    ("NVMD", 1, 2025,   640_000_000,   140_000_000,   430_000_000, "0.78"),
    ("NVMD", 2, 2025,   672_000_000,   152_000_000,   445_000_000, "0.74"),

    # ── Pinnacle Financial Group (PFGP) — high D/E normal for financials ──
    ("PFGP", 1, 2024, 2_100_000_000,   420_000_000, 1_450_000_000, "3.20"),
    ("PFGP", 2, 2024, 2_250_000_000,   455_000_000, 1_530_000_000, "3.15"),
    ("PFGP", 3, 2024, 2_380_000_000,   490_000_000, 1_610_000_000, "3.08"),
    ("PFGP", 4, 2024, 2_520_000_000,   530_000_000, 1_680_000_000, "3.01"),
    ("PFGP", 1, 2025, 2_650_000_000,   560_000_000, 1_750_000_000, "2.95"),
    ("PFGP", 2, 2025, 2_780_000_000,   595_000_000, 1_820_000_000, "2.88"),
]


def clear_data() -> None:
    qf_count = QuarterlyFinancials.objects.count()
    co_count = Company.objects.count()
    QuarterlyFinancials.objects.all().delete()
    Company.objects.all().delete()
    print(f"  Cleared {qf_count} quarterly records and {co_count} companies.")


def seed_companies() -> dict:
    """Seeds Company records and returns a ticker → Company instance map."""
    company_map = {}
    for data in COMPANIES:
        company = Company.objects.create(**data)
        company_map[data["ticker"]] = company
        print(f"  Created: {company}  |  Market Cap: USD {company.market_cap_billions}B")
    return company_map


def seed_financials(company_map: dict) -> None:
    """Seeds QuarterlyFinancials records for all companies."""
    records = []
    for (ticker, quarter, year, revenue, net_income, opex, dte) in FINANCIALS:
        records.append(QuarterlyFinancials(
            company           = company_map[ticker],
            quarter           = quarter,
            year              = year,
            revenue           = revenue,
            net_income        = net_income,
            operating_expenses= opex,
            debt_to_equity    = dte,
        ))
    QuarterlyFinancials.objects.bulk_create(records)
    print(f"  Created {len(records)} quarterly financial records via bulk_create.")


def run():
    print("\n── SQL Seeder: Financial & Regulatory Intelligence Agent ──")
    print("\n[1/3] Clearing existing data...")
    clear_data()

    print("\n[2/3] Seeding companies...")
    company_map = seed_companies()

    print("\n[3/3] Seeding quarterly financials...")
    seed_financials(company_map)

    print(f"\n✅ Done — {Company.objects.count()} companies, "
          f"{QuarterlyFinancials.objects.count()} quarterly records in PostgreSQL.\n")


if __name__ == "__main__":
    run()