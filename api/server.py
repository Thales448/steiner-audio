#!/usr/bin/env python3
"""Ask API for the Steiner Audio library.

Retrieval is local (see retrieve.py). If OPENAI_API_KEY or ANTHROPIC_API_KEY is
set, the retrieved passages are sent to that provider. Otherwise the response
is retrieval-only and says so.

  GET  /api/health
  GET  /api/ask?q=What+is+anthroposophy
  POST /api/ask   {"question": "...", "history": [{"role":"user","content":"..."}]}

Environment:
  STEINER_INDEX, STEINER_PASSAGES   research index paths
  OPENAI_API_KEY, OPENAI_MODEL      default model gpt-4o-mini
  ANTHROPIC_API_KEY, ANTHROPIC_MODEL default model claude-3-5-haiku-latest
  LLM_PROVIDER                      openai or anthropic when both keys exist
  STEINER_STATIC                    if set, also serve that directory (local dev)
  PORT                              default 8080
"""
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from retrieve import Retriever, tokenize

ROOT = Path(__file__).resolve().parents[1]
INDEX_PATH = Path(os.environ.get("STEINER_INDEX", ROOT / "research" / "index.json"))
PASSAGES_PATH = Path(os.environ.get("STEINER_PASSAGES", ROOT / "research" / "passages.jsonl"))
STATIC_ROOT = Path(os.environ["STEINER_STATIC"]).resolve() if os.environ.get("STEINER_STATIC") else None

RETRIEVAL_NOTICE = (
    "Full generative answers need OPENAI_API_KEY or ANTHROPIC_API_KEY on the API server. "
    "Showing the closest recordings and the research-index summaries."
)
GENERATIVE_NOTICE = (
    "Generated from passages retrieved from the Rudolf Steiner Archive texts and this library's catalog. "
    "Not an audio transcript. Quotations are only supported when they appear in those passages."
)

BOOKS: dict[str, dict] = {}
RETRIEVER: Retriever | None = None
LOAD_ERROR: str | None = None


