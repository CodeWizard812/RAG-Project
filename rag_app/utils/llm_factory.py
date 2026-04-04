import os
import time
import logging
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI

from langchain_core.runnables import Runnable

load_dotenv()
logger = logging.getLogger(__name__)

MODEL_REGISTRY = {
    "gemini-2.5-flash": "gemini-2.5-flash",
    "gemini-2.5-pro":   "gemini-2.5-pro",
}

MAX_RETRIES = 8   # try up to 8 times across the key pool before giving up


def _is_rate_limit_error(e: Exception) -> bool:
    """Returns True if the exception is a 429 / quota-exceeded error."""
    msg = str(e).lower()
    return any(x in msg for x in [
        "429",
        "resource_exhausted",
        "quota exceeded",
        "rate limit",
        "too many requests",
        "resourceexhausted",
    ])


def _is_daily_limit_error(e: Exception) -> bool:
    """Returns True if the 429 is specifically a daily quota exhaustion."""
    msg = str(e).lower()
    return any(x in msg for x in [
        "daily",
        "per day",
        "quota_exceeded",
        "free tier",
    ])


def _build_llm(api_key: str, model_id: str, temperature: float) -> ChatGoogleGenerativeAI:
    return ChatGoogleGenerativeAI(
        model=model_id,
        google_api_key=api_key,
        temperature=temperature,
        convert_system_message_to_human=True,
    )


def get_llm(temperature: float = 0.0) -> "RotatingLLM":
    """
    Returns a RotatingLLM wrapper that automatically cycles through
    API keys on 429 errors.

    Drop-in replacement for the old get_llm() — same interface,
    same return type as far as LangChain is concerned.
    """
    model_key = os.getenv("LLM_MODEL_TYPE", "gemini-2.5-flash").strip().lower()
    model_id  = MODEL_REGISTRY.get(model_key, MODEL_REGISTRY["gemini-2.5-flash"])
    logger.info(f"[LLM Factory] Model: {model_id}")
    return RotatingLLM(model_id=model_id, temperature=temperature)


class RotatingLLM(Runnable):
    """
    A thin wrapper around ChatGoogleGenerativeAI that intercepts 429 errors
    and retries with the next available key from GeminiKeyPool.

    Implements the LangChain Runnable interface (invoke, stream, batch)
    so it works as a drop-in anywhere an LLM is expected.
    """

    def __init__(self, model_id: str, temperature: float):
        self.model_id    = model_id
        self.temperature = temperature

    def _run_with_rotation(self, fn_name: str, *args, **kwargs):
        """
        Core retry loop. Calls fn_name on a fresh LLM instance using
        successive keys until success or MAX_RETRIES exhausted.
        """
        from rag_app.utils.key_pool import get_key_pool, AllKeysExhaustedError

        pool = get_key_pool()
        last_error: Exception | None = None

        for attempt in range(1, MAX_RETRIES + 1):
            key = pool.get_available_key()
            llm = _build_llm(key, self.model_id, self.temperature)

            try:
                result = getattr(llm, fn_name)(*args, **kwargs)
                pool.mark_success(key)
                if attempt > 1:
                    logger.info(
                        f"[RotatingLLM] Succeeded on attempt {attempt} "
                        f"using key ...{key[-6:]}"
                    )
                return result

            except AllKeysExhaustedError:
                raise

            except Exception as e:
                if _is_rate_limit_error(e):
                    daily = _is_daily_limit_error(e)
                    pool.mark_exhausted(key, daily=daily)
                    last_error = e
                    logger.warning(
                        f"[RotatingLLM] Attempt {attempt}/{MAX_RETRIES} — "
                        f"429 on key ...{key[-6:]}. Rotating..."
                    )
                    # Brief pause before retry so we don't hammer the API
                    time.sleep(0.5)
                    continue
                else:
                    # Non-rate-limit error — don't retry
                    raise

        raise RuntimeError(
            f"All {MAX_RETRIES} attempts failed. Last error: {last_error}"
        )

    # ── LangChain Runnable interface ─────────────────────────────────────────

    def invoke(self, *args, **kwargs):
        return self._run_with_rotation("invoke", *args, **kwargs)

    def stream(self, *args, **kwargs):
        """
        Streaming is harder to retry mid-stream, so we collect the full
        response first then re-yield it. Acceptable tradeoff for free tier.
        """
        return self._run_with_rotation("invoke", *args, **kwargs)

    def batch(self, *args, **kwargs):
        return self._run_with_rotation("batch", *args, **kwargs)

    def bind_tools(self, *args, **kwargs):
        """
        LangChain agents call bind_tools() to attach tool schemas to the LLM.
        We delegate to a real LLM instance but keep rotation on invoke.
        """
        from rag_app.utils.key_pool import get_key_pool
        pool = get_key_pool()
        key  = pool.get_available_key()
        llm  = _build_llm(key, self.model_id, self.temperature)
        bound = llm.bind_tools(*args, **kwargs)
        # Wrap the bound LLM so invoke() still rotates
        return _BoundRotatingLLM(bound, self)

    # Needed by LangChain internals
    @property
    def _llm_type(self):
        return "rotating_gemini"


class _BoundRotatingLLM(Runnable):
    """
    Returned by RotatingLLM.bind_tools(). Holds a bound LLM for the tool
    schema but delegates invoke() back to the parent RotatingLLM so
    key rotation still works during agent tool-calling loops.
    """
    def __init__(self, bound_llm, parent: RotatingLLM):
        self._bound  = bound_llm
        self._parent = parent

    def invoke(self, input, config=None, **kwargs):
        from rag_app.utils.key_pool import get_key_pool, AllKeysExhaustedError
        import time
        pool = get_key_pool()
        last_err = None

        for attempt in range(1, MAX_RETRIES + 1):
            key = pool.get_available_key()
            llm = _build_llm(key, self._parent.model_id, self._parent.temperature)

            # 1. Grab the correctly formatted tools from the original binding
            bound_kwargs = getattr(self._bound, "kwargs", {})
            
            # 2. Merge them with any new kwargs passed by the AgentExecutor
            invoke_kwargs = {**bound_kwargs, **kwargs}

            try:
                # 3. Call invoke directly with the combined kwargs
                result = llm.invoke(input, config=config, **invoke_kwargs)
                pool.mark_success(key)
                return result
                
            except AllKeysExhaustedError:
                raise
            except Exception as e:
                if _is_rate_limit_error(e):
                    pool.mark_exhausted(key, daily=_is_daily_limit_error(e))
                    last_err = e
                    time.sleep(0.5)  # Pause before retry
                    continue
                # If it's a non-rate-limit error (like a network drop), raise it
                raise

        raise RuntimeError(f"All retries exhausted. Last error: {last_err}")

    def stream(self, input, config=None, **kwargs):
        # LangChain agents sometimes call stream() instead of invoke().
        # For tool-calling loops, we yield the invoke result to maintain compatibility.
        yield self.invoke(input, config=config, **kwargs)

    # Passthrough for anything else LangChain internally accesses
    def __getattr__(self, name):
        return getattr(self._bound, name)