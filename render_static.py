import json,html
d=json.load(open('app/data/catalog.json'))
items=''.join(f'<li><a href="#/album/{a["id"]}">{"CW "+a["cw"] if a["cw"] else "Compilation"} — {html.escape(a["title"])}</a> ({a["year_range"][0] if a["year_range"] else ""}{"–"+str(a["year_range"][1]) if a["year_range"] and a["year_range"][1]!=a["year_range"][0] else ""}, {a["episode_count"]} tracks)</li>' for a in d['albums'])
block=f'<div class="loading">Loading catalog…</div><noscript><h1>Rudolf Steiner Audio — {len(d["albums"])} books &amp; lecture cycles</h1><ul id="static-albums">{items}</ul></noscript>'
s=open('app/index.html').read()
import re
s=re.sub(r'<main id="view">.*?</main>',lambda m:f'<main id="view">{block}</main>',s,flags=re.S)
open('app/index.html','w').write(s)
print(len(d['albums']))