def load() -> None:
    global BOOKS, RETRIEVER, LOAD_ERROR
    try:
        index = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
        passages = [
            json.loads(line)
            for line in PASSAGES_PATH.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        BOOKS = {book["id"]: book for book in index.get("books") or []}
        RETRIEVER = Retriever(passages)
        LOAD_ERROR = None
    except Exception as exc:  # noqa: BLE001 — reported by /api/health
        BOOKS = {}
        RETRIEVER = None
        LOAD_ERROR = str(exc)


def _key(name: str) -> str:
    return (os.environ.get(name) or "").strip()


def provider() -> str | None:
    preference = _key("LLM_PROVIDER").lower()
    anthropic = bool(_key("ANTHROPIC_API_KEY"))
    openai = bool(_key("OPENAI_API_KEY"))
    if preference == "openai" and openai:
        return "openai"
    if preference == "anthropic" and anthropic:
        return "anthropic"
    if preference in {"openai", "anthropic"}:
        # Honor an explicit provider only when its key is present; otherwise use whichever key exists.
        pass
    if anthropic:
        return "anthropic"
    if openai:
        return "openai"
    return None


def retrieval_query(question: str, history: list[dict]) -> str:
    if len(tokenize(question)) >= 4 or not history:
        return question
    previous = ""
    for message in reversed(history):
        if message.get("role") == "user" and message.get("content"):
            previous = str(message["content"])
            break
    return f"{previous} {question}".strip()


def _track_for(book: dict, passage: dict, question: str) -> dict | None:
    tracks = book.get("tracks") or []
    if not tracks:
        return None
    date = passage.get("lecture_date")
    if date:
        for track in tracks:
            if track.get("lecture_date") == date:
                return track
    wanted = set(tokenize(question))
    best = None
    best_score = 0
    for track in tracks:
        score = len(wanted & set(tokenize(f"{track.get('short') or ''} {track.get('title') or ''}")))
        if score > best_score:
            best_score = score
            best = track
    if best_score >= 2:
        return best
    return None


def _clip(text: str, limit: int) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def gather(question: str, history: list[dict]) -> tuple[list[dict], list[dict], list[tuple[dict, float]]]:
    assert RETRIEVER is not None
    hits = RETRIEVER.search(retrieval_query(question, history), k=24)
    grouped: dict[str, dict] = {}
    for passage, score in hits:
        bucket = grouped.setdefault(passage["book_id"], {"score": 0.0, "passages": []})
        # Max score, with a small lift from a second passage. Summing would favor books that were split into more chunks.
        bucket["passages"].append((passage, score))
        ranked = sorted((item[1] for item in bucket["passages"]), reverse=True)
        bucket["score"] = ranked[0] + (0.15 * ranked[1] if len(ranked) > 1 else 0.0)
    ranked_ids = sorted(grouped, key=lambda book_id: grouped[book_id]["score"], reverse=True)[:4]
    recommendations = []
    citations = []
    used_urls = set()
    for book_id in ranked_ids:
        book = BOOKS.get(book_id)
        if not book:
            continue
        passages = sorted(grouped[book_id]["passages"], key=lambda item: item[1], reverse=True)
        lead = passages[0][0]
        track = _track_for(book, lead, question)
        cw = book.get("cw")
        recommendations.append(
            {
                "id": book_id,
                "cw": cw,
                "title": book.get("title"),
                "year_label": book.get("year_label"),
                "section": book.get("section"),
                "themes": book.get("themes") or [],
                "cover": book.get("cover"),
                "href": book.get("album_href") or f"#/album/{book_id}",
                "site_url": book.get("site_url"),
                "rsarchive_url": book.get("rsarchive_url"),
                "summary": _clip(book.get("summary") or "", 480),
                "score": round(grouped[book_id]["score"], 3),
                "track": (
                    {
                        "title": _clip(track.get("short") or track.get("title") or "", 160),
                        "date": track.get("lecture_date"),
                        "place": track.get("location"),
                        "play_href": track.get("play_href"),
                        "spotify_url": track.get("spotify_url"),
                        "duration_s": track.get("duration_s"),
                    }
                    if track
                    else None
                ),
            }
        )
        for passage, _score in passages[:2]:
            url = passage.get("url") or book.get("rsarchive_url")
            key = (book_id, passage.get("lecture_title"), url)
            if key in used_urls:
                continue
            used_urls.add(key)
            matched = _track_for(book, passage, question)
            citations.append(
                {
                    "cw": cw,
                    "book_title": book.get("title"),
                    "lecture_title": passage.get("lecture_title"),
                    "date": passage.get("lecture_date") or (matched.get("lecture_date") if matched else None),
                    "place": passage.get("place") or (matched.get("location") if matched else None),
                    "rsarchive_url": url,
                    "album_href": book.get("album_href") or f"#/album/{book_id}",
                    "play_href": matched.get("play_href") if matched else None,
                    "kind": passage.get("kind"),
                }
            )
    return recommendations, citations[:6], hits


def retrieval_text(recommendations: list[dict]) -> str:
    if not recommendations:
        return (
            "Nothing in the research index matched that question. "
            "Try a CW number, a theme such as karma or education, or the title of a lecture cycle."
        )
    lines = [
        "These are the closest recordings and Rudolf Steiner Archive texts in this library.",
        "Each note is taken from the research index (archive introductions, lecture and chapter titles, and short opening excerpts). It is not a transcript of the audio, and it does not add quotations beyond those excerpts.",
        "",
    ]
    for index, item in enumerate(recommendations, 1):
        label = f"CW {item['cw']}" if item.get("cw") else "Compilation"
        lines.append(f"{index}. {label} — {item.get('title')} ({item.get('year_label') or 'undated'}, {item.get('section') or 'catalog'})")
        lines.append(item.get("summary") or "")
        track = item.get("track")
        if track:
            where = ", ".join(bit for bit in (track.get("date"), track.get("place")) if bit)
            lines.append(f"A matching recording: {track.get('title')}" + (f" ({where})" if where else "") + ".")
        lines.append("")
    return "\n".join(lines).strip()


def _post_json(url: str, payload: dict, headers: dict, timeout: int = 45) -> dict:
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def context_block(hits: list[tuple[dict, float]], limit: int = 12000) -> str:
    chunks = []
    used = 0
    for index, (passage, _score) in enumerate(hits, 1):
        if len(chunks) >= 10:
            break
        cw = f"CW {passage.get('cw')}" if passage.get("cw") else "Compilation"
        header = (
            f"[{index}] {cw} — {passage.get('title')}. "
            f"Kind: {passage.get('kind')}. "
            f"Lecture: {passage.get('lecture_title') or '—'} "
            f"{passage.get('lecture_date') or ''} {passage.get('place') or ''}. "
            f"Source: {passage.get('url') or ''}"
        )
        body = (passage.get("text") or "")[:1800]
        piece = header + "\n" + body
        if used + len(piece) > limit and chunks:
            break
        chunks.append(piece)
        used += len(piece)
    return "\n\n".join(chunks)


def generate(question: str, history: list[dict], hits: list[tuple[dict, float]]) -> tuple[str | None, str | None, str | None]:
    """Return (answer, provider, error). error is a short safe message."""
    name = provider()
    if not name:
        return None, None, None
    system = (
        "You answer questions about Rudolf Steiner for readers of the Steiner Audio library. "
        "Use ONLY the source passages in the user message. Do not invent quotations, dates, or biographical claims. "
        "If you quote, every quoted word must appear in a passage, and you must name the CW number and the lecture or chapter. "
        "If the passages do not support a claim, say that the index does not contain it. "
        "Recommend specific books by CW number and title. "
        "The recordings are read by Dale B. Brunsvold; you do not have audio transcripts. "
        "Write clear prose. End with a Sources list of the CW numbers you used."
    )
    prior = []
    for message in history[-4:]:
        role = message.get("role")
        content = str(message.get("content") or "")[:1500]
        if role in {"user", "assistant"} and content:
            prior.append({"role": role, "content": content})
    user = f"Source passages:\n\n{context_block(hits)}\n\nQuestion: {question}"
    try:
        if name == "anthropic":
            message = _post_json(
                "https://api.anthropic.com/v1/messages",
                {
                    "model": os.environ.get("ANTHROPIC_MODEL", "claude-3-5-haiku-latest"),
                    "max_tokens": 900,
                    "system": system,
                    "messages": prior + [{"role": "user", "content": user}],
                },
                {
                    "content-type": "application/json",
                    "x-api-key": _key("ANTHROPIC_API_KEY"),
                    "anthropic-version": "2023-06-01",
                },
            )
            parts = [block.get("text", "") for block in message.get("content") or [] if block.get("type") == "text"]
            text = "\n".join(part for part in parts if part).strip()
        else:
            message = _post_json(
                "https://api.openai.com/v1/chat/completions",
                {
                    "model": os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
                    "temperature": 0.2,
                    "messages": [{"role": "system", "content": system}, *prior, {"role": "user", "content": user}],
                },
                {
                    "content-type": "application/json",
                    "authorization": f"Bearer {_key('OPENAI_API_KEY')}",
                },
            )
            text = (((message.get("choices") or [{}])[0].get("message") or {}).get("content") or "").strip()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:240]
        detail = re.sub(r"sk-[A-Za-z0-9_-]+", "[redacted]", detail)
        return None, name, f"The language-model call failed ({exc.code}). {detail}"
    except Exception as exc:  # noqa: BLE001
        return None, name, f"The language-model call failed ({type(exc).__name__})."
    if not text:
        return None, name, "The language model returned an empty answer."
    return text, name, None


