#!/usr/bin/env python3
"""Build a machine-readable research index of the Steiner Audio catalog.

Reads catalog.json, fetches public-domain Rudolf Steiner texts from
https://rsarchive.org matched by CW/GA number, and writes:

  research/index.json      one record per book / lecture cycle
  research/passages.jsonl  retrieval passages for the Ask API

Fetched HTML is cached under research/cache/ (gitignored). Re-running uses
the cache. This index does not contain audio transcripts of the Brunsvold
recordings.

Usage:
  python3 research/build_research_index.py
  python3 research/build_research_index.py --only 4,135,294
  python3 research/build_research_index.py --refresh
"""
from __future__ import annotations

import argparse
import hashlib
import html as html_lib
import json
import re
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CACHE = Path(__file__).resolve().parent / "cache"
BASE = "https://rsarchive.org"
UA = "Mozilla/5.0 (compatible; SteinerAudioResearch/1.0; +https://github.com/Thales448/steiner-audio)"

MONTHS = {}
for _i, _name in enumerate(
    "january february march april may june july august september october november december".split(),
    1,
):
    MONTHS[_name] = _i
    MONTHS[_name[:3]] = _i
MONTHS["sept"] = 9

DE_WORDS = {
    "und", "der", "das", "nicht", "eine", "einer", "einem", "einen", "ist", "von",
    "den", "dem", "des", "mit", "auch", "als", "zum", "zur", "sich", "auf", "für",
    "fur", "ein", "wird", "sind", "oder", "nach", "aus", "bei", "durch", "über",
}

# Catalog CW strings that do not match a single Volumes.html label.
SPECIAL_GA = {
    "266": ["266i"],
    "266-1": ["266i"],
    "266-2": ["266ii"],
    "266-3": ["266iii"],
    "173": ["173a", "173b", "173c"],
    "174": ["174a", "174b"],
    "340-341": ["340", "341"],
}

ROMAN = {1: "i", 2: "ii", 3: "iii", 4: "iv", 5: "v", 6: "vi"}


class HttpCache:
    def __init__(self, root: Path, delay: float = 0.12, concurrency: int = 4):
        self.root = root
        self.delay = delay
        self.sem = threading.Semaphore(concurrency)
        self.mu = threading.Lock()
        self.last = 0.0
        (root / "pages").mkdir(parents=True, exist_ok=True)

    def path_for(self, url: str) -> Path:
        u = urllib.parse.urlparse(url)
        name = (u.path.strip("/") or "root").replace("/", "__")
        if u.query:
            name += "__" + hashlib.sha1(u.query.encode()).hexdigest()[:8]
        name = re.sub(r"[^A-Za-z0-9._-]+", "_", name)[:180]
        return self.root / "pages" / f"{name}.html"

    def get(self, url: str) -> str | None:
        path = self.path_for(url)
        if path.exists() and path.stat().st_size > 400:
            return path.read_text(encoding="utf-8", errors="replace")
        text = self._fetch(url)
        if text:
            path.write_text(text, encoding="utf-8")
        return text

    def _fetch(self, url: str) -> str | None:
        err = "unknown"
        for attempt in range(4):
            with self.sem:
                with self.mu:
                    gap = self.delay - (time.time() - self.last)
                    if gap > 0:
                        time.sleep(gap)
                    self.last = time.time()
                try:
                    req = urllib.request.Request(
                        url,
                        headers={
                            "User-Agent": UA,
                            "Accept": "text/html,application/xhtml+xml",
                            "Accept-Language": "en",
                        },
                    )
                    with urllib.request.urlopen(req, timeout=45) as resp:
                        raw = resp.read()
                    text = raw.decode("utf-8", errors="replace")
                    low = text.lower()
                    if "just a moment" in low and "cloudflare" in low:
                        err = "cloudflare challenge"
                        time.sleep(1.5 * (attempt + 1))
                        continue
                    if len(text) < 400:
                        err = f"short response {len(text)}"
                        time.sleep(0.5)
                        continue
                    return text
                except Exception as exc:  # noqa: BLE001 — keep crawling after one bad URL
                    err = str(exc)
                    time.sleep(0.7 * (attempt + 1))
        print(f"fetch fail {url} ({err})", flush=True)
        return None


def clean_html(fragment: str) -> str:
    s = re.sub(r"(?is)<script\b.*?</script>", " ", fragment or "")
    s = re.sub(r"(?is)<style\b.*?</style>", " ", s)
    s = re.sub(r"(?i)<br\s*/?>", "\n", s)
    s = re.sub(r"(?i)</p>", "\n", s)
    s = re.sub(r"<[^>]+>", " ", s)
    s = html_lib.unescape(s).replace("\xa0", " ")
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\n\s*", "\n", s)
    return s.strip()


