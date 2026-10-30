"""
Knowledge retrieval.

`Retriever` is a small interface. Today MENDORA uses `KeywordRetriever` (simple, local, no AI).
A vector/embedding retriever can be added later as another class with the same `search()` method
and selected in `get_retriever()` — routes and the guidance service don't need to change.

Relevance: each result reports a score from 0 to 1 and the words that matched, so it's clear
WHY an entry was returned. Results below the threshold are dropped; if nothing passes, the
caller gets an empty list (a clear "no match"), never a made-up answer.
"""

import re
from dataclasses import dataclass, field
from typing import Protocol

# A few everyday synonyms (e.g. Indian and British/US English), mapped to one word.
SYNONYMS = {
    "faucet": "tap", "taps": "tap", "outlet": "socket", "outlets": "socket", "plugpoint": "socket",
    "commode": "toilet", "wc": "toilet", "loo": "toilet", "geyser": "heater", "almirah": "wardrobe",
    "cupboard": "cabinet", "cupboards": "cabinet", "fusebox": "fuse", "clogged": "clog", "blocked": "clog",
    "block": "clog", "jammed": "stick", "jam": "stick", "stuck": "stick", "lamp": "bulb", "lights": "light",
}
STOPWORDS = {
    "the", "a", "an", "and", "or", "is", "it", "its", "my", "in", "on", "of", "to", "for", "with", "when", "at",
    "this", "that", "there", "are", "was", "be", "been", "has", "have", "had", "i", "we", "our", "from", "very",
    "since", "but", "so", "just", "also", "some", "any", "can", "does", "do", "did", "after", "before", "it's",
    "started", "days", "day", "week", "ago", "now", "even", "one", "two", "really", "quite", "bit", "little",
}


# Common words that say little about WHICH problem it is: they count only a little, and never on their own.
GENERIC = {"work", "stop", "stopp", "keep", "not", "doesn't", "won't", "out", "use", "start", "problem", "issue", "new", "old", "make", "time", "long", "suddenly"}
GENERIC_WEIGHT = 0.25


def _stem(word: str) -> str:
    for suffix in ("ing", "ly", "ed", "es", "s"):
        if len(word) > len(suffix) + 2 and word.endswith(suffix):
            word = word[: -len(suffix)]
            break
    if len(word) > 4 and word.endswith("e"):  # "replace"/"replacing" -> "replac", "close"/"closing" -> "clos"
        word = word[:-1]
    return word


def tokenize(text: str) -> list[str]:
    words = re.findall(r"[a-z][a-z']+", text.lower())
    out = []
    for w in words:
        w = w.strip("'")
        if w in STOPWORDS or len(w) < 3:
            continue
        w = SYNONYMS.get(w, w)
        out.append(_stem(w))
    return out


@dataclass(frozen=True)
class Document:
    id: str
    trade: str
    text_fields: dict[str, str]  # field name -> text (title, keywords, symptoms…)
    weights: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class RetrievalHit:
    id: str
    score: float  # 0..1
    matched_terms: tuple[str, ...]


class Retriever(Protocol):
    name: str

    def search(self, query: str, *, trade: str | None = None, limit: int = 3) -> list[RetrievalHit]: ...


class KeywordRetriever:
    """
    Weighted word-overlap search. Score = matched field weights / best possible for this query,
    plus a small bonus for matching the trade. Deterministic and fast enough for hundreds of entries.
    """

    name = "keyword-v1"

    def __init__(self, documents: list[Document], *, min_score: float = 0.2, min_terms: int = 2) -> None:
        self.min_score = min_score
        self.min_terms = min_terms
        self._docs = []
        for doc in documents:
            index: dict[str, float] = {}
            for field_name, text in doc.text_fields.items():
                weight = doc.weights.get(field_name, 1.0)
                for token in tokenize(text):
                    index[token] = max(index.get(token, 0.0), weight)
            self._docs.append((doc, index))

    def search(self, query: str, *, trade: str | None = None, limit: int = 3) -> list[RetrievalHit]:
        q_tokens = list(dict.fromkeys(tokenize(query)))  # unique, in order
        specific = [t for t in q_tokens if t not in GENERIC]
        if not specific:
            return []
        # Best possible = the first few specific words all matching a title (weight 1.5).
        best_possible = min(len(specific), 5) * 1.5 + 0.0001
        hits: list[RetrievalHit] = []
        for doc, index in self._docs:
            if trade and doc.trade != trade:
                continue
            matched_specific = [t for t in specific if t in index]
            if len(matched_specific) < self.min_terms:
                continue
            matched_generic = [t for t in q_tokens if t in GENERIC and t in index]
            raw = sum(index[t] for t in matched_specific) + GENERIC_WEIGHT * len(matched_generic)
            score = min(1.0, raw / best_possible)
            if score >= self.min_score:
                hits.append(RetrievalHit(doc.id, round(score, 3), tuple(matched_specific + matched_generic)))
        hits.sort(key=lambda h: (-h.score, -len(h.matched_terms), h.id))
        return hits[:limit]


def documents_from_entries(entries) -> list[Document]:
    return [
        Document(
            id=e.id,
            trade=e.trade,
            text_fields={
                "title": e.title,
                "keywords": " ".join(e.keywords),
                "symptoms": " ".join(e.symptoms),
                "category": e.category,
            },
            weights={"title": 1.5, "keywords": 1.0, "symptoms": 1.2, "category": 0.8},
        )
        for e in entries
    ]


def get_retriever(entries, kind: str = "keyword") -> Retriever:
    if kind == "keyword":
        return KeywordRetriever(documents_from_entries(entries))
    raise ValueError(f"Unknown retriever '{kind}'. Only 'keyword' is available; an embedding retriever can be added later.")
