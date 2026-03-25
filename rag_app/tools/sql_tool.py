import os
from dotenv import load_dotenv
from langchain_community.utilities import SQLDatabase
from langchain_classic.chains import create_sql_query_chain
from langchain_core.tools import Tool

load_dotenv()


def _build_db_url() -> str:
    """Constructs the PostgreSQL connection URL from environment variables."""
    return (
        f"postgresql://{os.getenv('DB_USER', 'postgres')}:"
        f"{os.getenv('DB_PASSWORD', 'yourpassword')}@"
        f"{os.getenv('DB_HOST', 'localhost')}:"
        f"{os.getenv('DB_PORT', '5432')}/"
        f"{os.getenv('DB_NAME', 'ragdb')}"
    )


def get_sql_tool() -> Tool:
    """
    Builds and returns a LangChain Tool that translates a natural language
    question into SQL, executes it against PostgreSQL, and returns the result.

    The tool is scoped exclusively to the rag_app_company and
    rag_app_quarterlyfinancials tables to prevent unintended data access.
    """
    # Lazily import get_llm here to avoid circular imports at module load time
    from rag_app.utils.llm_factory import get_llm

    db = SQLDatabase.from_uri(
        _build_db_url(),
        include_tables=["rag_app_company", "rag_app_quarterlyfinancials"],
        sample_rows_in_table_info=2,    # Helps the LLM understand column types
    )

    llm         = get_llm(temperature=0.0)
    sql_chain   = create_sql_query_chain(llm, db)

    def run_sql_query(question: str) -> str:
        """
        Converts the natural language question to SQL, runs it, and
        returns the raw result string. Handles errors gracefully.
        """
        try:
            raw_sql = sql_chain.invoke({"question": question})

            # Gemini sometimes wraps SQL in markdown code fences — strip them
            clean_sql = (
                raw_sql
                .strip()
                .removeprefix("```sql").removeprefix("```")
                .removesuffix("```")
                .strip()
            )

            result = db.run(clean_sql)
            return result if result else "Query returned no results."

        except Exception as e:
            return f"SQL tool error: {str(e)}"

    return Tool(
        name="financial_database_query",
        func=run_sql_query,
        description=(
            "Use this tool to answer questions about hard financial metrics, revenue, debt, "
            "and company-specific quantitative data. Input should be a natural language question. "
            "Examples: 'What was ATHR revenue in Q2 2025?', "
            "'Which company has the highest debt-to-equity ratio?', "
            "'Show net income trend for GRHE across all quarters.'"
        ),
    )