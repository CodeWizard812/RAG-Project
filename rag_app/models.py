from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator


class Company(models.Model):
    """
    Represents a publicly listed company being tracked by the intelligence system.
    """

    SECTOR_CHOICES = [
        ("Technology",          "Technology"),
        ("Clean Energy",        "Clean Energy"),
        ("Pharmaceuticals",     "Pharmaceuticals"),
        ("Financial Services",  "Financial Services"),
        ("Manufacturing",       "Manufacturing"),
        ("Consumer Goods",      "Consumer Goods"),
        ("Other",               "Other"),
    ]

    name        = models.CharField(max_length=255)
    ticker      = models.CharField(max_length=20, unique=True, db_index=True)
    sector      = models.CharField(max_length=100, choices=SECTOR_CHOICES, default="Other")
    market_cap  = models.BigIntegerField(
        help_text="Market capitalisation in USD"
    )
    description = models.TextField(blank=True, default="")
    is_active   = models.BooleanField(default=True)
    created_at  = models.DateTimeField(auto_now_add=True)
    updated_at  = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name        = "Company"
        verbose_name_plural = "Companies"
        ordering            = ["name"]

    def __str__(self):
        return f"{self.name} ({self.ticker})"

    @property
    def market_cap_billions(self) -> float:
        """Returns market cap formatted in billions for readability."""
        return round(self.market_cap / 1_000_000_000, 2)


class QuarterlyFinancials(models.Model):
    """
    Stores quarterly financial metrics for a Company.
    One record per (company, quarter, year) combination.
    """

    QUARTER_CHOICES = [
        (1, "Q1 (Jan–Mar)"),
        (2, "Q2 (Apr–Jun)"),
        (3, "Q3 (Jul–Sep)"),
        (4, "Q4 (Oct–Dec)"),
    ]

    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name="financials",
        db_index=True,
    )
    quarter = models.IntegerField(
        choices=QUARTER_CHOICES,
        validators=[MinValueValidator(1), MaxValueValidator(4)],
    )
    year = models.IntegerField(
        validators=[MinValueValidator(2000), MaxValueValidator(2100)],
    )

    # Core financial metrics (in USD)
    revenue             = models.BigIntegerField(help_text="Total revenue in USD")
    net_income          = models.BigIntegerField(help_text="Net income (profit) in USD")
    operating_expenses  = models.BigIntegerField(help_text="Total operating expenses in USD")
    debt_to_equity      = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        help_text="Debt-to-Equity ratio (e.g., 1.82 means 1.82x leveraged)"
    )

    # Optional analyst notes
    analyst_notes = models.TextField(blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name        = "Quarterly Financials"
        verbose_name_plural = "Quarterly Financials"
        unique_together     = ("company", "quarter", "year")
        ordering            = ["-year", "-quarter"]

    def __str__(self):
        return f"{self.company.ticker} — Q{self.quarter} {self.year}"

    @property
    def net_margin(self) -> float:
        """Calculates net profit margin as a percentage."""
        if not self.revenue:
            return 0.0
        return round((self.net_income / self.revenue) * 100, 2)

    @property
    def label(self) -> str:
        return f"Q{self.quarter} FY{self.year}"