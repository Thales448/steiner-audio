"""Local retrieval over the research passages.

BM25 ranks tokens. A 256-dimension feature-hash embedding (token unigrams and
bigrams, no downloaded model) breaks ties. Query synonyms expand a few Steiner
themes such as karma and education. Nothing here calls a network.
"""
from __future__ import annotations

import hashlib
import math
import re
from collections import defaultdict

DIM = 256
STOP = {
    "a", "an", "the", "and", "or", "of", "to", "in", "on", "for", "with", "from",
    "by", "at", "as", "is", "are", "was", "were", "be", "been", "being", "it",
    "this", "that", "these", "those", "what", "which", "who", "whom", "whose",
    "how", "why", "when", "where", "did", "do", "does", "about", "into", "than",
    "then", "there", "their", "his", "her", "its", "if", "not", "no", "yes",
    "can", "could", "would", "should", "please", "tell", "me", "say", "said",
    "steiner", "rudolf", "audio", "library", "lecture", "lectures", "book", "books",
}

SYNONYMS = {
    "anthroposophy": ["anthroposophical", "anthroposophic", "theosophy"],
    "anthroposophical": ["anthroposophy", "theosophy"],
    "anthroposophic": ["anthroposophy"],
    "theosophy": ["anthroposophy", "theosophical"],
    "karma": ["karmic", "reincarnation", "destiny"],
    "karmic": ["karma", "reincarnation"],
    "reincarnation": ["karma", "rebirth"],
    "education": ["educational", "teacher", "teachers", "waldorf", "pedagogy", "school"],
    "waldorf": ["education", "teacher", "teachers"],
    "teacher": ["education", "waldorf"],
    "christ": ["christian", "christology", "golgotha", "jesus"],
    "gospel": ["christ", "jesus", "gospels"],
    "medicine": ["medical", "healing", "illness", "therapy"],
    "healing": ["medicine", "therapy"],
    "freedom": ["philosophy", "philosophical"],
    "eurythmy": ["speech", "movement"],
    "economics": ["economic", "threefold"],
    "social": ["society", "threefolding"],
    "festival": ["festivals", "christmas", "easter", "michaelmas", "whitsun"],
    "christmas": ["festival", "festivals"],
    "easter": ["festival", "festivals"],
}


def tokenize(text: str) -> list[str]:
    return [word for word in re.findall(r"[a-z0-9]+", (text or "").lower()) if word not in STOP and len(word) > 1]


def _bucket(token: str) -> int:
    digest = hashlib.md5(token.encode("utf-8")).hexdigest()
    return int(digest[:8], 16) % DIM


def embed(tokens: list[str]) -> list[float]:
    vector = [0.0] * DIM
    for index, token in enumerate(tokens):
        vector[_bucket(token)] += 1.0
        if index:
            vector[_bucket(tokens[index - 1] + "_" + token)] += 0.5
    norm = math.sqrt(sum(value * value for value in vector)) or 1.0
    return [value / norm for value in vector]


def _cosine(left: list[float], right: list[float]) -> float:
    return sum(a * b for a, b in zip(left, right))


def _title_bonus(query_tokens: list[str], title: str) -> float:
    """Prefer a book whose title names the thing being asked about."""
    titled = set(tokenize(title))
    bonus = 0.0
    exact = []
    for token in query_tokens:
        if token in titled:
            bonus += 7.0
            exact.append(token)
            continue
        if len(token) > 7:
            stem = token[:7]
            if any(word.startswith(stem) or token.startswith(word[:7]) for word in titled if len(word) > 7):
                bonus += 1.5
    # A short title that is mostly the query ("Anthroposophy: A Fragment") ranks above a long title that merely contains the word.
    if titled and exact:
        bonus += 8.0 * len(exact) / len(titled)
    return bonus


class Retriever:
    def __init__(self, passages: list[dict]):
        self.passages = passages
        self.docs: list[tuple[list[str], dict[str, int], list[float], set[str]]] = []
        document_freq: dict[str, int] = defaultdict(int)
        for passage in passages:
            tokens = tokenize(
                " ".join(
                    [
                        passage.get("text") or "",
                        passage.get("title") or "",
                        str(passage.get("cw") or ""),
                        " ".join(passage.get("themes") or []),
                        passage.get("section") or "",
                    ]
                )
            )
            counts: dict[str, int] = defaultdict(int)
            for token in tokens:
                counts[token] += 1
            themes = set(tokenize(" ".join(passage.get("themes") or [])))
            self.docs.append((tokens, counts, embed(tokens), themes))
            for token in counts:
                document_freq[token] += 1
        self.document_freq = document_freq
        self.count = len(passages)
        self.avg_len = (sum(len(tokens) for tokens, *_ in self.docs) / self.count) if self.count else 1.0

    def _idf(self, token: str) -> float:
        seen = self.document_freq.get(token, 0)
        return math.log(1 + (self.count - seen + 0.5) / (seen + 0.5))

    def search(self, query: str, k: int = 8) -> list[tuple[dict, float]]:
        if not self.docs or not (query or "").strip():
            return []
        query_tokens = tokenize(query)
        if not query_tokens:
            query_tokens = [word for word in re.findall(r"[a-z0-9]+", query.lower()) if len(word) > 2]
        weights: dict[str, float] = defaultdict(float)
        for token in query_tokens:
            weights[token] += 1.0
            for synonym in SYNONYMS.get(token, []):
                weights[synonym] += 0.45
        query_vector = embed(query_tokens + [syn for token in query_tokens for syn in SYNONYMS.get(token, [])[:3]])
        cw_match = re.search(r"\b(?:cw|ga)\s*([0-9]+[a-z]?(?:-[0-9]+)?)", query, re.I)
        wanted_cw = cw_match.group(1).lower() if cw_match else None
        k1, b = 1.4, 0.65
        scored: list[tuple[float, int]] = []
        for index, (tokens, counts, vector, themes) in enumerate(self.docs):
            length = len(tokens) or 1
            bm25 = 0.0
            for token, weight in weights.items():
                freq = counts.get(token)
                if not freq:
                    continue
                denom = freq + k1 * (1 - b + b * length / self.avg_len)
                bm25 += weight * self._idf(token) * (freq * (k1 + 1)) / denom
            passage = self.passages[index]
            score = bm25 + 2.4 * _cosine(query_vector, vector)
            score += 0.9 * len(set(query_tokens) & themes)
            score += _title_bonus(query_tokens, passage.get("title") or "")
            if wanted_cw and str(passage.get("cw") or "").lower() == wanted_cw:
                score += 5.0
            if score > 0:
                scored.append((score, index))
        scored.sort(key=lambda item: item[0], reverse=True)
        return [(self.passages[index], score) for score, index in scored[:k]]