def answer(question: str, history: list[dict] | None = None) -> dict:
    history = history or []
    if LOAD_ERROR or RETRIEVER is None:
        return {
            "question": question,
            "mode": "error",
            "provider": None,
            "notice": "The research index is not loaded on this server.",
            "answer": LOAD_ERROR or "missing index",
            "citations": [],
            "recommendations": [],
        }
    recommendations, citations, hits = gather(question, history)
    generated, name, error = generate(question, history, hits)
    if generated:
        return {
            "question": question,
            "mode": "generative",
            "provider": name,
            "notice": GENERATIVE_NOTICE,
            "answer": generated,
            "citations": citations,
            "recommendations": recommendations,
        }
    notice = RETRIEVAL_NOTICE
    if error:
        notice = error + " " + RETRIEVAL_NOTICE
    return {
        "question": question,
        "mode": "retrieval",
        "provider": None,
        "notice": notice,
        "answer": retrieval_text(recommendations),
        "citations": citations,
        "recommendations": recommendations,
    }


def _clean_history(raw) -> list[dict]:
    if not isinstance(raw, list):
        return []
    cleaned = []
    for item in raw[-6:]:
        if not isinstance(item, dict):
            continue
        role = item.get("role")
        content = item.get("content")
        if role in {"user", "assistant"} and isinstance(content, str) and content.strip():
            cleaned.append({"role": role, "content": content.strip()[:2000]})
    return cleaned


