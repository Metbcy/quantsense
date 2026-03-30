import nltk
from nltk.sentiment.vader import SentimentIntensityAnalyzer


# Financial terms to augment VADER's lexicon
_FINANCIAL_LEXICON = {
    "surge": 2.5, "surges": 2.5, "surging": 2.5,
    "rally": 2.0, "rallies": 2.0, "rallying": 2.0,
    "soar": 2.5, "soars": 2.5, "soaring": 2.5,
    "bullish": 2.0, "upgrade": 1.8, "upgraded": 1.8,
    "outperform": 1.5, "beat": 1.5, "beats": 1.5,
    "exceeded": 1.5, "record-high": 2.0, "breakout": 1.5,
    "dividend": 1.0, "buyback": 1.5, "acquisition": 0.5,
    "plunge": -2.5, "plunges": -2.5, "plunging": -2.5,
    "crash": -3.0, "crashes": -3.0, "crashing": -3.0,
    "bearish": -2.0, "downgrade": -1.8, "downgraded": -1.8,
    "underperform": -1.5, "miss": -1.5, "misses": -1.5,
    "missed": -1.5, "lawsuit": -1.5, "layoffs": -1.8,
    "recession": -2.0, "default": -2.0, "bankruptcy": -3.0,
    "selloff": -2.0, "sell-off": -2.0, "tumble": -2.0,
    "decline": -1.5, "declines": -1.5, "declining": -1.5,
    "volatile": -0.5, "uncertainty": -1.0,
}


class VaderScorer:
    """Lightweight sentiment scorer using VADER with financial lexicon."""

    def __init__(self):
        try:
            nltk.data.find("sentiment/vader_lexicon.zip")
        except LookupError:
            nltk.download("vader_lexicon", quiet=True)
        self._analyzer = SentimentIntensityAnalyzer()
        self._analyzer.lexicon.update(_FINANCIAL_LEXICON)

    def score(self, text: str) -> float:
        """Score text from -1.0 (bearish) to +1.0 (bullish)."""
        scores = self._analyzer.polarity_scores(text)
        return scores["compound"]

    def score_batch(self, texts: list[str]) -> list[float]:
        """Score multiple texts."""
        return [self.score(t) for t in texts]
