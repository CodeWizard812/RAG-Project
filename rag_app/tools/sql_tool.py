import os
import logging
from dotenv import load_dotenv
from pydantic import BaseModel, Field
from langchain_core.tools import StructuredTool
from langchain_community.utilities import SQLDatabase

load_dotenv()
logger = logging.getLogger(__name__)


class SQLQueryInput(BaseModel):
    """
    Explicit input schema — forces Gemini to always use the parameter
    name 'query' instead of inventing arbitrary names like 'arg1' or 'ayudará'.
    """
    query: str = Field(description="Natural language question about financial data.")


def _build_db_url() -> str:
    return (
        f"postgresql://{os.getenv('DB_USER', 'postgres')}:"
        f"{os.getenv('DB_PASSWORD', 'yourpassword')}@"
        f"{os.getenv('DB_HOST', 'localhost')}:"
        f"{os.getenv('DB_PORT', '5432')}/"
        f"{os.getenv('DB_NAME', 'ragdb')}"
    )


def get_sql_tool() -> StructuredTool:
    """
    Returns a StructuredTool that translates a natural language question
    into SQL, executes it against PostgreSQL, and returns the result.
    Scoped exclusively to rag_app_company and rag_app_quarterlyfinancials.
    """
    from rag_app.utils.llm_factory import get_llm

    db = SQLDatabase.from_uri(
        _build_db_url(),
        include_tables=["rag_app_company", "rag_app_quarterlyfinancials"],
        sample_rows_in_table_info=2,
    )

    # Get table schema once at startup — pass it explicitly in every prompt
    # so Gemini never has to guess column names
    table_info = db.get_table_info()
    llm = get_llm(temperature=0.0)

    def run_sql_query(query: str) -> str:
        """Converts NL question to SQL, runs it, returns results."""
        try:
            # Ask Gemini to write the SQL using the exact schema we provide.
            # We structure this as a plain invoke() — no chain, full control.
            sql_prompt = f"""You are a PostgreSQL expert. Given the table schemas below, \
write a single valid PostgreSQL SELECT query to answer the question.

RULES:
- Output ONLY the raw SQL query. No markdown, no backticks, no explanation.
- Use only the tables and columns defined in the schema below.
- Always use table aliases for clarity.
- For financial figures, use the exact column names from the schema.
- Use ILIKE for company name matching (case-insensitive).

TABLE SCHEMA:
{table_info}

QUESTION: {query}

SQL QUERY:"""

            response = llm.invoke(sql_prompt)

            # Extract text from Gemini's response (handles both string and block formats)
            raw_sql = _extract_text(response.content)

            # Strip any accidental markdown fences Gemini might add
            clean_sql = (
                raw_sql.strip()
                .removeprefix("```sql").removeprefix("```postgresql").removeprefix("```")
                .removesuffix("```")
                .strip()
            )

            logger.info(f"[SQL Tool] Generated SQL: {clean_sql}")

            if not clean_sql.upper().startswith("SELECT"):
                return f"Generated query was not a SELECT statement. Got: {clean_sql[:100]}"

            result = db.run(clean_sql)
            logger.info(f"[SQL Tool] Result: {str(result)[:200]}")
            return result if result else "Query returned no results."

        except Exception as e:
            logger.exception("[SQL Tool] Error executing query")
            return f"SQL tool error: {str(e)}"

    return StructuredTool.from_function(
        func=run_sql_query,
        name="financial_database_query",
        description=(
            "Use this tool to answer questions about hard financial metrics: revenue, "
            "net income, operating expenses, debt-to-equity ratios, market capitalisation, "
            "and company-specific quantitative data. "
            "Examples: 'What was ATHR revenue in Q2 2025?', "
            "'Which company has the highest D/E ratio?', "
            "'Show GRHE net income across all quarters.'"
        ),
        args_schema=SQLQueryInput,
    )


def _extract_text(content) -> str:
    """
    Safely extracts plain text from Gemini's response content.
    Handles: plain string, list of content blocks, or single block dict.
    """
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
            elif isinstance(block, str):
                parts.append(block)
        return " ".join(parts)
    if isinstance(content, dict) and content.get("type") == "text":
        return content.get("text", "")
    return str(content)