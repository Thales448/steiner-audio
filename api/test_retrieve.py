#!/usr/bin/env python3
"""Ranking checks for the local retriever. No network and no API key."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from retrieve import Retriever  # noqa: E402


def passage(book_id, cw, title, text, themes, kind="summary"):
    return {
        "id": book_id + ":" + kind,
        "book_id": book_id,
        "cw": cw,
        "kind": kind,
        "title": title,
        "text": f"CW {cw}. {title}. Topics: {', '.join(themes)}. {text}",
        "themes": themes,
        "section": "Test",
        "url": "https://rsarchive.org/example",
    }


PASSAGES = [
    passage("45", "45", "Anthroposophy: A Fragment", "The beginning of anthroposophy is a study of the human senses and the spiritual in the human being.", ["Philosophy"]),
    passage("135", "135", "Reincarnation and Karma", "These lectures treat reincarnation and karma as the way destiny works from one life to the next.", ["Karma & Reincarnation"]),
    passage("294", "294", "Practical Advice to Teachers", "A course for the first Waldorf teachers on education, the child, and how to teach.", ["Education"]),
    passage("4", "4", "The Philosophy of Freedom", "A philosophy of thinking, perception, and moral freedom.", ["Philosophy"]),
    passage("354", "354", "From Sunspots to Strawberries", "Conversations with the workers about plants, bees, and the sun.", ["Nature & Science"]),
]


def top(query: str) -> str:
    hits = Retriever(PASSAGES).search(query, k=3)
    assert hits, query
    return hits[0][0]["book_id"]


def main() -> None:
    assert top("What is anthroposophy?") == "45"
    assert top("Recommend lectures on karma") == "135"
    assert top("What did Steiner say about education?") == "294"
    assert top("CW 4 philosophy of freedom") == "4"
    print("retrieve ok")
    index = Path(__file__).resolve().parents[1] / "research" / "index.json"
    if not index.exists():
        print("skip catalog examples (no research/index.json)")
        return
    import server
    server.load()
    cases = {
        "What is anthroposophy?": {"45", "82", "84", "234"},
        "Recommend lectures on karma": {"135"},
        "What did Steiner say about education?": {"294", "295", "303", "307", "311", "317"},
    }
    for question, expected in cases.items():
        result = server.answer(question)
        assert result["mode"] == "retrieval", result["mode"]
        assert "OPENAI_API_KEY" in result["notice"]
        found = {item.get("cw") for item in result["recommendations"]}
        assert found & expected, (question, found)
        assert result["citations"] and result["recommendations"][0]["href"].startswith("#/album/")
    print("catalog examples ok")


if __name__ == "__main__":
    main()
