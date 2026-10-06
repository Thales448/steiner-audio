# Steiner Audio Library — https://steiner.rtech.cloud

A visual library of the **Rudolf Steiner Audio** podcast on Spotify (show `3Ci1JAfMuj3fewAOfSAuKY`,
read by Dale B. Brunsvold): 1999 recordings grouped into 159 books / lecture cycles.

## Data sources
| Source | Used for |
|---|---|
| Podbean RSS `https://feed.podbean.com/rudolfsteiner/feed.xml` (feed URL from the Apple Podcasts lookup) | All episodes: titles, durations, release dates, **full MP3 URLs** |
| Spotify Web API (client credentials, `SPOTIFY_CLIENT_ID/SECRET` env) `GET /v1/shows/{id}/episodes` | Spotify episode IDs/URIs/URLs (1982 of 1999 matched by exact title) for the embeds |
| rudolfsteineraudio.com (`texttitleCWorder.html`, `lecturesimagebased.html`, `writtenimagebased.html`) | Canonical book titles per CW number + book-cover artwork |

On Spotify this is a **podcast show**, not an artist: there are no albums. An "album" here is one
book or lecture cycle, i.e. all the episodes that share a CW number.

## How the catalog is grouped
- **Series / CW (GA) number**: Episode titles start with `CW <n>` (or the older `<n> Episode k:` style), e.g. `CW 354 From Sunspots to Strawberries: Discussion 1: … (June 30 1924)`.
  157 groups have a CW number (sub-volumes such as 93a, 174a, 266-1/2/3 and 340-341 are kept separate). There are 2 compilations without one: *Festivals and Their Meaning* and *Spiritualism, Madame Blavatsky and Theosophy*.
- **Lecture year**: parsed from the dates in the titles (1673 of 1999 tracks). For 18 written works or undated cycles the album year is the GA reference date (`year_source` says which).
  The release date on Spotify/Podbean is stored separately (`released`).
- **Location**: parsed from the date parentheses (1120 tracks: Dornach, Berlin, Stuttgart, …).
- **GA section**: standard Gesamtausgabe ranges (1–28 Written Works, 51–87 Public Lectures, 88–253 Lectures to Members (103 cycles), 254–270 Movement & Esoteric Lessons, 271–292 Art, 293–311 Education, 312–319 Medicine, 320–327 Science, 328–341 Social, 342–346 Priests' courses, 347–354 Workers' lectures).
- **Topic**: keyword tags (Christology & Gospels, Esoteric Development, Karma, Cosmology, Arts, …).

## Files
- `catalog.json` is the full index (albums → tracks with Spotify id/uri/url, MP3, durations, dates, places, artwork). The same file is copied to `app/data/catalog.full.json`.
- `app/` is the static site (`index.html`, `app.js`, `style.css`, `data/catalog.json` slim, `img/` covers).
- Pipeline: `build.sh` runs `fetch_spotify.py`, `build_index.py`, `build_assets.py` and `render_static.py`.
- `deploy.sh` + `k8s/`: the namespace `steiner` with nginx-unprivileged serving an emptyDir. An init container unpacks the site tarball,
  which is split across the ConfigMaps `steiner-bundle-NN`. Also includes a Service, `Certificate/steiner-tls` (ClusterIssuer `rquants-selfsigned`, same as whipme/book)
  and `Ingress/steiner-ingress` (class nginx). There is no trading toleration, so the pod runs on worker3. DNS is the existing proxied `*.rtech.cloud` wildcard on Cloudflare.

Update the catalog and static site: `./build.sh && ./deploy.sh`

## Research index

`research/` is a structured index of the same 159 cycles for retrieval and for the Ask page. Each record has the CW number, title, year, place, GA section, topics, track list (duration, Spotify, MP3), artwork, and a short summary. Summaries are grounded in public-domain texts on [rsarchive.org](https://rsarchive.org) (volume introductions, lecture and chapter titles, and short opening excerpts). **There are no audio transcripts** of the Brunsvold readings. Rebuild and field notes: `research/README.md`.

```bash
python3 research/build_research_index.py
```

Outputs: `research/index.json` and `research/passages.jsonl`. Fetched HTML is cached in `research/cache/` and is not committed.

## Ask

The site has an **Ask** page (`#/ask`). It calls `POST /api/ask` and shows the answer, RS Archive citations, and recommended albums (cover and link) that open the existing player pages. Example questions, also listed in `research/examples.md`:

- What is anthroposophy?
- Recommend lectures on karma
- What did Steiner say about education?

Retrieval is local (BM25 plus a small hashed embedding over the research passages). It does not need a network or a key. A generative answer is added when the API process has a key:

| Variable | Role |
|---|---|
| `OPENAI_API_KEY` | OpenAI chat completions. Model: `OPENAI_MODEL` (default `gpt-4o-mini`) |
| `ANTHROPIC_API_KEY` | Anthropic messages. Model: `ANTHROPIC_MODEL` (default `claude-3-5-haiku-latest`) |
| `LLM_PROVIDER` | `openai` or `anthropic` when both keys are set. Otherwise an Anthropic key is used if present, else OpenAI |

If neither key is set, the API still answers: it returns the closest cycles and their research-index summaries, and the page says that a full generative answer needs a key. The model is told to use only the retrieved passages and not to invent quotations.

Local run (static site and API together):

```bash
PORT=8091 STEINER_STATIC=app python3 api/server.py
```

On the cluster, `./deploy.sh` keeps nginx on `/` and serves the API at `/api` from a second Deployment, `steiner-api`, in the `steiner` namespace. The API image is public `python:3.12-alpine`; the code and index are mounted from ConfigMaps, same pattern as the site, so no registry is required. An optional image build is `api/Dockerfile`. The pod has no trading-pool toleration.

Create the key as a Secret (the example manifest is not applied automatically, and keys are not committed):

```bash
kubectl -n steiner create secret generic steiner-llm \
  --from-literal=OPENAI_API_KEY='sk-...' \
  --from-literal=ANTHROPIC_API_KEY='' \
  --from-literal=LLM_PROVIDER='' \
  --dry-run=client -o yaml | kubectl apply -f -
kubectl -n steiner rollout restart deploy/steiner-api
```

`LLM_PROVIDER` may be omitted. See `k8s/09-llm-secret.example.yaml`.

Rebuild the index, then the site and the API:

```bash
python3 research/build_research_index.py
./build.sh && ./deploy.sh
```

`./build.sh` refreshes the podcast catalog only. It does not call rsarchive.org. `./deploy.sh` refuses to roll the API if `research/index.json` is missing.