def squash(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def mostly_english(text: str) -> bool:
    words = re.findall(r"[A-Za-zÄÖÜäöüß]+", text or "")
    if len(words) < 12:
        return True
    de = sum(1 for w in words if w.lower() in DE_WORDS)
    return (de / len(words)) < 0.06


def article_html(page: str) -> str:
    m = re.search(r'(?is)<div class="articleBox">(.*)', page or "")
    chunk = m.group(1) if m else (page or "")
    for marker in ("<!-- End Article", "<!-- End Center", '<aside class="sidebars">'):
        i = chunk.find(marker)
        if i != -1:
            chunk = chunk[:i]
            break
    return chunk


def parse_archive_date(text: str) -> str | None:
    s = squash(text)
    m = re.search(r"(\d{1,2})\s+([A-Za-z]+)\.?\s+(\d{4})", s)
    if m:
        day, mon, year = m.groups()
    else:
        m = re.search(r"([A-Za-z]+)\.?\s+(\d{1,2}),?\s+(\d{4})", s)
        if not m:
            return None
        mon, day, year = m.groups()
    key = mon.lower().replace(".", "")
    month = MONTHS.get(key) or MONTHS.get(key[:3])
    if not month:
        return None
    return f"{int(year):04d}-{month:02d}-{int(day):02d}"


def paragraphs(fragment: str) -> list[str]:
    out = []
    for raw in re.findall(r"(?is)<p[^>]*>(.*?)</p>", fragment):
        t = squash(clean_html(raw))
        t = re.sub(r"^\[\s*\d+\s*\]\s*", "", t)
        if len(t) < 70:
            continue
        low = t.lower()
        if low.startswith("translated by"):
            continue
        if "project of steiner online library" in low:
            continue
        if low.startswith("copyright"):
            continue
        if "donate books" in low:
            continue
        out.append(t)
    return out


def excerpt_text(paras: list[str], limit: int = 1400) -> str:
    buf = ""
    for para in paras:
        if buf and len(buf) + 1 + len(para) > limit:
            break
        buf = f"{buf} {para}".strip()
        if len(buf) >= limit:
            break
    if len(buf) > limit:
        cut = buf[:limit]
        stop = max(cut.rfind(". "), cut.rfind("? "), cut.rfind("! "))
        buf = cut[: stop + 1] if stop > 400 else cut.rstrip() + "…"
    return buf


def first_sentence(text: str, limit: int = 380) -> str | None:
    text = squash(text)
    if not text:
        return None
    parts = re.split(r"(?<=[.!?])\s+", text)
    sentence = parts[0].strip()
    if len(sentence) < 40:
        return None
    if len(sentence) > limit:
        return sentence[: limit - 1].rstrip() + "…"
    return sentence


def volume_heading(article: str) -> tuple[str | None, str | None]:
    m = re.search(r"(?is)<h2>(.*?)</h2>", article)
    if not m:
        return None, None
    parts = re.split(r"(?is)<br\s*/?>|<small>|</small>", m.group(1))
    cleaned = []
    for part in parts:
        text = squash(clean_html(part))
        if not text or re.fullmatch(r"GA\s*\d+[a-zIVX]*", text, re.I):
            continue
        cleaned.append(text)
    if not cleaned:
        return None, None
    return cleaned[0], squash(" ".join(cleaned[1:]))[:400] or None


def editorial_text(article: str) -> str:
    chunks = []
    for raw in re.findall(r"(?is)<blockquote>(.*?)</blockquote>", article):
        text = squash(clean_html(raw))
        if len(text) < 80 or not mostly_english(text):
            continue
        chunks.append(text)
    if not chunks:
        # Some volume pages introduce the book in ordinary paragraphs (GA 27) rather than a blockquote.
        head = re.split(r"(?is)<table\b|<h3\b", article, maxsplit=1)[0]
        chunks = [paragraph for paragraph in paragraphs(head) if mostly_english(paragraph)]
    return "\n\n".join(chunks)[:2500]


def lecture_score(item: dict) -> int:
    title = item.get("title") or ""
    score = len(title)
    if re.fullmatch(
        r"(First|Second|Third|Fourth|Fifth|Sixth|Seventh|Eighth|Ninth|Tenth|Eleventh|Twelfth|Lecture \d+|Part \d+)",
        title,
        re.I,
    ):
        score -= 80
    url = item.get("url") or ""
    if "/English/" in url:
        score += 25
    if re.search(r"p01\.html$", url):
        score += 10
    return score


def merge_lecture(old: dict, new: dict) -> dict:
    if lecture_score(new) > lecture_score(old):
        base, extra = dict(new), old
    else:
        base, extra = dict(old), new
    for key in ("date", "place", "n"):
        if not base.get(key) and extra.get(key):
            base[key] = extra[key]
    return base


def table_rows(article: str) -> list[list[str]]:
    """Return table cells. Some archive pages close </tr> without opening <tr>."""
    chunk = re.sub(r"(?is)<thead>.*?</thead>", " ", article)
    rows = []
    for part in re.split(r"(?is)</tr>", chunk):
        if re.search(r"(?is)<tr\b", part):
            part = re.split(r"(?is)<tr\b[^>]*>", part)[-1]
        cells = re.findall(r"(?is)<td[^>]*>(.*?)</td>", part)
        if len(cells) >= 2:
            rows.append(cells)
    return rows


def parse_lectures(article: str) -> list[dict]:
    groups: list[dict] = []
    index: dict = {}
    current_n = None
    for cells in table_rows(article):
        nmatch = re.match(r"(\d+)", squash(clean_html(cells[0])))
        if nmatch:
            current_n = int(nmatch.group(1))
        anchors = re.findall(r'(?is)<a href="([^"]+)"[^>]*>(.*?)</a>', cells[1])
        if not anchors:
            continue
        href, label = anchors[0]
        if "/German/" in href:
            continue
        title = squash(clean_html(label))
        if not title or title.upper() in {"DE", "EN"}:
            continue
        date = parse_archive_date(clean_html(cells[3])) if len(cells) >= 4 else None
        place = squash(clean_html(cells[4])) if len(cells) >= 5 else ""
        if not place or len(place) > 48 or place.upper() == "DE":
            place = None
        item = {
            "n": current_n,
            "title": title,
            "url": urllib.parse.urljoin(BASE + "/", href),
            "date": date,
            "place": place,
        }
        key = ("n", current_n) if current_n else ("u", item["url"])
        if key not in index:
            index[key] = len(groups)
            groups.append(item)
        else:
            groups[index[key]] = merge_lecture(groups[index[key]], item)
    return groups


def parse_volume(page: str, url: str) -> dict:
    article = article_html(page)
    title, subtitle = volume_heading(article)
    return {
        "url": url,
        "title": title,
        "subtitle": subtitle,
        "editorial": editorial_text(article),
        "lectures": parse_lectures(article),
        "article": article,
    }


def word_set(text: str) -> set[str]:
    stop = {"with", "from", "that", "this", "their", "volume", "lecture", "lectures", "chapter"}
    return {w for w in re.findall(r"[a-z0-9]+", (text or "").lower()) if len(w) > 3 and w not in stop}


def title_overlap(a: str, b: str) -> float:
    left, right = word_set(a), word_set(b)
    if not left or not right:
        return 0.0
    return len(left & right) / min(len(left), len(right))


def norm_title(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()


GENERIC_TITLE = re.compile(
    r"^(?:(?:lecture|part|chapter|section|discussion)\s+(?:\d+|[ivxlc]+)|"
    r"(?:first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth|eleventh|twelfth)\s+lecture)$",
    re.I,
)


def is_generic_title(title: str) -> bool:
    core = re.sub(r"\([^)]*\)", "", title or "")
    core = core.strip(" .:-–—")
    return bool(GENERIC_TITLE.fullmatch(core))


def display_heading(album: dict, archive_title: str | None) -> str:
    catalog_title = album.get("title") or archive_title or "Untitled"
    if not archive_title:
        return catalog_title
    cat_n, arch_n = norm_title(catalog_title), norm_title(archive_title)
    if not arch_n or arch_n in cat_n or cat_n in arch_n or title_overlap(catalog_title, archive_title) >= 0.6:
        return catalog_title
    return f"{catalog_title} (Rudolf Steiner Archive: {archive_title})"


def pick_edition(article: str, album_title: str) -> str | None:
    """Choose an English edition contents page. Nearby German text must not hide it."""
    best = None
    best_score = -1.0
    for match in re.finditer(r'href="([^"]*/English/[^"]*)"', article):
        href = match.group(1)
        if re.search(r"\.(jpg|png|gif)$", href, re.I):
            continue
        window = article[max(0, match.start() - 500) : match.end() + 500]
        text = squash(clean_html(window))
        score = title_overlap(album_title, text)
        if href.lower().endswith("index.html"):
            score += 0.6
        if "wilson" in text.lower() and "wilson" in (album_title or "").lower():
            score += 0.5
        if score > best_score:
            best_score = score
            best = urllib.parse.urljoin(BASE + "/", href)
    return best


def chapter_links(page: str, base_url: str) -> list[dict]:
    article = article_html(page)
    base_dir = urllib.parse.urlparse(base_url).path.rsplit("/", 1)[0] + "/"
    found = []
    seen = set()
    for href, label in re.findall(r'(?is)<a href="([^"]+)"[^>]*>(.*?)</a>', article):
        title = squash(clean_html(label))
        if not title or len(title) < 3:
            continue
        if re.search(r"^(contents|cover|next|previous|prev|back|more|home|books|lectures)\b", title, re.I):
            continue
        if re.fullmatch(r"[›»>˃\s.]+", title):
            continue
        full = urllib.parse.urljoin(base_url, href)
        path = urllib.parse.urlparse(full).path
        if "/English/" not in path:
            continue
        if not path.startswith(base_dir) and base_dir not in path:
            # relative chapter links resolve inside the edition directory
            if "://" in href or href.startswith("/"):
                continue
        if full in seen or full.rstrip("/").endswith("index.html"):
            continue
        if re.search(r"\.(jpg|png|gif|pdf)$", full, re.I):
            continue
        seen.add(full)
        found.append({"title": title, "url": full})
    return found


def choose_texts(links: list[dict]) -> list[dict]:
    content = [
        link
        for link in links
        if not re.search(r"cover|table of contents|contents$", link["title"], re.I)
    ]
    if not content:
        return []
    first = content[0]
    for link in content:
        blob = f"{link['title']} {link['url']}"
        if re.search(r"c0?1\b|chapter\s+1\b|lecture\s+1\b|first lecture", blob, re.I):
            first = link
            break
    picked = [first]
    if len(content) > 2:
        mid = content[len(content) // 2]
        if mid["url"] != first["url"]:
            picked.append(mid)
    return picked


def ga_label(inner: str) -> str:
    text = re.sub(r"<[^>]+>", "", inner)
    text = re.sub(r"\s+", "", text)
    text = text.replace("–", "-").replace("—", "-").replace("/", "")
    return text.lower()


def parse_ga_map(page: str) -> dict[str, str]:
    found = {}
    for href, inner in re.findall(
        r'(?is)<a href="(/(?:Books|Lectures|Articles)/[^"]+)"[^>]*>(.*?)</a>', page
    ):
        if "GA" not in href and "/GA" not in href.upper() and not re.search(r"/GA", href, re.I):
            continue
        label = ga_label(inner)
        if not re.fullmatch(r"\d+[a-z]*", label):
            continue
        found.setdefault(label, urllib.parse.urljoin(BASE + "/", href))
    return found


def explicit_keys(cw: str) -> list[str]:
    key = cw.lower().replace(" ", "")
    if key in SPECIAL_GA:
        return list(SPECIAL_GA[key])
    keys = [key]
    match = re.fullmatch(r"(\d+)-(\d+)", key)
    if match:
        num, suffix = match.group(1), int(match.group(2))
        if suffix < 10 and suffix in ROMAN:
            keys.append(f"{num}{ROMAN[suffix]}")
        else:
            keys.extend([num, str(suffix)])
    return keys


def resolve_volumes(cw: str | None, ga_map: dict[str, str]) -> list[str]:
    if not cw:
        return []
    urls = []
    for key in explicit_keys(cw):
        url = ga_map.get(key)
        if url and url not in urls:
            urls.append(url)
    if urls:
        return urls
    num = re.match(r"\d+", cw)
    if not num:
        return []
    number = num.group(1)
    if number in ga_map:
        return [ga_map[number]]
    for key, url in sorted(ga_map.items()):
        if re.fullmatch(number + r"[a-z]+", key) and url not in urls:
            urls.append(url)
    return urls


def year_label(album: dict) -> str:
    span = album.get("year_range") or []
    if len(span) == 2:
        return str(span[0]) if span[0] == span[1] else f"{span[0]}–{span[1]}"
    if album.get("year"):
        return str(album["year"])
    return "undated"


def cw_label(album: dict) -> str:
    return f"CW {album['cw']}" if album.get("cw") else "Compilation"


def place_phrase(places: list[str]) -> str:
    clean = [p for p in places if p]
    if not clean:
        return ""
    if len(clean) == 1:
        return f" in {clean[0]}"
    return " in " + ", ".join(clean[:-1]) + f" and {clean[-1]}"


def catalog_summary(album: dict, note: str) -> str:
    titles = []
    for track in album.get("tracks") or []:
        title = squash(track.get("short") or track.get("title") or "")
        if title and title not in titles:
            titles.append(title)
        if len(titles) >= 6:
            break
    themes = ", ".join(album.get("themes") or []) or "General"
    listed = "; ".join(titles) if titles else "the episode titles in the catalog"
    hours = (album.get("total_duration_s") or 0) / 3600
    return (
        f"{album['title']} ({cw_label(album)}, {year_label(album)}"
        f"{place_phrase(album.get('locations') or [])}) is a {album.get('section') or 'catalog'} "
        f"recording in the Rudolf Steiner Audio library: {album.get('episode_count')} tracks "
        f"read by Dale B. Brunsvold"
        f"{f', about {hours:.1f} hours' if hours else ''}. "
        f"Topics tagged for this album: {themes}. "
        f"Recording titles include: {listed}. {note} "
        f"Audio transcripts of these recordings are not part of this index."
    )


def enrich_lecture_titles(lectures: list[dict], tracks: list[dict]) -> list[dict]:
    """Prefer the catalog's descriptive episode title when the archive only says 'Lecture I'."""
    by_date: dict[str, str] = {}
    for track in tracks:
        date = track.get("lecture_date")
        raw = squash(track.get("short") or "")
        raw = re.sub(r"\([^)]*\)", " ", raw)
        raw = re.sub(r"(?i)^(?:lecture|chapter|part|section|discussion)\s+\d+\s*:\s*", "", raw)
        raw = squash(raw)
        if date and raw and not is_generic_title(raw):
            by_date.setdefault(date, raw)
    for lecture in lectures:
        replacement = by_date.get(lecture.get("date") or "")
        if replacement and is_generic_title(lecture.get("title") or ""):
            lecture["title"] = replacement
    return lectures


def compose_summary(album: dict, archive_title: str | None, editorial: str, lectures: list[dict], excerpts: list[dict]) -> str:
    title = display_heading(album, archive_title)
    places = []
    for lecture in lectures:
        if lecture.get("place") and lecture["place"] not in places:
            places.append(lecture["place"])
    if not places:
        places = list(album.get("locations") or [])
    named = []
    for lecture in lectures:
        label = lecture.get("title")
        if label and label not in named:
            named.append(label)
        if len(named) >= 8:
            break
    hours = (album.get("total_duration_s") or 0) / 3600
    parts = [
        f"{title} ({cw_label(album)}, {year_label(album)}{place_phrase(places[:4])}) "
        f"is available in this library as {album.get('episode_count')} recordings "
        f"read by Dale B. Brunsvold"
        f"{f' (about {hours:.1f} hours)' if hours else ''}, "
        f"in the Gesamtausgabe section {album.get('section') or 'unspecified'}."
    ]
    sentence = first_sentence(editorial, 420) if editorial else None
    if sentence:
        parts.append(f"The Rudolf Steiner Archive introduces the volume in these words: {sentence}")
    if named:
        parts.append("Archive lecture or chapter titles include: " + "; ".join(named) + ".")
    if excerpts:
        opening = excerpts[0]
        quoted = first_sentence(opening.get("text") or "", 320)
        where = ", ".join(bit for bit in (opening.get("date"), opening.get("place")) if bit)
        if quoted:
            parts.append(
                f"An opening passage of the archive text “{opening.get('title') or title}”"
                f"{f' ({where})' if where else ''} begins: “{quoted}”"
            )
    parts.append(
        "This summary is grounded in the Rudolf Steiner Archive text and the recording titles. "
        "It is not a transcript of the audio."
    )
    return " ".join(parts)


def filter_lectures_to_tracks(lectures: list[dict], tracks: list[dict]) -> list[dict]:
    dates = {track.get("lecture_date") for track in tracks if track.get("lecture_date")}
    dated = [lecture for lecture in lectures if lecture.get("date")]
    if not dates or not dated:
        return lectures
    matched = [lecture for lecture in lectures if lecture.get("date") in dates]
    if len(matched) >= max(2, int(0.25 * len(dates))):
        return matched
    return lectures


def search_hits(page: str) -> list[dict]:
    hits = []
    seen = set()
    for href, label in re.findall(r'(?is)<a href="([^"]+)"[^>]*>(.*?)</a>', page or ""):
        if "/German/" in href or not re.search(r"/(?:Lectures|Books|Articles)/", href):
            continue
        if href in seen:
            continue
        seen.add(href)
        title = squash(clean_html(label))
        date_m = re.search(r"(18|19)\d{6}", href)
        hits.append(
            {
                "title": title,
                "url": urllib.parse.urljoin(BASE + "/", href),
                "date": (
                    f"{date_m.group(0)[:4]}-{date_m.group(0)[4:6]}-{date_m.group(0)[6:8]}"
                    if date_m
                    else None
                ),
            }
        )
    return hits


def match_compilation(album: dict, client: HttpCache) -> list[dict]:
    """Find RS Archive lectures for compilations that have no single CW number."""
    tracks = album.get("tracks") or []
    sample = tracks[:30]
    matched = []
    seen_urls = set()
    for track in sample:
        date = track.get("lecture_date")
        short = squash(track.get("short") or track.get("title") or "")
        short = re.sub(r"\([^)]*\)", " ", short)
        short = re.sub(r"(?i)^lecture\s+\d+\s*:\s*", "", short)
        words = [w for w in re.findall(r"[A-Za-z][A-Za-z'-]+", short) if len(w) > 2 and w.lower() not in {"lecture", "the", "and", "of", "its", "for"}]
        if len(words) < 2 or not date:
            continue
        best = None
        for query_words in (words[:8], words[:4]):
            query = " ".join(query_words)
            url = BASE + "/Search.php?" + urllib.parse.urlencode({"q": query, "date": date[:4]})
            page = client.get(url)
            if not page:
                continue
            candidates = [
                hit for hit in search_hits(page)
                if hit.get("date") == date and "/English/" in hit["url"] and not re.search(r"p0?[2-9]\.html$", hit["url"])
            ]
            if not candidates:
                continue
            best = max(
                candidates,
                key=lambda hit: title_overlap(short, hit.get("title") or "")
                + (0.35 if re.search(r"(?:p|n|s)0?1\.html$", hit["url"]) else 0),
            )
            break
        if not best:
            continue
        if best["url"] in seen_urls:
            continue
        seen_urls.add(best["url"])
        matched.append(
            {
                "n": track.get("lecture_no"),
                "title": best["title"] or short,
                "url": best["url"],
                "date": date,
                "place": track.get("location"),
            }
        )
    return matched


def fetch_excerpts(client: HttpCache, targets: list[dict]) -> list[dict]:
    excerpts = []
    for target in targets[:2]:
        page = client.get(target["url"])
        if not page:
            continue
        text = excerpt_text(paragraphs(article_html(page)))
        if len(text) < 80:
            continue
        excerpts.append(
            {
                "title": target.get("title"),
                "url": target["url"],
                "date": target.get("date"),
                "place": target.get("place"),
                "text": text,
            }
        )
    return excerpts


def album_stamp(album: dict) -> str:
    payload = {
        "id": album.get("id"),
        "title": album.get("title"),
        "cw": album.get("cw"),
        "tracks": [track.get("title") for track in album.get("tracks") or []],
    }
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False).encode()).hexdigest()[:16]


def build_album(album: dict, ga_map: dict[str, str], client: HttpCache, refresh: bool) -> dict:
    cache_path = CACHE / "books" / f"{re.sub(r'[^A-Za-z0-9._-]+', '_', album['id'])}.json"
    stamp = album_stamp(album)
    if cache_path.exists() and not refresh:
        cached = json.loads(cache_path.read_text(encoding="utf-8"))
        if cached.get("_stamp") == stamp:
            cached.pop("_stamp", None)
            return cached

    volumes = []
    errors = []
    for url in resolve_volumes(album.get("cw"), ga_map):
        page = client.get(url)
        if not page:
            errors.append(url)
            continue
        volumes.append(parse_volume(page, url))

    lectures = []
    editorials = []
    archive_title = None
    edition_url = None
    edition_article = None
    track_dates = {track.get("lecture_date") for track in album.get("tracks") or [] if track.get("lecture_date")}

    def volume_rank(volume: dict) -> tuple:
        matches = sum(1 for lecture in volume.get("lectures") or [] if lecture.get("date") in track_dates)
        return (matches, title_overlap(album.get("title") or "", volume.get("title") or ""))

    if volumes:
        primary = max(volumes, key=volume_rank)
        archive_title = primary.get("title")
    for volume in volumes:
        if volume.get("editorial"):
            editorials.append(volume["editorial"])
        lectures.extend(volume.get("lectures") or [])
        if not volume.get("lectures"):
            picked = pick_edition(volume.get("article") or "", album.get("title") or "")
            if picked and not edition_url:
                edition_url = picked
                edition_article = volume.get("article")

    lectures = filter_lectures_to_tracks(lectures, album.get("tracks") or [])
    # Drop duplicate urls after filtering.
    deduped = []
    seen = set()
    for lecture in lectures:
        if lecture["url"] in seen:
            continue
        seen.add(lecture["url"])
        deduped.append(lecture)
    lectures = enrich_lecture_titles(deduped, album.get("tracks") or [])

    basis = []
    if album.get("cw") and not volumes and not errors:
        basis.append("no_rsarchive_volume")
    if errors:
        basis.append("fetch_error")

    excerpts = []
    if lectures:
        basis.append("lecture_titles")
        targets = choose_texts(lectures) or lectures[:2]
        excerpts = fetch_excerpts(client, targets)
    elif edition_url:
        page = client.get(edition_url)
        links = chapter_links(page or "", edition_url) if page else []
        if not links and edition_url.endswith("/"):
            # edition landing pages sometimes link to index.html
            guess = edition_url.rstrip("/") + "/"
            page = page or ""
        targets = choose_texts(links)
        if targets:
            basis.append("chapter_titles")
            lectures = [
                {"n": i + 1, "title": link["title"], "url": link["url"], "date": None, "place": None}
                for i, link in enumerate(links[:80])
            ]
            excerpts = fetch_excerpts(client, targets)
        elif page:
            # The edition URL itself may be a single text.
            text = excerpt_text(paragraphs(article_html(page)))
            if len(text) >= 80:
                excerpts.append({"title": archive_title or album["title"], "url": edition_url, "date": None, "place": None, "text": text})

    if not lectures and not album.get("cw"):
        lectures = match_compilation(album, client)
        if lectures:
            basis.append("search_by_title_and_date")
            excerpts = excerpts or fetch_excerpts(client, lectures[:2])

    editorial = "\n\n".join(editorials)[:2500]
    if editorial:
        basis.append("rsarchive_editorial")
    if excerpts:
        basis.append("opening_excerpts")
    if not basis or basis == ["no_rsarchive_volume"] or basis == ["fetch_error"]:
        summary = catalog_summary(
            album,
            "No matching Rudolf Steiner Archive chapter was retrieved, so this note follows the catalog titles.",
        )
        basis.append("catalog_titles")
    else:
        summary = compose_summary(album, archive_title, editorial, lectures, excerpts)
        basis.append("catalog_titles")

    volume_url = volumes[0]["url"] if volumes else (lectures[0]["url"] if lectures else None)
    record = {
        "id": album["id"],
        "cw": album.get("cw"),
        "ga": album.get("ga") or album.get("cw"),
        "title": album.get("title"),
        "site_title": album.get("site_title"),
        "archive_title": archive_title,
        "year": album.get("year"),
        "years": album.get("years") or [],
        "year_range": album.get("year_range"),
        "year_label": year_label(album),
        "locations": album.get("locations") or [],
        "section": album.get("section"),
        "themes": album.get("themes") or [],
        "cover": album.get("cover"),
        "cover_src": album.get("cover_src"),
        "episode_artwork": album.get("episode_artwork"),
        "site_url": album.get("site_url"),
        "spotify_show": album.get("spotify_show"),
        "album_href": f"#/album/{album['id']}",
        "episode_count": album.get("episode_count"),
        "total_duration_s": album.get("total_duration_s"),
        "summary": summary,
        "summary_basis": basis,
        "audio_transcript": False,
        "rsarchive_url": volume_url,
        "editorial": editorial or None,
        "lectures": [
            {
                "n": lecture.get("n"),
                "title": lecture.get("title"),
                "date": lecture.get("date"),
                "place": lecture.get("place"),
                "url": lecture.get("url"),
            }
            for lecture in lectures
        ],
        "excerpts": excerpts,
        "tracks": [
            {
                "n": index + 1,
                "title": track.get("title"),
                "short": track.get("short"),
                "lecture_no": track.get("lecture_no"),
                "lecture_date": track.get("lecture_date"),
                "lecture_year": track.get("lecture_year"),
                "location": track.get("location"),
                "duration_s": track.get("duration_s"),
                "mp3": track.get("mp3"),
                "spotify_url": track.get("spotify_url"),
                "spotify_id": track.get("spotify_id"),
                "podbean_url": track.get("podbean_url"),
                "play_href": f"#/album/{album['id']}/{index}",
            }
            for index, track in enumerate(album.get("tracks") or [])
        ],
    }
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cached = dict(record)
    cached["_stamp"] = stamp
    cache_path.write_text(json.dumps(cached, ensure_ascii=False), encoding="utf-8")
    return record


def passages_for(book: dict) -> list[dict]:
    rows = []

    def add(kind: str, text: str, **extra):
        text = squash(text)
        if len(text) < 40:
            return
        rows.append(
            {
                "id": f"{book['id']}:{kind}:{len(rows)}",
                "book_id": book["id"],
                "cw": book.get("cw"),
                "kind": kind,
                "title": book.get("title"),
                "text": text[:8000],
                "url": extra.get("url") or book.get("rsarchive_url"),
                "lecture_title": extra.get("lecture_title"),
                "lecture_date": extra.get("lecture_date"),
                "place": extra.get("place"),
                "themes": book.get("themes") or [],
                "section": book.get("section"),
            }
        )

    header = (
        f"{cw_label(book)}. {book.get('title')}. "
        f"Section: {book.get('section') or ''}. "
        f"Topics: {', '.join(book.get('themes') or [])}. "
        f"Years: {book.get('year_label')}. "
        f"Places: {', '.join(book.get('locations') or [])}."
    )
    lecture_lines = []
    for lecture in book.get("lectures") or []:
        bits = [lecture.get("title") or "", lecture.get("date") or "", lecture.get("place") or ""]
        lecture_lines.append(" ".join(bit for bit in bits if bit))
    add(
        "summary",
        " ".join(
            part
            for part in (
                header,
                book.get("summary") or "",
                ("Archive introduction: " + book["editorial"]) if book.get("editorial") else "",
                ("Lectures and chapters: " + " | ".join(lecture_lines[:60])) if lecture_lines else "",
            )
            if part
        ),
        url=book.get("rsarchive_url"),
    )
    for excerpt in book.get("excerpts") or []:
        where = " ".join(bit for bit in (excerpt.get("date"), excerpt.get("place")) if bit)
        add(
            "excerpt",
            f"{header} Archive text: {excerpt.get('title') or ''} {where}. {excerpt.get('text') or ''}",
            url=excerpt.get("url"),
            lecture_title=excerpt.get("title"),
            lecture_date=excerpt.get("date"),
            place=excerpt.get("place"),
        )
    lines = []
    for track in book.get("tracks") or []:
        lines.append(
            " ".join(
                bit
                for bit in (
                    f"Track {track.get('n')}",
                    track.get("short") or track.get("title"),
                    track.get("lecture_date") or "",
                    track.get("location") or "",
                )
                if bit
            )
        )
    for offset in range(0, len(lines), 40):
        add("tracks", header + " Recordings: " + " | ".join(lines[offset : offset + 40]))
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the Steiner research index")
    parser.add_argument("--catalog", default=str(ROOT / "catalog.json"))
    parser.add_argument("--only", help="Comma-separated album ids")
    parser.add_argument("--refresh", action="store_true", help="Ignore per-book cache")
    parser.add_argument("--delay", type=float, default=0.12)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()

    catalog = json.loads(Path(args.catalog).read_text(encoding="utf-8"))
    albums = catalog["albums"]
    if args.only:
        wanted = {item.strip() for item in args.only.split(",") if item.strip()}
        albums = [album for album in albums if album["id"] in wanted]
        missing = wanted - {album["id"] for album in albums}
        if missing:
            print("unknown album ids:", ", ".join(sorted(missing)), file=sys.stderr)
            return 2

    client = HttpCache(CACHE, delay=args.delay, concurrency=max(1, args.workers))
    print("fetching RS Archive volume list…", flush=True)
    volumes_page = client.get(BASE + "/Volumes.html")
    if not volumes_page:
        print("could not fetch Volumes.html and no cache is present", file=sys.stderr)
        return 1
    ga_map = parse_ga_map(volumes_page)
    print(f"GA labels: {len(ga_map)}; albums: {len(albums)}", flush=True)

    books = []
    for index, album in enumerate(albums, 1):
        print(f"[{index}/{len(albums)}] CW {album.get('cw') or '—'} {album['id']}", flush=True)
        try:
            books.append(build_album(album, ga_map, client, args.refresh))
        except Exception as exc:  # noqa: BLE001
            print(f"  error {album['id']}: {exc}", flush=True)
            books.append(
                {
                    "id": album["id"],
                    "cw": album.get("cw"),
                    "title": album.get("title"),
                    "summary": catalog_summary(album, f"Indexing failed ({exc})."),
                    "summary_basis": ["error"],
                    "audio_transcript": False,
                    "tracks": [],
                    "lectures": [],
                    "excerpts": [],
                    "themes": album.get("themes") or [],
                    "section": album.get("section"),
                    "cover": album.get("cover"),
                    "album_href": f"#/album/{album['id']}",
                    "year_label": year_label(album),
                    "locations": album.get("locations") or [],
                    "episode_count": album.get("episode_count"),
                    "total_duration_s": album.get("total_duration_s"),
                }
            )

    passages = [passage for book in books for passage in passages_for(book)]
    out_dir = Path(__file__).resolve().parent
    catalog_hash = hashlib.sha256(Path(args.catalog).read_bytes()).hexdigest()
    index = {
        "built_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "audio_transcripts": False,
        "catalog_sha256": catalog_hash,
        "notes": (
            "Research index of the Rudolf Steiner Audio library. Summaries are grounded in "
            "rsarchive.org public-domain texts (volume introductions, lecture/chapter titles, "
            "and short opening excerpts) plus catalog recording titles. They are not transcripts "
            "of the Dale B. Brunsvold readings. Rebuild with research/build_research_index.py."
        ),
        "sources": {
            "catalog": "catalog.json",
            "rsarchive": BASE,
            "audio": catalog.get("source"),
        },
        "stats": {
            "books": len(books),
            "tracks": sum(len(book.get("tracks") or []) for book in books),
            "passages": len(passages),
            "with_excerpts": sum(1 for book in books if book.get("excerpts")),
            "with_lectures_or_chapters": sum(1 for book in books if book.get("lectures")),
            "with_editorial": sum(1 for book in books if book.get("editorial")),
            "catalog_only": sum(1 for book in books if "opening_excerpts" not in (book.get("summary_basis") or []) and "rsarchive_editorial" not in (book.get("summary_basis") or [])),
        },
        "books": books,
    }
    index_path = out_dir / "index.json"
    passages_path = out_dir / "passages.jsonl"
    index_path.write_text(json.dumps(index, ensure_ascii=False, indent=1), encoding="utf-8")
    with passages_path.open("w", encoding="utf-8") as handle:
        for passage in passages:
            handle.write(json.dumps(passage, ensure_ascii=False) + "\n")
    print(json.dumps(index["stats"], indent=2), flush=True)
    print(f"wrote {index_path} ({index_path.stat().st_size} bytes)", flush=True)
    print(f"wrote {passages_path} ({passages_path.stat().st_size} bytes)", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
