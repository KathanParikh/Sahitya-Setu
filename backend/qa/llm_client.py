"""Provider-agnostic LLM access.

Everything above this module calls `generate()` and never imports a vendor
SDK, so switching the whole system between Gemini and Groq is one line in
config.py. Both providers are on free tiers with tight per-minute limits, so
only transient errors (429/5xx/network) are retried, waiting as long as the
provider asks, and there is an optional cross-provider fallback.
"""
from __future__ import annotations

import json
import logging
import random
import re
import time
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

import config

logger = logging.getLogger(__name__)


class LLMError(RuntimeError):
    """Raised when a provider fails after all retries."""


# ------------------------------------------------------------ base class ----
class BaseLLM(ABC):
    name: str = "base"
    model: str = ""

    @abstractmethod
    def _complete(self, prompt: str, system: Optional[str], temperature: float) -> str:
        ...

    def generate(
        self,
        prompt: str,
        system: Optional[str] = None,
        temperature: Optional[float] = None,
        max_retries: Optional[int] = None,
    ) -> str:
        temperature = config.LLM_TEMPERATURE if temperature is None else temperature
        max_retries = config.LLM_MAX_RETRIES if max_retries is None else max_retries

        last_error: Optional[Exception] = None
        for attempt in range(max_retries):
            try:
                text = self._complete(prompt, system, temperature)
                if text and text.strip():
                    return text.strip()
                last_error = LLMError("provider returned an empty response")
            except Exception as exc:
                last_error = exc
                logger.warning("%s attempt %d/%d failed: %s",
                               self.name, attempt + 1, max_retries, _short(exc))
                if not is_transient(exc):
                    # Bad key, unknown model, malformed request: retrying
                    # only spends quota on the same answer.
                    raise LLMError(f"{self.name} failed: {exc}") from exc
            if attempt == max_retries - 1:
                break
            delay = retry_delay(last_error, attempt)
            if delay is None:
                raise LLMError(f"{self.name} quota exhausted, not retrying: "
                               f"{_short(last_error)}") from last_error
            logger.info("%s retrying in %.1fs", self.name, delay)
            time.sleep(delay)
        raise LLMError(f"{self.name} failed after {max_retries} attempts: {last_error}")

    def generate_json(
        self,
        prompt: str,
        system: Optional[str] = None,
        temperature: Optional[float] = None,
    ) -> Any:
        """Generate and parse JSON, tolerating the fences models like to add."""
        raw = self.generate(prompt, system=system, temperature=temperature)
        return parse_json_response(raw)


# ---------------------------------------------------------- retry policy ----
# Rate limits, overload and gateway errors clear up on their own; anything
# else with a status code (400/401/403/404) will fail identically next time.
_TRANSIENT_STATUS = {408, 429, 500, 502, 503, 504}
_RETRY_IN = re.compile(r"retry in ([\d.]+)\s*s", re.IGNORECASE)


def _status(exc: Exception) -> Optional[int]:
    """HTTP status from a google-genai (`.code`) or groq (`.status_code`) error."""
    for attr in ("code", "status_code"):
        value = getattr(exc, attr, None)
        if isinstance(value, int):
            return value
    return None


def _short(exc: Exception) -> str:
    return str(exc).split("{", 1)[0].strip()[:200] or type(exc).__name__


def is_transient(exc: Exception) -> bool:
    status = _status(exc)
    if status is None:
        # No status means it never reached the API (timeout, dropped
        # connection) or the response was empty — both worth another try.
        return True
    return status in _TRANSIENT_STATUS


def _is_daily_quota(exc: Exception) -> bool:
    # Gemini names the exhausted quota, e.g. "GenerateRequestsPerDayPerProject...".
    # A daily cap will not reset within any wait worth making.
    return _status(exc) == 429 and "PerDay" in str(exc)


def provider_retry_after(exc: Exception) -> Optional[float]:
    """Seconds the provider asked us to wait, if it said."""
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", None)
    if headers is not None:
        try:
            return float(headers.get("retry-after"))
        except (TypeError, ValueError):
            pass  # absent, or the rarely used HTTP-date form

    # google.rpc.RetryInfo inside the error body: {"retryDelay": "8s"}
    details = getattr(exc, "details", None)
    error = details.get("error", details) if isinstance(details, dict) else {}
    for item in error.get("details", []) if isinstance(error, dict) else []:
        if isinstance(item, dict) and "retryDelay" in item:
            try:
                return float(str(item["retryDelay"]).rstrip("s"))
            except ValueError:
                break

    match = _RETRY_IN.search(str(exc))
    return float(match.group(1)) if match else None


def retry_delay(exc: Optional[Exception], attempt: int) -> Optional[float]:
    """How long to wait before retry `attempt + 1`, or None to stop now.

    The provider's own guidance wins; without it, back off exponentially. A
    429 without guidance waits at least RATE_LIMIT_MIN_WAIT, since free tiers
    count requests per minute and a quick retry lands in the same window.
    """
    if exc is not None and _is_daily_quota(exc):
        return None
    backoff = config.LLM_RETRY_BASE_DELAY * (2 ** attempt)
    hinted = provider_retry_after(exc) if exc is not None else None
    if hinted is not None:
        delay = max(hinted, backoff)
    elif exc is not None and _status(exc) == 429:
        delay = max(config.LLM_RATE_LIMIT_MIN_WAIT, backoff)
    else:
        delay = backoff
    if delay > config.LLM_MAX_RETRY_WAIT:
        # Better to fail over to the backup provider than stall a request.
        return None
    # Jitter so concurrent requests don't all retry on the same second.
    return delay + random.uniform(0, 1)


