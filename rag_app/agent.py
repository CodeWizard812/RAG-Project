# rag_app/agent.py

import os
import logging
from typing import Optional
from dotenv import load_dotenv

from langchain_classic.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage

load_dotenv()
logger = logging.getLogger(__name__)

# ── Session memory TTL ────────────────────────────────────────────────────────
# Sessions expire from Redis after this many seconds of inactivity.
# 86400 = 24 hours. Prevents unbounded memory growth in production.
SESSION_TTL_SECONDS = int(os.getenv("SESSION_TTL_SECONDS", 86400))
MAX_HISTORY_TURNS   = int(os.getenv("MAX_HISTORY_TURNS", 10))

SYSTEM_PROMPT = """You are a Financial and Regulatory Intelligence Agent specialising \
in cross-referencing quantitative financial data with qualitative regulatory guidelines.

You have access to two tools:

1. financial_database_query — Use this for hard numbers: revenue, net income, \
operating expenses, debt-to-equity ratios, market capitalisation, and trends. \
Always query the database before stating any financial figure.

2. regulatory_knowledge_search — Use this for regulatory rules (SEBI guidelines, \
disclosure requirements, ESG mandates) and qualitative insights from earnings \
transcripts (strategic pivots, management commentary, forward guidance).

REASONING RULES:
- Quantitative questions only → financial_database_query
- Qualitative or regulatory questions only → regulatory_knowledge_search
- Cross-reference questions → use BOTH tools, then synthesise a unified answer
- Always cite which tool provided which piece of information
- If a tool returns no results, say so explicitly — never hallucinate data
- Format financial figures clearly: "USD 4.75B", "D/E ratio of 0.35"
- When referencing regulatory documents, always mention the source name
"""


# ── Memory backend factory ─────────────────────────────────────────────────────

def _get_memory_history(session_id: str):
    """
    Returns the appropriate chat history backend based on USE_REDIS setting.

    Redis backend  → sessions persist across server restarts, work across
                     multiple Django workers, expire automatically via TTL.

    Fallback       → in-process list, resets on restart, single-worker only.
                     Used when USE_REDIS=false (local dev without Redis).
    """
    use_redis = os.getenv("USE_REDIS", "true").lower() == "true"

    if use_redis:
        try:
            from langchain_community.chat_message_histories import RedisChatMessageHistory
            redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
            return RedisChatMessageHistory(
                session_id=session_id,
                url=redis_url,
                ttl=SESSION_TTL_SECONDS,
                key_prefix="rag_agent:session:",
            )
        except Exception as e:
            logger.warning(
                f"[Agent] Redis unavailable ({e}) — falling back to in-memory history."
            )

    # In-memory fallback
    return _InMemoryHistory(session_id)


class _InMemoryHistory:
    """
    Minimal in-memory chat history that matches the RedisChatMessageHistory
    interface so the rest of agent.py works identically regardless of backend.
    """
    _store: dict = {}

    def __init__(self, session_id: str):
        self.session_id = session_id
        if session_id not in _InMemoryHistory._store:
            _InMemoryHistory._store[session_id] = []

    @property
    def messages(self):
        return _InMemoryHistory._store[self.session_id]

    def add_user_message(self, content: str):
        _InMemoryHistory._store[self.session_id].append(
            HumanMessage(content=content)
        )
        self._trim()

    def add_ai_message(self, content: str):
        _InMemoryHistory._store[self.session_id].append(
            AIMessage(content=content)
        )
        self._trim()

    def clear(self):
        _InMemoryHistory._store[self.session_id] = []

    def _trim(self):
        """Keep only the last MAX_HISTORY_TURNS * 2 messages."""
        store = _InMemoryHistory._store[self.session_id]
        if len(store) > MAX_HISTORY_TURNS * 2:
            _InMemoryHistory._store[self.session_id] = store[-(MAX_HISTORY_TURNS * 2):]


# ── Text extraction ────────────────────────────────────────────────────────────

