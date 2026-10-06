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

Update: `./build.sh && ./deploy.sh`
