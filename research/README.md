# Research index

A machine-readable index of the Rudolf Steiner Audio library (159 books and lecture cycles, 1999 recordings) for retrieval and research agents.

It is **not** a transcript of the Dale B. Brunsvold readings. Audio transcripts are not available from the podcast feed. Where a public-domain text exists, the index stores the Rudolf Steiner Archive lecture or chapter list, a short opening excerpt, and a summary grounded in that text.

## What each book record contains

`research/index.json` has one object per catalog album:

| Field | Source |
|---|---|
| `cw`, `title`, `year` / `years` / `year_label`, `locations`, `section`, `themes` | `catalog.json` |
| `tracks[]` | Recording title, date, place, duration, MP3 URL, Spotify URL, `play_href` into this site (`#/album/<id>/<track>`) |
| `cover`, `cover_src`, `episode_artwork` | Library cover and publisher artwork |
| `site_url`, `spotify_show`, `album_href` | rudolfsteineraudio.com, the Spotify show, and this site |
| `rsarchive_url`, `archive_title`, `lectures[]`, `editorial` | [rsarchive.org](https://rsarchive.org) volume matched by CW/GA number |
| `excerpts[]` | Opening paragraphs of up to two English lectures or chapters |
| `summary` | Natural-language overview. Quoted sentences are copied from `excerpts` or the archive introduction. `summary_basis` says which inputs were used |
| `audio_transcript` | Always `false` |

`research/passages.jsonl` is the retrieval view: one passage per summary, excerpt, and chunk of recording titles. The Ask API loads both files.

## Pipeline

`research/build_research_index.py` rebuilds both files.

1. Read `catalog.json`.
2. Fetch `https://rsarchive.org/Volumes.html` and map each CW/GA label to a Books, Lectures, or Articles URL. Split volumes are handled explicitly (`173` → 173a/b/c, `174` → 174a/b, `266-1/2/3` → GA 266/I–III, `340-341` → GA 340 and 341). Lectures are then kept when their dates match the recordings.
3. Fetch the volume page. Lecture tables become the chapter list (title, date, place, English URL). Written works follow the English contents page (the Michael Wilson edition of CW 4 is preferred when the album title says so).
4. Fetch up to two English texts and store the opening ~1,400 characters. These are the only Steiner passages the summary is allowed to quote.
5. Compilations with no CW number (*Festivals and Their Meaning*, *Spiritualism, Madame Blavatsky and Theosophy*) are matched by recording title plus year against the archive search, and only kept when the lecture URL contains that recording's date.
6. Write the summary from the archive introduction (when the volume page has one), the lecture or chapter titles, and one short opening quotation. Catalog-only wording is used if a fetch fails.
7. Write `index.json` and `passages.jsonl`.

HTML is cached under `research/cache/` (gitignored). A later run reuses the cache. `--refresh` ignores the per-book JSON cache. `--only 4,135` rebuilds selected album ids (it also rewrites the output files to just those ids, so use it for debugging, then run a full build).

```bash
python3 research/build_research_index.py
python3 api/test_retrieve.py
```

Steiner died in 1925. The texts on rsarchive.org are public domain in the United States. This repo stores short excerpts and citations, not a mirror of the archive. Be polite to rsarchive.org if you rebuild; the script waits between requests.

## Ask API

Retrieval is local: BM25 over the passages, plus a 256-dimension feature-hash embedding of token unigrams and bigrams (no model download). A few theme synonyms (`karma` → reincarnation, `education` → Waldorf / teacher) are expanded on the query only.

Generation, when configured, sends those passages to OpenAI or Anthropic and is instructed not to invent quotations. See the root README for keys and deploy.
