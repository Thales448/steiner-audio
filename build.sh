#!/bin/sh
# Full rebuild: refresh RSS + Spotify episode list, re-index, covers, static fallback.
set -e; cd "$(dirname "$0")"
curl -sf -o feed.xml https://feed.podbean.com/rudolfsteiner/feed.xml
if [ -n "$SPOTIFY_CLIENT_ID" ]; then
  curl -s -X POST https://accounts.spotify.com/api/token -u "$SPOTIFY_CLIENT_ID:$SPOTIFY_CLIENT_SECRET" -d grant_type=client_credentials \
   | python3 -c 'import sys,json;print(json.load(sys.stdin)["access_token"])' > /tmp/sptok && chmod 600 /tmp/sptok && python3 fetch_spotify.py
fi
python3 build_index.py >/dev/null && python3 build_assets.py && python3 render_static.py
cp catalog.json app/data/catalog.full.json
