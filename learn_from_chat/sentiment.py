from __future__ import annotations

import logging
from importlib import import_module
from dataclasses import dataclass

logger = logging.getLogger(__name__)

_CRITICAL_KEYWORDS = (
    "wrong",
    "incorrect",
    "hallucination",
    "false",
    "error",
    "mistake",
    "not true",
    "bad answer",
)


@dataclass
class SentimentResult:
    label: str
    score: float


class SentimentAnalyzer:
    """Lightweight sentiment detector with keyword fallback."""

    def __init__(self, model_name: str = "distilbert-base-uncased-finetuned-sst-2-english") -> None:
        self.model_name = model_name
        self._classifier = None
        self._load_error = False
        self._load_model()

    def _load_model(self) -> None:
        try:
            transformers_module = import_module("transformers")
            pipeline = getattr(transformers_module, "pipeline")
            self._classifier = pipeline("sentiment-analysis", model=self.model_name)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Sentiment model unavailable, keyword-only fallback enabled: %s", exc)
            self._load_error = True
            self._classifier = None

    def analyze(self, text: str) -> SentimentResult:
        normalized = (text or "").strip()
        if not normalized:
            return SentimentResult(label="NEUTRAL", score=0.0)

        has_critical_keyword = any(keyword in normalized.lower() for keyword in _CRITICAL_KEYWORDS)

        if not self._classifier:
            return SentimentResult(
                label="CRITICAL_FEEDBACK" if has_critical_keyword else "NEUTRAL",
                score=1.0 if has_critical_keyword else 0.0,
            )

        try:
            result = self._classifier(normalized[:512])[0]
            label = str(result.get("label", "NEUTRAL")).upper()
            score = float(result.get("score", 0.0))
        except Exception as exc:  # noqa: BLE001
            logger.warning("Sentiment inference failed, fallback to keyword rule: %s", exc)
            return SentimentResult(
                label="CRITICAL_FEEDBACK" if has_critical_keyword else "NEUTRAL",
                score=1.0 if has_critical_keyword else 0.0,
            )

        if has_critical_keyword:
            return SentimentResult(label="CRITICAL_FEEDBACK", score=max(score, 0.8))

        return SentimentResult(label=label, score=score)

    def is_dissatisfied(self, text: str) -> bool:
        result = self.analyze(text)
        return result.label in {"NEGATIVE", "CRITICAL_FEEDBACK"}