class Handler(BaseHTTPRequestHandler):
    server_version = "SteinerAsk/1.0"

    def log_message(self, fmt: str, *args) -> None:
        print(f"{self.address_string()} {fmt % args}", flush=True)

    def _send(self, code: int, payload: dict | None = None, body: bytes | None = None, content_type: str = "application/json; charset=utf-8") -> None:
        data = body if body is not None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _question(self) -> tuple[str | None, list[dict], str | None]:
        if self.command == "GET":
            from urllib.parse import urlparse, parse_qs
            query = parse_qs(urlparse(self.path).query)
            text = (query.get("q") or [""])[0].strip()
            return text, [], None
        length = int(self.headers.get("Content-Length") or "0")
        if length > 40_000:
            return None, [], "Request body is too large."
        raw = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(raw.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            return None, [], "Body must be JSON."
        text = payload.get("question") or payload.get("q") or ""
        if not isinstance(text, str):
            return None, [], "question must be a string."
        return text.strip(), _clean_history(payload.get("history")), None

    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        if path == "/api/health":
            self._send(
                200 if not LOAD_ERROR else 500,
                {
                    "ok": LOAD_ERROR is None,
                    "books": len(BOOKS),
                    "passages": len(RETRIEVER.passages) if RETRIEVER else 0,
                    "llm": provider(),
                    "error": LOAD_ERROR,
                },
            )
            return
        if path == "/api/ask":
            self._handle_ask()
            return
        if path.startswith("/api/"):
            self._send(404, {"error": "Not found"})
            return
        if STATIC_ROOT is not None:
            self._static(path)
            return
        self._send(404, {"error": "Not found"})

    def do_POST(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        if path != "/api/ask":
            self._send(404, {"error": "Not found"})
            return
        self._handle_ask()

    def _handle_ask(self) -> None:
        question, history, error = self._question()
        if error:
            self._send(400, {"error": error})
            return
        if not question:
            self._send(400, {"error": "Ask a question."})
            return
        if len(question) > 800:
            self._send(400, {"error": "Question is too long."})
            return
        self._send(200, answer(question, history))

    def _static(self, path: str) -> None:
        assert STATIC_ROOT is not None
        relative = path.lstrip("/") or "index.html"
        if ".." in relative.split("/"):
            self._send(400, {"error": "Bad path"})
            return
        file = (STATIC_ROOT / relative).resolve()
        if not str(file).startswith(str(STATIC_ROOT)) or not file.is_file():
            file = STATIC_ROOT / "index.html"
        kind = {
            ".html": "text/html; charset=utf-8",
            ".css": "text/css; charset=utf-8",
            ".js": "text/javascript; charset=utf-8",
            ".json": "application/json",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".svg": "image/svg+xml",
            ".webp": "image/webp",
        }.get(file.suffix.lower(), "application/octet-stream")
        self._send(200, body=file.read_bytes(), content_type=kind)


def main() -> None:
    load()
    if LOAD_ERROR:
        print(f"index not loaded: {LOAD_ERROR}", flush=True)
    else:
        print(f"loaded {len(BOOKS)} books, {len(RETRIEVER.passages) if RETRIEVER else 0} passages, llm={provider()}", flush=True)
    port = int(os.environ.get("PORT", "8080"))
    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    print(f"listening on {port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
