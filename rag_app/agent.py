import os
import logging
from typing import Dict, List
from dotenv import load_dotenv

from langchain_classic.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage

load_dotenv()
logger = logging.getLogger(__name__)

_SESSION_STORE: Dict[str, List[BaseMessage]] = {}
MAX_HISTORY_TURNS = 10

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
- Cross-reference questions (e.g. eligibility checks) → use BOTH tools, then synthesise
- Always cite which tool provided which piece of information
- If a tool returns no results, say so explicitly — never hallucinate data
- Format financial figures clearly: "USD 4.75B", "D/E ratio of 0.35"
- When referencing regulatory documents, always mention the source name
"""


def _extract_text(content) -> str:
    """
    Safely extracts a plain string from Gemini 2.5's response content.

    Gemini 2.5 Flash/Pro can return content in three formats:
      1. Plain string  →  "The revenue was USD 4.75B"
      2. List of blocks → [{'type': 'text', 'text': '...', 'extras': {...}}]
      3. Single block   → {'type': 'text', 'text': '...'}

    This function normalises all three into a plain string.
    """
    if isinstance(content, str):
        return content

    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict):
                if block.get("type") == "text":
                    parts.append(block.get("text", ""))
            elif isinstance(block, str):
                parts.append(block)
        return " ".join(p for p in parts if p).strip()

    if isinstance(content, dict) and content.get("type") == "text":
        return content.get("text", "").strip()

    # Last resort — convert whatever it is to a string
    return str(content)


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
        # Still no handle_parsing_errors — we want real errors in logs
    )

    logger.info("[Agent] AgentExecutor initialised successfully.")
    return executor


_EXECUTOR: AgentExecutor = _build_agent_executor()


def get_session_history(session_id: str) -> List[BaseMessage]:
    return _SESSION_STORE.get(session_id, [])


def clear_session(session_id: str) -> None:
    _SESSION_STORE.pop(session_id, None)
    logger.info(f"[Agent] Cleared session: {session_id}")


def run_agent(question: str, session_id: str = "default") -> dict:
    history = get_session_history(session_id)

    try:
        result = _EXECUTOR.invoke({
            "input":        question,
            "chat_history": history,
        })

        raw_output = result.get("output", "")
        logger.info(f"[Agent] Raw output type: {type(raw_output)}")
        logger.info(f"[Agent] Raw output repr: {repr(raw_output)[:300]}")

        # Normalise Gemini 2.5's content blocks into a plain string
        answer = _extract_text(raw_output)

        if not answer.strip():
            answer = (
                "The agent completed but returned an empty response. "
                "Check server logs for details."
            )

        # Extract tool call trace
        tool_calls = []
        for step in result.get("intermediate_steps", []):
            action, _ = step
            tool_calls.append({
                "tool":  getattr(action, "tool", "unknown"),
                "input": getattr(action, "tool_input", {}),
            })

        # Store clean plain-text answer in memory — never the raw block dict.
        # Storing the raw block as AIMessage.content poisons the next turn
        # because Gemini receives `str({'type': 'text', ...})` as context.
        history.append(HumanMessage(content=question))
        history.append(AIMessage(content=answer))
        _SESSION_STORE[session_id] = history[-(MAX_HISTORY_TURNS * 2):]

        return {
            "answer":         answer,
            "session_id":     session_id,
            "tool_calls":     tool_calls,
            "history_length": len(_SESSION_STORE[session_id]),
        }

    except Exception as e:
        logger.exception(f"[Agent] Exception in run_agent for session '{session_id}'")
        return {
            "answer":         f"Agent error: {str(e)}",
            "session_id":     session_id,
            "tool_calls":     [],
            "history_length": len(history),
        }