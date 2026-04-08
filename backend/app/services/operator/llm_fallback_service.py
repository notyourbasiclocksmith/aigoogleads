"""
Unified LLM call interface with automatic fallback from Claude to GPT-4o.

Prevents total pipeline failure during Anthropic outages by transparently
routing to OpenAI when the primary Claude API is unavailable.
"""

from __future__ import annotations

import json
import re
from typing import Any, Optional

import anthropic
import openai
import structlog

from app.core.config import settings

logger = structlog.get_logger(__name__)

# Maps Claude models to cost-appropriate OpenAI fallbacks
_FALLBACK_MODEL_MAP: dict[str, str] = {
    "claude-opus-4-6": "gpt-4o",
    "claude-opus-4-20250620": "gpt-4o",
    "claude-sonnet-4-20250514": "gpt-4o-mini",
}

# Anthropic status codes that warrant a fallback
_RETRIABLE_STATUS_CODES = {500, 502, 503, 529}

_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*\n?(.*?)\n?\s*```", re.DOTALL)


def _strip_json_fences(text: str) -> str:
    """Remove markdown code fences wrapping JSON."""
    match = _JSON_FENCE_RE.search(text)
    if match:
        return match.group(1).strip()
    return text.strip()


def _repair_truncated_json(text: str) -> str:
    """Attempt to repair JSON truncated by max_tokens by closing open brackets."""
    # Count unclosed braces and brackets
    open_braces = 0
    open_brackets = 0
    in_string = False
    escape_next = False

    for ch in text:
        if escape_next:
            escape_next = False
            continue
        if ch == "\\":
            escape_next = True
            continue
        if ch == '"' and not escape_next:
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == "{":
            open_braces += 1
        elif ch == "}":
            open_braces -= 1
        elif ch == "[":
            open_brackets += 1
        elif ch == "]":
            open_brackets -= 1

    # Strip trailing incomplete value (after last comma or colon)
    stripped = text.rstrip()
    # Remove trailing comma if present
    if stripped.endswith(","):
        stripped = stripped[:-1]
    # If it ends mid-string, close the string
    if in_string:
        stripped += '"'
    # If it ends mid-key-value, remove the partial entry
    if stripped.endswith(":"):
        stripped = stripped[:stripped.rfind(",")]
    # Close brackets/braces
    stripped += "]" * max(open_brackets, 0)
    stripped += "}" * max(open_braces, 0)
    return stripped


def _parse_json(raw: str) -> Any:
    """Parse JSON from raw LLM output, stripping fences and preamble if present."""
    cleaned = _strip_json_fences(raw)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass
    # Fallback: find the first { or [ and try to parse from there
    for i, ch in enumerate(cleaned):
        if ch in "{[":
            try:
                return json.loads(cleaned[i:])
            except json.JSONDecodeError:
                # Try repairing truncated JSON
                try:
                    repaired = _repair_truncated_json(cleaned[i:])
                    return json.loads(repaired)
                except json.JSONDecodeError:
                    continue
    # Nothing worked — raise so caller can handle
    raise json.JSONDecodeError("No valid JSON found in response", raw, 0)


class LLMFallbackService:
    """Calls Claude first, falls back to OpenAI on failure.

    Retry logic: 2 attempts on Claude, then 2 attempts on GPT-4o.
    Returns a dict with ``data``, ``model_used``, and ``fallback`` keys,
    or ``None`` if both providers fail.
    """

    def __init__(self) -> None:
        self._anthropic = anthropic.AsyncAnthropic(
            api_key=settings.ANTHROPIC_API_KEY,
        )
        self._openai = openai.AsyncOpenAI(
            api_key=settings.OPENAI_API_KEY,
        )
        self._fallback_count: int = 0
        self._total_count: int = 0

    # --------------------------------------------------------------------- #
    # Public API
    # --------------------------------------------------------------------- #

    async def call_json(
        self,
        system: str,
        user_msg: str,
        max_tokens: int = 4096,
        temperature: float = 0.2,
        preferred_model: str | None = None,
    ) -> Optional[dict[str, Any]]:
        """Request structured JSON from an LLM with automatic fallback.

        Returns::

            {
                "data": <parsed JSON object>,
                "model_used": "claude-opus-4-6" | "gpt-4o" | ...,
                "fallback": False | True,
            }

        Returns ``None`` only when **both** providers fail after retries.
        """
        self._total_count += 1
        claude_model = preferred_model or settings.ANTHROPIC_MODEL
        openai_model = _FALLBACK_MODEL_MAP.get(claude_model, "gpt-4o")

        # --- Attempt Claude (up to 2 tries) ---
        result = await self._try_claude(
            system=system,
            user_msg=user_msg,
            model=claude_model,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        if result is not None:
            return {"data": result, "model_used": claude_model, "fallback": False}

        # --- Fallback to OpenAI (up to 2 tries) ---
        self._fallback_count += 1
        logger.warning(
            "llm_fallback_triggered",
            preferred_model=claude_model,
            fallback_model=openai_model,
            fallback_count=self._fallback_count,
            total_count=self._total_count,
            fallback_rate=round(self._fallback_count / self._total_count, 4),
        )

        result = await self._try_openai(
            system=system,
            user_msg=user_msg,
            model=openai_model,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        if result is not None:
            return {"data": result, "model_used": openai_model, "fallback": True}

        logger.error(
            "llm_both_providers_failed",
            claude_model=claude_model,
            openai_model=openai_model,
        )
        return None

    @property
    def fallback_rate(self) -> float:
        """Fraction of calls that fell back to OpenAI."""
        if self._total_count == 0:
            return 0.0
        return self._fallback_count / self._total_count

    # --------------------------------------------------------------------- #
    # Internal helpers
    # --------------------------------------------------------------------- #

    async def _try_claude(
        self,
        system: str,
        user_msg: str,
        model: str,
        max_tokens: int,
        temperature: float,
    ) -> Any | None:
        """Try Claude up to 2 times. Returns parsed JSON or None."""
        last_error: Exception | None = None

        for attempt in range(2):
            raw = ""
            try:
                response = await self._anthropic.messages.create(
                    model=model,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    system=system,
                    messages=[{"role": "user", "content": user_msg}],
                )
                # Guard against empty / missing content blocks
                if not response.content:
                    logger.warning(
                        "claude_empty_content",
                        model=model,
                        attempt=attempt + 1,
                        stop_reason=getattr(response, "stop_reason", None),
                        usage=str(getattr(response, "usage", None)),
                    )
                    continue
                raw = response.content[0].text
                if not raw or not raw.strip():
                    logger.warning(
                        "claude_empty_text",
                        model=model,
                        attempt=attempt + 1,
                        stop_reason=getattr(response, "stop_reason", None),
                        content_type=type(response.content[0]).__name__,
                    )
                    continue
                return _parse_json(raw)

            except (json.JSONDecodeError, IndexError, KeyError) as exc:
                # JSON parse / extraction error — retry once on same model
                last_error = exc
                # Log first 500 chars of raw response for debugging
                raw_preview = raw[:500] if raw else "(empty)"
                logger.warning(
                    "claude_json_parse_error",
                    model=model,
                    attempt=attempt + 1,
                    error=str(exc),
                    raw_preview=raw_preview,
                    raw_length=len(raw) if raw else 0,
                    stop_reason=getattr(response, "stop_reason", None),
                )
                continue

            except anthropic.RateLimitError as exc:
                logger.warning("claude_rate_limited", model=model, attempt=attempt + 1)
                last_error = exc
                break  # don't retry rate limits, go straight to fallback

            except anthropic.APIStatusError as exc:
                last_error = exc
                if exc.status_code in _RETRIABLE_STATUS_CODES:
                    logger.warning(
                        "claude_api_status_error",
                        model=model,
                        status=exc.status_code,
                        attempt=attempt + 1,
                    )
                    continue
                # Non-retriable status (e.g. 401 auth) — break immediately
                logger.error(
                    "claude_api_non_retriable",
                    model=model,
                    status=exc.status_code,
                )
                break

            except anthropic.APIConnectionError as exc:
                last_error = exc
                logger.warning(
                    "claude_connection_error",
                    model=model,
                    attempt=attempt + 1,
                    error=str(exc),
                )
                continue

            except Exception as exc:
                last_error = exc
                logger.error(
                    "claude_unexpected_error",
                    model=model,
                    attempt=attempt + 1,
                    error=str(exc),
                )
                break

        logger.warning(
            "claude_attempts_exhausted",
            model=model,
            last_error=str(last_error),
        )
        return None

    async def _try_openai(
        self,
        system: str,
        user_msg: str,
        model: str,
        max_tokens: int,
        temperature: float,
    ) -> Any | None:
        """Try OpenAI up to 2 times. Returns parsed JSON or None."""
        last_error: Exception | None = None

        for attempt in range(2):
            try:
                response = await self._openai.chat.completions.create(
                    model=model,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    response_format={"type": "json_object"},
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": user_msg},
                    ],
                )
                raw = response.choices[0].message.content
                if raw is None:
                    logger.warning(
                        "openai_null_content",
                        model=model,
                        attempt=attempt + 1,
                    )
                    continue
                return json.loads(raw)

            except (json.JSONDecodeError, IndexError, KeyError) as exc:
                last_error = exc
                logger.warning(
                    "openai_json_parse_error",
                    model=model,
                    attempt=attempt + 1,
                    error=str(exc),
                )
                continue

            except openai.RateLimitError as exc:
                last_error = exc
                logger.warning("openai_rate_limited", model=model, attempt=attempt + 1)
                break

            except openai.APIStatusError as exc:
                last_error = exc
                logger.warning(
                    "openai_api_status_error",
                    model=model,
                    status=exc.status_code,
                    attempt=attempt + 1,
                )
                continue

            except openai.APIConnectionError as exc:
                last_error = exc
                logger.warning(
                    "openai_connection_error",
                    model=model,
                    attempt=attempt + 1,
                    error=str(exc),
                )
                continue

            except Exception as exc:
                last_error = exc
                logger.error(
                    "openai_unexpected_error",
                    model=model,
                    attempt=attempt + 1,
                    error=str(exc),
                )
                break

        logger.error(
            "openai_attempts_exhausted",
            model=model,
            last_error=str(last_error),
        )
        return None
