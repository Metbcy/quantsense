from __future__ import annotations

import json
import logging
import os
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

ANALYSIS_PROMPT = """\
Analyze the following text for sentiment related to the stock ticker {ticker}.

Text:
\"\"\"
{text}
\"\"\"

Respond with ONLY valid JSON in this exact format:
{{
  "score": <float between -1.0 (very bearish) and 1.0 (very bullish)>,
  "summary": "<one-sentence summary of the sentiment>",
  "signals": ["<bullish: reason or bearish: reason>", ...],
  "catalysts": ["<upcoming catalyst>", ...]
}}
"""


@dataclass
class LLMSentimentResult:
    score: float  # -1.0 to 1.0
    summary: str
    signals: list[str] = field(default_factory=list)
    catalysts: list[str] = field(default_factory=list)


class LLMProvider(ABC):
    @abstractmethod
    async def analyze(self, text: str, ticker: str) -> LLMSentimentResult: ...

    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    def is_available(self) -> bool: ...


def _parse_llm_json(raw: str) -> dict:
    """Best-effort extraction of a JSON object from LLM output."""
    match = re.search(r"\{[\s\S]*\}", raw)
    if match:
        return json.loads(match.group())
    raise ValueError("No JSON object found in response")


def _fallback_result(error_msg: str) -> LLMSentimentResult:
    return LLMSentimentResult(
        score=0.0, summary=f"Analysis unavailable: {error_msg}"
    )


def _result_from_dict(data: dict) -> LLMSentimentResult:
    score = float(data.get("score", 0.0))
    score = max(-1.0, min(1.0, score))
    return LLMSentimentResult(
        score=score,
        summary=str(data.get("summary", "")),
        signals=list(data.get("signals", [])),
        catalysts=list(data.get("catalysts", [])),
    )


# ---------------------------------------------------------------------------
# Provider implementations
# ---------------------------------------------------------------------------


class GroqProvider(LLMProvider):
    """Groq cloud inference (Llama 3.3 70B)."""

    def __init__(self) -> None:
        from config.settings import get_settings

        self._api_key = get_settings().groq_api_key or os.getenv("GROQ_API_KEY", "")

    @property
    def name(self) -> str:
        return "groq"

    def is_available(self) -> bool:
        return bool(self._api_key)

    async def analyze(self, text: str, ticker: str) -> LLMSentimentResult:
        if not self.is_available():
            return _fallback_result("GROQ_API_KEY not configured")
        try:
            from groq import AsyncGroq

            client = AsyncGroq(api_key=self._api_key)
            response = await client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[
                    {
                        "role": "system",
                        "content": "You are a financial sentiment analyst. Respond with valid JSON only.",
                    },
                    {
                        "role": "user",
                        "content": ANALYSIS_PROMPT.format(ticker=ticker, text=text),
                    },
                ],
                temperature=0.1,
                max_tokens=1024,
                response_format={"type": "json_object"},
            )
            raw = response.choices[0].message.content or ""
            return _result_from_dict(_parse_llm_json(raw))
        except Exception as exc:
            logger.warning("GroqProvider error: %s", exc)
            return _fallback_result(str(exc))


class OpenAIProvider(LLMProvider):
    """OpenAI GPT-4o-mini provider."""

    def __init__(self) -> None:
        from config.settings import get_settings

        self._api_key = get_settings().openai_api_key or os.getenv(
            "OPENAI_API_KEY", ""
        )

    @property
    def name(self) -> str:
        return "openai"

    def is_available(self) -> bool:
        return bool(self._api_key)

    async def analyze(self, text: str, ticker: str) -> LLMSentimentResult:
        if not self.is_available():
            return _fallback_result("OPENAI_API_KEY not configured")
        try:
            from openai import AsyncOpenAI

            client = AsyncOpenAI(api_key=self._api_key)
            response = await client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "system",
                        "content": "You are a financial sentiment analyst. Respond with valid JSON only.",
                    },
                    {
                        "role": "user",
                        "content": ANALYSIS_PROMPT.format(ticker=ticker, text=text),
                    },
                ],
                temperature=0.1,
                max_tokens=1024,
                response_format={"type": "json_object"},
            )
            raw = response.choices[0].message.content or ""
            return _result_from_dict(_parse_llm_json(raw))
        except Exception as exc:
            logger.warning("OpenAIProvider error: %s", exc)
            return _fallback_result(str(exc))


class CopilotProvider(LLMProvider):
    """GitHub Copilot provider (via device-flow auth)."""

    @property
    def name(self) -> str:
        return "copilot"

    def is_available(self) -> bool:
        try:
            from sentiment.ghcp_auth import get_token

            get_token()
            return True
        except Exception:
            return False

    async def analyze(self, text: str, ticker: str) -> LLMSentimentResult:
        try:
            from sentiment.ghcp_auth import get_token, COPILOT_ENDPOINT, DEFAULT_HEADERS
            import httpx

            token = get_token()
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    f"{COPILOT_ENDPOINT}/chat/completions",
                    headers={
                        **DEFAULT_HEADERS,
                        "Authorization": f"Bearer {token}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": "claude-opus-4-6",
                        "messages": [
                            {
                                "role": "system",
                                "content": "You are a financial sentiment analyst. Respond with valid JSON only.",
                            },
                            {
                                "role": "user",
                                "content": ANALYSIS_PROMPT.format(
                                    ticker=ticker, text=text
                                ),
                            },
                        ],
                        "temperature": 0.1,
                        "max_tokens": 1024,
                    },
                )
                resp.raise_for_status()
                raw = resp.json()["choices"][0]["message"]["content"]
                return _result_from_dict(_parse_llm_json(raw))
        except Exception as exc:
            logger.warning("CopilotProvider error: %s", exc)
            return _fallback_result(str(exc))