def parse_json_response(raw: str) -> Any:
    """Extract a JSON value from a model response.

    Models wrap JSON in ```json fences, prepend "Here is the JSON:", or both.
    """
    text = raw.strip()
    fenced = re.search(r"```(?:json)?\s*(.+?)\s*```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Fall back to the outermost brace/bracket pair.
    for opener, closer in (("{", "}"), ("[", "]")):
        start, end = text.find(opener), text.rfind(closer)
        if start != -1 and end > start:
            try:
                return json.loads(text[start:end + 1])
            except json.JSONDecodeError:
                continue
    raise LLMError(f"Response was not valid JSON: {raw[:300]}")


# ---------------------------------------------------------------- gemini ----
class GeminiLLM(BaseLLM):
    name = "gemini"

    def __init__(self, model: Optional[str] = None, api_key: Optional[str] = None):
        self.model = model or config.GEMINI_MODEL
        self.api_key = api_key or config.GEMINI_API_KEY
        if not self.api_key:
            raise LLMError("GEMINI_API_KEY is not set (put it in backend/.env)")
        self._client = None

    def _get_client(self):
        if self._client is None:
            from google import genai
            self._client = genai.Client(api_key=self.api_key)
        return self._client

    def _complete(self, prompt: str, system: Optional[str], temperature: float) -> str:
        from google.genai import types

        client = self._get_client()
        cfg = types.GenerateContentConfig(
            temperature=temperature,
            max_output_tokens=config.LLM_MAX_OUTPUT_TOKENS,
            system_instruction=system,
        )
        response = client.models.generate_content(
            model=self.model, contents=prompt, config=cfg
        )
        return response.text or ""


# ------------------------------------------------------------------ groq ----
class GroqLLM(BaseLLM):
    name = "groq"

    def __init__(self, model: Optional[str] = None, api_key: Optional[str] = None):
        self.model = model or config.GROQ_MODEL
        self.api_key = api_key or config.GROQ_API_KEY
        if not self.api_key:
            raise LLMError("GROQ_API_KEY is not set (put it in backend/.env)")
        self._client = None

    def _get_client(self):
        if self._client is None:
            from groq import Groq
            # max_retries=0: BaseLLM.generate owns retries; the SDK's own
            # would multiply every attempt into three requests.
            self._client = Groq(api_key=self.api_key, max_retries=0)
        return self._client

    def _complete(self, prompt: str, system: Optional[str], temperature: float) -> str:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        completion = self._get_client().chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
            max_tokens=config.LLM_MAX_OUTPUT_TOKENS,
        )
        return completion.choices[0].message.content or ""


# ------------------------------------------------------------- fallback -----
class FallbackLLM(BaseLLM):
    """Try the primary provider; on failure, try the backup once.

    Free tiers hit quota mid-demo. This keeps a live demo alive rather than
    surfacing a 429 to the evaluator.
    """

    def __init__(self, primary: BaseLLM, backup: BaseLLM):
        self.primary, self.backup = primary, backup
        self.name = f"{primary.name}->{backup.name}"
        self.model = primary.model

    def _complete(self, prompt: str, system: Optional[str], temperature: float) -> str:
        return self.primary._complete(prompt, system, temperature)

    def generate(self, prompt: str, system: Optional[str] = None,
                 temperature: Optional[float] = None,
                 max_retries: Optional[int] = None) -> str:
        try:
            return self.primary.generate(prompt, system, temperature, max_retries)
        except Exception as exc:
            logger.warning("Primary provider %s exhausted (%s); falling back to %s.",
                           self.primary.name, exc, self.backup.name)
            return self.backup.generate(prompt, system, temperature, max_retries)


# ------------------------------------------------------------- factory ------
_PROVIDERS = {"gemini": GeminiLLM, "groq": GroqLLM}
_singleton: Optional[BaseLLM] = None


def build_llm(provider: Optional[str] = None, allow_fallback: Optional[bool] = None) -> BaseLLM:
    provider = (provider or config.LLM_PROVIDER).lower()
    if provider not in _PROVIDERS:
        raise LLMError(f"Unknown LLM provider '{provider}'. Choose one of {list(_PROVIDERS)}.")

    primary = _PROVIDERS[provider]()
    allow_fallback = config.LLM_AUTO_FALLBACK if allow_fallback is None else allow_fallback
    if not allow_fallback:
        return primary

    other = "groq" if provider == "gemini" else "gemini"
    try:
        return FallbackLLM(primary, _PROVIDERS[other]())
    except LLMError:
        # No key for the backup — run without one rather than refusing to start.
        logger.info("No backup provider configured; running on %s only.", provider)
        return primary


def configured_providers() -> list:
    """Which providers have an API key set. Used for clear startup/API errors."""
    available = []
    if config.GEMINI_API_KEY:
        available.append("gemini")
    if config.GROQ_API_KEY:
        available.append("groq")
    return available


def get_llm() -> BaseLLM:
    """Process-wide LLM instance."""
    global _singleton
    if _singleton is None:
        _singleton = build_llm()
    return _singleton


def call_llm(prompt: str) -> str:
    """One-shot completion on whichever provider config.LLM_PROVIDER selects."""
    return get_llm().generate(prompt)


def reset_llm() -> None:
    """Drop the cached client (used by tests and after a config change)."""
    global _singleton
    _singleton = None
