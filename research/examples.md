# Example questions

These run against the committed index with no API key. The API then returns `mode: "retrieval"` and says that a full written answer needs `OPENAI_API_KEY` or `ANTHROPIC_API_KEY`. Recommendations are albums in this library. `href` opens the album page; a citation's RS Archive link opens the lecture text.

Start the API (and, for the buttons in the site, the static files) from the repo root:

```bash
PORT=8091 STEINER_STATIC=app python3 api/server.py
```

```bash
curl -s -X POST localhost:8091/api/ask \
  -H 'content-type: application/json' \
  -d '{"question":"What is anthroposophy?"}'
```

Same for the other two questions. In the site, open `#/ask` and use the three suggestion buttons.

## What is anthroposophy?

Retrieval recommends, in order:

1. **CW 84 — The Aims of Anthroposophy** (`#/album/84`)
2. **CW 82 — Becoming Fully Human: The Significance of Anthroposophy in Contemporary Spiritual Life** (`#/album/82`)
3. **CW 45 — Anthroposophy: A Fragment** (`#/album/45`)
4. **CW 234 — Anthroposophy and the Inner Life** (`#/album/234`)

Citations include the archive volume and, where a lecture was retrieved, its date. For CW 234 that is the lecture “Anthroposophy as What Men Long For Today” (19 January 1924).

## Recommend lectures on karma

1. **CW 135 — Reincarnation and Karma** (`#/album/135`), including “Reincarnation and karma: the fundamental ideas of the anthroposophical world conception” (5 March 1912, Berlin)
2. **CW 176 — The Karma of Materialism** (`#/album/176`)
3. **CW 174 — The Karma of Untruthfulness, Vol. 2** (`#/album/174`)
4. **CW 173 — The Karma of Untruthfulness, Vol. 1** (`#/album/173`)

## What did Steiner say about education?

1. **CW 307 — A Modern Art of Education** (`#/album/307`)
2. **CW 303 — Soul Economy and Waldorf Education** (`#/album/303`)
3. **CW 317 — Education for Special Needs: The Curative Education Course** (`#/album/317`)
4. **CW 311 — The Kingdom of Childhood** (`#/album/311`)

`api/test_retrieve.py` checks that these questions still surface those CW numbers.