def _extract_text(content) -> str:
    """Normalises Gemini 2.5's response into a plain string."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
            elif isinstance(block, str):
                parts.append(block)
        return " ".join(p for p in parts if p).strip()
    if isinstance(content, dict) and content.get("type") == "text":
        return content.get("text", "").strip()
    return str(content)


# ── Agent executor (lazy singleton) ───────────────────────────────────────────

_EXECUTOR: Optional[AgentExecutor] = None


def _build_agent_executor() -> AgentExecutor:
    from rag_app.utils.llm_factory import get_llm
    from rag_app.tools.sql_tool import get_sql_tool
    from rag_app.tools.vector_tool import get_vector_tool

    llm   = get_llm(temperature=0.0)
    tools = [get_sql_tool(), get_vector_tool()]

    prompt = ChatPromptTemplate.from_messages([
        ("system", SYSTEM_PROMPT),
        MessagesPlaceholder(variable_name="chat_history", optional=True),
        ("human", "{input}"),
        MessagesPlaceholder(variable_name="agent_scratchpad"),
    ])

    agent = create_tool_calling_agent(llm=llm, tools=tools, prompt=prompt)

    executor = AgentExecutor(
        agent=agent,
        tools=tools,
        verbose=True,
        max_iterations=6,
        return_intermediate_steps=True,
    )

    logger.info("[Agent] AgentExecutor initialised successfully.")
    return executor


def _get_executor() -> AgentExecutor:
    global _EXECUTOR
    if _EXECUTOR is None:
        logger.info("[Agent] First request — building AgentExecutor (lazy init)...")
        _EXECUTOR = _build_agent_executor()
    return _EXECUTOR


# ── Public API ─────────────────────────────────────────────────────────────────

def get_session_history(session_id: str) -> list[BaseMessage]:
    """Returns the current message list for a session."""
    history = _get_memory_history(session_id)
    return history.messages


def clear_session(session_id: str) -> None:
    """Clears all messages for a given session from the memory backend."""
    history = _get_memory_history(session_id)
    history.clear()
    logger.info(f"[Agent] Cleared session: {session_id}")


def run_agent(question: str, session_id: str = "default") -> dict:
    """
    Runs the agent for a given question and session.

    Memory is loaded from and saved to the configured backend (Redis or
    in-memory) so context persists across requests and server restarts.

    Args:
        question:   Natural language question from the user.
        session_id: Conversation thread identifier. Scope this to the
                    authenticated user in views.py to prevent bleed.

    Returns:
        dict with keys: answer, session_id, tool_calls, history_length,
                        contexts (list of retrieved document snippets for RAGAS).
    """
    executor = _get_executor()
    memory   = _get_memory_history(session_id)
    history  = memory.messages

    try:
        result = executor.invoke({
            "input":        question,
            "chat_history": history,
        })

        raw_output = result.get("output", "")
        answer     = _extract_text(raw_output)

        if not answer.strip():
            answer = (
                "The agent completed but returned an empty response. "
                "Check server logs for details."
            )

        # Extract tool calls and retrieved contexts
        # Contexts are the raw tool outputs — used by RAGAS for faithfulness scoring
        tool_calls = []
        contexts   = []

        for step in result.get("intermediate_steps", []):
            action, tool_output = step
            tool_calls.append({
                "tool":  getattr(action, "tool", "unknown"),
                "input": getattr(action, "tool_input", {}),
            })
            # Collect non-empty tool outputs as retrieved contexts
            if isinstance(tool_output, str) and tool_output.strip():
                contexts.append(tool_output)

        # Persist this turn to memory backend
        memory.add_user_message(question)
        memory.add_ai_message(answer)

        return {
            "answer":         answer,
            "session_id":     session_id,
            "tool_calls":     tool_calls,
            "history_length": len(memory.messages),
            "contexts":       contexts,   # raw retrieved chunks — used by RAGAS
        }

    except Exception as e:
        logger.exception(f"[Agent] Exception in run_agent for session '{session_id}'")
        return {
            "answer":         f"Agent error: {str(e)}",
            "session_id":     session_id,
            "tool_calls":     [],
            "history_length": len(history),
            "contexts":       [],
        }