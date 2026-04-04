import os
import time
import logging
import threading
from typing import Optional

logger = logging.getLogger(__name__)


class GeminiKeyPool:
    """
    Thread-safe rotating pool of Gemini API keys.

    Behaviour:
    - Loads all GEMINI_API_KEY_N keys from environment on startup.
    - Tracks which keys are exhausted and when they reset.
    - On 429: marks the current key exhausted, immediately retries
      with the next available key.
    - If ALL keys are exhausted: waits until the soonest reset time
      rather than raising immediately.
    - Reset window: 60 seconds (conservative — actual RPM window is 60s,
      daily limit resets at midnight Pacific but we can't predict that).
    - Thread-safe: safe to use across Django request threads simultaneously.

    Usage:
        pool = GeminiKeyPool()          # singleton via get_key_pool()
        key  = pool.get_available_key() # blocks if all exhausted
        pool.mark_exhausted(key)        # call on 429
        pool.mark_success(key)          # call on 200 (optional, for logging)
    """

    # How long to consider a key exhausted after a 429 (seconds).
    # 60s covers the per-minute quota window.
    # Keys exhausted by daily limit will keep failing — the pool will
    # cycle through all keys and then raise AllKeysExhaustedError.
    COOLDOWN_SECONDS = 62

    def __init__(self):
        self._lock       = threading.Lock()
        self._keys       = self._load_keys()
        self._exhausted  = {}   # key -> reset_at (unix timestamp)
        self._usage      = {k: 0 for k in self._keys}  # successful calls per key
        self._current_idx = 0

        if not self._keys:
            raise EnvironmentError(
                "No Gemini API keys found. Set GEMINI_API_KEY_1, "
                "GEMINI_API_KEY_2, ... in your .env file."
            )

        logger.info(f"[KeyPool] Initialised with {len(self._keys)} key(s).")

    def _load_keys(self) -> list[str]:
        """
        Loads keys in order: GEMINI_API_KEY_1, _2, _3 ... up to _20.
        Falls back to GEMINI_API_KEY if no numbered keys are found.
        Skips blank or placeholder values.
        """
        keys = []
        for i in range(1, 21):
            val = os.getenv(f"GEMINI_API_KEY_{i}", "").strip()
            if val and not val.startswith("your_") and len(val) > 10:
                keys.append(val)

        if not keys:
            # Fallback — single key mode
            fallback = os.getenv("GEMINI_API_KEY", "").strip()
            if fallback and len(fallback) > 10:
                keys.append(fallback)
                logger.warning(
                    "[KeyPool] Only one key found (GEMINI_API_KEY). "
                    "Add GEMINI_API_KEY_1, _2, etc. for rotation."
                )

        return keys

    def get_available_key(self, timeout: float = 120.0) -> str:
        """
        Returns the next available (non-exhausted) API key.
        Rotates through keys in round-robin order.

        If all keys are currently exhausted, waits up to `timeout` seconds
        for the soonest one to reset before raising.

        Raises:
            AllKeysExhaustedError: if no key becomes available within timeout.
        """
        deadline = time.monotonic() + timeout

        while time.monotonic() < deadline:
            with self._lock:
                now = time.time()

                # Un-exhaust any keys whose cooldown has expired
                for key, reset_at in list(self._exhausted.items()):
                    if now >= reset_at:
                        del self._exhausted[key]
                        logger.info(
                            f"[KeyPool] Key ...{key[-6:]} cooldown expired — back in rotation."
                        )

                # Try each key starting from current index
                for _ in range(len(self._keys)):
                    candidate = self._keys[self._current_idx % len(self._keys)]
                    self._current_idx += 1

                    if candidate not in self._exhausted:
                        return candidate

                # All keys exhausted — calculate wait time
                soonest_reset = min(self._exhausted.values())
                wait = max(0.1, soonest_reset - time.time())

            logger.warning(
                f"[KeyPool] All {len(self._keys)} key(s) exhausted. "
                f"Waiting {wait:.1f}s for next reset..."
            )
            time.sleep(min(wait, 5.0))  # check every 5s max

        raise AllKeysExhaustedError(
            f"All {len(self._keys)} Gemini API key(s) are exhausted and "
            f"none recovered within {timeout}s. "
            f"Add more API keys via GEMINI_API_KEY_3, _4 etc. in .env"
        )

    def mark_exhausted(self, key: str, daily: bool = False) -> None:
        """
        Marks a key as exhausted after a 429 response.

        Args:
            key:   The API key string that received the 429.
            daily: If True, sets a longer cooldown (12h) because the daily
                   quota is hit — not just the per-minute limit.
        """
        cooldown = 43200 if daily else self.COOLDOWN_SECONDS
        with self._lock:
            reset_at = time.time() + cooldown
            self._exhausted[key] = reset_at
            remaining = [k for k in self._keys if k not in self._exhausted]
            logger.warning(
                f"[KeyPool] Key ...{key[-6:]} exhausted "
                f"({'daily' if daily else 'per-minute'} limit). "
                f"Resets in {cooldown}s. "
                f"{len(remaining)}/{len(self._keys)} key(s) remaining."
            )

    def mark_success(self, key: str) -> None:
        """Records a successful call for diagnostics."""
        with self._lock:
            self._usage[key] = self._usage.get(key, 0) + 1

    def status(self) -> dict:
        """Returns pool health — exposed via /api/health/ endpoint."""
        with self._lock:
            now = time.time()
            return {
                "total_keys":     len(self._keys),
                "available_keys": sum(
                    1 for k in self._keys if k not in self._exhausted
                ),
                "exhausted_keys": [
                    {
                        "suffix":     f"...{k[-6:]}",
                        "resets_in":  max(0, round(v - now)),
                    }
                    for k, v in self._exhausted.items()
                ],
                "usage_counts": {
                    f"...{k[-6:]}": v for k, v in self._usage.items()
                },
            }


class AllKeysExhaustedError(Exception):
    """Raised when every key in the pool is exhausted and timeout expires."""
    pass


# ── Singleton ──────────────────────────────────────────────────────────────────
# One pool instance shared across all threads / Django workers.

_pool: Optional[GeminiKeyPool] = None
_pool_lock = threading.Lock()


def get_key_pool() -> GeminiKeyPool:
    global _pool
    if _pool is None:
        with _pool_lock:
            if _pool is None:
                _pool = GeminiKeyPool()
    return _pool