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


class AnthropicProvider(LLMProvider):
    """Anthropic Claude 3 Haiku provider."""

    def __init__(self) -> None:
        from config.settings import get_settings

        self._api_key = get_settings().anthropic_api_key or os.getenv(
            "ANTHROPIC_API_KEY", ""
        )

    @property
    def name(self) -> str:
        return "anthropic"

    def is_available(self) -> bool:
        return bool(self._api_key)

    async def analyze(self, text: str, ticker: str) -> LLMSentimentResult:
        if not self.is_available():
            return _fallback_result("ANTHROPIC_API_KEY not configured")
        try:
            import anthropic

            client = anthropic.AsyncAnthropic(api_key=self._api_key)
            response = await client.messages.create(
                model="claude-3-haiku-20240307",
                max_tokens=1024,
                system="You are a financial sentiment analyst. Respond with valid JSON only.",
                messages=[
                    {
                        "role": "user",
                        "content": ANALYSIS_PROMPT.format(ticker=ticker, text=text),
                    },
                ],
            )
            raw = response.content[0].text if response.content else ""
            return _result_from_dict(_parse_llm_json(raw))
        except Exception as exc:
            logger.warning("AnthropicProvider error: %s", exc)
            return _fallback_result(str(exc))
