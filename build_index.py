import re, json, html, difflib, collections, xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
NS={'itunes':'http://www.itunes.com/dtds/podcast-1.0.dtd'}
SHOW_ID='3Ci1JAfMuj3fewAOfSAuKY'
MONTHS='January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec|Whitsunday'
# ---------- publisher site: CW -> titles + covers
def site_links(f):
    s=open('site/'+f,encoding='latin-1').read()
    return re.findall(r'<a href="([^"]+)"[^>]*>\s*<img src="([^"]+)"',s,re.I)
cover={}
for f in ['lecturesimagebased.html','writtenimagebased.html']:
    for h,i in site_links(f): cover[h]=i
s=open('site/texttitleCWorder.html',encoding='latin-1').read()
site=[]
for h,t in re.findall(r'<a href="([^"]+)"[^>]*>(.*?)</a>',s,re.S|re.I):
    t=re.sub(r'\s+',' ',re.sub('<[^>]+>','',html.unescape(t))).strip()
    if not t or h.startswith('http') or h.startswith('mailto'): continue
    m=re.search(r'\b(?:CW|GA)\s*([\d]+[a-z]?(?:\s*[-/,&]\s*\d+[a-z]?)*)',t)
    cws=re.findall(r'\d+[a-z]?',m.group(1)) if m else []
    m2=re.search(r'\((\d{3}[a-z])\)',t)
    if m2: cws.append(m2.group(1))
    clean=re.sub(r'\s*\((?:from |)?(?:CW|GA)[^)]*\)|\s*(?:CW|GA)\s*\d+[a-z]?\s*$','',t).strip()
    site.append(dict(href=h,title=t,clean=clean,cws=cws,cover=cover.get(h)))
by_cw=collections.defaultdict(list)
for x in site:
    for c in x['cws']: by_cw[c].append(x)
def norm(t): return re.sub(r'[^a-z0-9]+',' ',t.lower()).strip()
def site_match(cw,series):
    cands=by_cw.get(cw,[])
    if not cands and series:
        cands=site
        best=max(cands,key=lambda x:difflib.SequenceMatcher(None,norm(series),norm(x['clean'])).ratio())
        return best if difflib.SequenceMatcher(None,norm(series),norm(best['clean'])).ratio()>0.7 else None
    if not cands: return None
    if not series: return cands[0]
    return max(cands,key=lambda x:difflib.SequenceMatcher(None,norm(series),norm(x['clean'])).ratio())
# ---------- GA topic ranges (Steiner Gesamtausgabe structure)
def ga_section(cw):
    m=re.match(r'(\d+)',cw or '')
    if not m: return 'Compilations'
    n=int(m.group(1))
    for lo,hi,name in [(1,28,'Written Works'),(29,50,'Essays & Collected Writings'),(51,87,'Public Lectures'),
        (88,253,'Lectures to Members'),(254,270,'Anthroposophical Movement & Esoteric Lessons'),(271,292,'Art: Eurythmy, Speech, Music, Architecture, Colour'),
        (293,311,'Education'),(312,319,'Medicine & Therapy'),(320,327,'Natural Science & Agriculture'),(328,341,'Social Life & Economics'),
        (342,346,'Christian Community (Priests\' Courses)'),(347,354,'Lectures to Workers at the Goetheanum')]:
        if lo<=n<=hi: return name
    return 'Other'
THEMES=[('Christology & Gospels',r'christ|gospel|golgotha|jesus|matthew|mark\b|luke|john|apocalypse|revelation|fifth gospel|easter|whitsun|pentecost|christmas'),
 ('Karma & Reincarnation',r'karma|reincarnation|destin|rebirth|death|the dead|living and the dead'),
 ('Esoteric Development',r'esoteric|initiation|higher worlds|meditat|threshold|occult|mystery|mysteries|rosicrucian|grail|templar'),
 ('Cosmology & Evolution',r'cosmo|cosmic|evolution|saturn|akashic|atlant|universe|sun\b|stars|hierarch|creation|genesis|spiritual beings'),
 ('Human Being & Psychology',r'soul|psycholog|human being|body|senses|thinking|consciousness|sleep|ego\b|spirit as|man\b|anthropology|youth'),
 ('Education',r'educat|child|teacher|waldorf|curriculum|soul economy'),
 ('Medicine & Health',r'medic|healing|therap|illness|health|physiolog|epidemic|nutrition|food'),
 ('Arts',r'eurythm|speech|drama|music|art\b|artistic|colour|color|sculpt|architect|painting'),
 ('Social & Economics',r'social|econom|threefold|nation|war\b|folk souls|history|historical|symptom'),
 ('Nature & Science',r'nature|science|astronom|agricultur|plant|animal|elemental|bees|warmth|light course|physics'),
 ('Philosophy',r'philosoph|freedom|truth and knowledge|goethe|aquinas|knowledge|monism'),
 ('Festivals & Seasons',r'festival|michael|christmas|easter|whitsun|year'),
 ('Theosophy & Spiritualism',r'theosoph|blavatsky|spiritualis|buddh|gita|krishna|east in the light')]
def themes(text,section):
    t=text.lower(); out=[n for n,rx in THEMES if re.search(rx,t)]
    sec={'Education':'Education','Medicine & Therapy':'Medicine & Health','Natural Science & Agriculture':'Nature & Science','Social Life & Economics':'Social & Economics','Art: Eurythmy, Speech, Music, Architecture, Colour':'Arts','Written Works':'Philosophy'}.get(section)
    if sec and sec not in out: out.insert(0,sec)
    return out[:4] or ['General']
def album_themes(text,sec,lst):
    th=themes(text,sec)
    if th!=['General']: return th
    c=collections.Counter(n for e in lst for n,rx in THEMES if re.search(rx,e['title'].lower()))
    out=[n for n,k in c.most_common(3) if k>=2]
    return out or ['General']
# ---------- date/location parsing
DATE_RXS=[r'(\d{1,2})(?:st|nd|rd|th)?\s+('+MONTHS+r')\.?\s*,?\s+(18[6-9]\d|19[0-2]\d)',
          r'('+MONTHS+r')\.?\s+(\d{1,2})(?:st|nd|rd|th)?\s*,?\s+(18[6-9]\d|19[0-2]\d)']
MNUM={m[:3].lower():i+1 for i,m in enumerate('January February March April May June July August September October November December'.split())}
def parse_date(t):
    for i,rx in enumerate(DATE_RXS):
        m=re.search(rx,t,re.I)
        if m:
            if i==0: d,mo,y=m.groups()
            else: mo,d,y=m.groups()
            mn=MNUM.get(mo[:3].lower())
            if mn: return f'{y}-{mn:02d}-{int(d):02d}', int(y)
    m=re.search(r'\b(18[6-9]\d|19[0-2]\d)\b',t)
    return (None,int(m.group(1))) if m else (None,None)
NOTLOC=re.compile(r'\d|lecture|discussion|extract|written|address|session|part|public|insert|semi|with answers|questions|'+MONTHS,re.I)
def parse_location(t):
    for grp in re.findall(r'\(([^()]*(?:\([^()]*\)[^()]*)?)\)',t):
        if not re.search(r'18[6-9]\d|19[0-2]\d',grp): continue
        for part in re.split(r',',grp):
            p=part.strip()
            if p and not NOTLOC.search(p) and len(p)<40 and p[0].isupper(): return p
    m=re.search(r'\b(Dornach|Berlin|Stuttgart|Munich|Basel|Basle|Vienna|Kristiania|Oslo|Cologne|Hamburg|Norrkoping|Karlsruhe|Prague|London|Oxford|Torquay|Penmaenmawr|Arnhem|Breslau|Koberwitz|Kassel|Hanover|Helsingfors|Leipzig|Nuremberg|Zurich|Berne|Stockholm|Copenhagen|The Hague|Paris|Ilkley|Budapest|Bern)\b',t)
    return m.group(1) if m else None
MANUAL_YEARS={'4':[1894],'24':[1919,1920,1921],'26':[1924,1925],'27':[1925],'45':[1910],'74':[1920],'112':[1909],'128':[1911],
 '152':[1913,1914],'177':[1917],'184':[1918],'215':[1922],'229':[1923],'230':[1923],'294':[1919],'295':[1919],'315':[1921],'353':[1924]}
# ---------- episodes
root=ET.parse('feed.xml').getroot().find('channel')
show_img=root.find('itunes:image',NS).get('href')
spot=json.load(open('spotify_episodes.json'))
sp_by={}
for e in spot: sp_by.setdefault(norm(e['name']),e)
CW_RX=re.compile(r'^\s*CW\s*(\d+[a-z]?(?:\s*-\s*\d+[a-z]?)?)\s*[:.]?\s*(.*)$',re.I)
OLD_RX=re.compile(r'^\s*(?:CW\s*)?(\d+[a-z]?)\.?\s+Episode\s+\d+\s*:\s*(.*)$',re.I)
NUM_RX=re.compile(r'^\s*(\d{2,3}[a-z]?)\s+(.*)$')
UNIT=re.compile(r'\b(Lecture|Lect|Chapter|Part|Letter|Section|Discussion|Episode|Talk|Prologue|Introduction|Preface|Foreword|Appendix|Session)s?\b\.?\s*(\d+)?',re.I)
eps=[]
for it in root.findall('item'):
    title=re.sub(r'\s+',' ',it.findtext('title')).strip()
    base=re.sub(r'\s*\bby Rudolf Steiner\s*$','',title,flags=re.I).strip()
    cw=None; rest=base
    m=OLD_RX.match(base) or CW_RX.match(base) or NUM_RX.match(base)
    if m:
        cw=re.sub(r'\s+','',m.group(1)).lstrip('0') or '0'; rest=m.group(2)
    else:
        m=re.match(r'^(\d{3}[a-z]?)\s*:\s*(.*)$',base)
        if m: cw,rest=m.group(1),m.group(2)
    # series name: text before first unit marker
    um=UNIT.search(rest)
    series=rest[:um.start()] if um else rest.split(':')[0]
    series=series.strip(' :.-;')
    if OLD_RX.match(base):
        # old format: "<cw> Episode n: Lecture n: Series: subtitle" -> series after unit
        parts=[p.strip() for p in rest.split(':')]
        series=parts[1] if len(parts)>=3 and len(parts[1])>3 else ''
    lnum=None
    if um and um.group(2): lnum=int(um.group(2))
    date,year=parse_date(title)
    enc=it.find('enclosure'); im=it.find('itunes:image',NS)
    dur=it.findtext('itunes:duration',namespaces=NS)
    try: dur=int(dur)
    except: 
        try: p=[int(x) for x in dur.split(':')]; dur=sum(v*60**i for i,v in enumerate(reversed(p)))
        except: dur=None
    sp=sp_by.get(norm(title))
    pub=parsedate_to_datetime(it.findtext('pubDate'))
    eps.append(dict(title=title,short=re.sub(r'^.*?\b(?=(Lecture|Chapter|Part|Letter|Section|Discussion|Prologue)\b)','',rest,count=1,flags=re.I) if um else rest,
        cw=cw,series_raw=series,lecture_no=lnum,lecture_date=date,lecture_year=year,location=parse_location(title),
        end_of_book='[End of Book]' in title,duration_s=dur,mp3=enc.get('url') if enc is not None else None,
        episode_image=im.get('href') if im is not None else None,released=pub.date().isoformat(),
        podbean_url=it.findtext('link'),episode_no=it.findtext('itunes:episode',namespaces=NS),
        spotify_id=sp['id'] if sp else None,spotify_url=sp['external_urls']['spotify'] if sp else None,spotify_uri=sp['uri'] if sp else None,
        spotify_image=sp['images'][0]['url'] if sp and sp.get('images') else None))
# ---------- group into books/cycles
groups=collections.OrderedDict()
def gkey(e):
    if not e['cw'] and e['series_raw']:
        sm=site_match(None,e['series_raw'])
        if sm and sm['cws']: e['cw']=sm['cws'][0]
    if e['cw']: return 'cw-'+e['cw'].lower()
    return 'x-'+norm(e['series_raw'])[:40].replace(' ','-')
for e in sorted(eps,key=lambda e:e['released']):
    groups.setdefault(gkey(e),[]).append(e)
albums=[]
for k,lst in groups.items():
    cw=lst[0]['cw']
    sc=collections.Counter(e['series_raw'] for e in lst if e['series_raw'])
    series=sc.most_common(1)[0][0] if sc else ''
    sm=site_match(cw.split('-')[0] if cw and '-' in cw and not re.match(r'\d+-\d$',cw) else (cw.split('-')[0] if cw else None),series) if (cw or series) else None
    if not cw and sm and sm['cws']: cw=sm['cws'][0]
    cands=by_cw.get(cw,[]) if cw else []
    if len(cands)>1:
        words=set(norm(' '.join(e['title'] for e in lst)).split())
        sm=max(cands,key=lambda x:(len(set(norm(x['clean']).split())&words)/max(1,len(set(norm(x['clean']).split())))))
    if cw and cw.startswith('266'):
        sm=site_match('266',series) if series else None
        title=series
    else:
        title=sm['clean'] if sm else (series or f'CW {cw}')
    title=re.sub(r'\s*\[[^\]]*\]\s*$','',title).strip()
    years=sorted({e['lecture_year'] for e in lst if e['lecture_year']})
    year_source='parsed from episode titles' if years else None
    if not years and cw in MANUAL_YEARS:
        years=MANUAL_YEARS[cw]; year_source='GA reference date (not in episode titles)'
    yc=collections.Counter(e['lecture_year'] for e in lst if e['lecture_year'])
    locs=collections.Counter(e['location'] for e in lst if e['location'])
    lst.sort(key=lambda e:(e['lecture_no'] is None, e['lecture_no'] or 0, e['released']))
    imgs=collections.Counter(e['spotify_image'] or e['episode_image'] for e in lst)
    ep_img=imgs.most_common(1)[0][0]
    sec=ga_section(cw)
    slug=k[3:] if k.startswith('cw-') else k[2:]
    albums.append(dict(id=slug,title=title,cw=cw,ga=cw,site_title=sm['title'] if sm else None,
        site_url='https://rudolfsteineraudio.com/'+sm['href'] if sm else None,
        cover_src=('https://rudolfsteineraudio.com/'+sm['cover']) if sm and sm.get('cover') else None,
        episode_artwork=ep_img, artwork_is_generic=(ep_img in (show_img,) or imgs.most_common(1)[0][1]==0),
        year=(yc.most_common(1)[0][0] if yc else (years[0] if years else None)), year_source=year_source, years=years,
        year_range=[years[0],years[-1]] if years else None,
        locations=[l for l,_ in locs.most_common(5)], section=sec, themes=album_themes(title+' '+(sm['title'] if sm else ''),sec,lst),
        episode_count=len(lst), total_duration_s=sum(e['duration_s'] or 0 for e in lst),
        released_first=min(e['released'] for e in lst), released_last=max(e['released'] for e in lst),
        complete=any(e['end_of_book'] for e in lst),
        spotify_show='https://open.spotify.com/show/'+SHOW_ID,
        tracks=lst))
albums.sort(key=lambda a:(a['cw'] is None, int(re.match(r'\d+',a['cw']).group()) if a['cw'] else 0, a['cw'] or '', a['title']))
json.dump(dict(source=dict(show='Rudolf Steiner Audio',reader='Dale B. Brunsvold',spotify_show_id=SHOW_ID,
    spotify_url='https://open.spotify.com/show/'+SHOW_ID,rss='https://feed.podbean.com/rudolfsteiner/feed.xml',website='https://rudolfsteineraudio.com/',
    show_image=show_img,episodes_rss=len(eps),episodes_spotify=len(spot),episodes_matched=sum(1 for e in eps if e['spotify_id'])),
    albums=albums),open('catalog.json','w'),ensure_ascii=False,indent=1)
print('episodes',len(eps),'albums',len(albums),'matched spotify',sum(1 for e in eps if e['spotify_id']))
print('no year albums',[(a['cw'],a['title']) for a in albums if not a['years']])
print('no cw',[(a['title'],a['episode_count']) for a in albums if not a['cw']])
print('no cover',len([a for a in albums if not a['cover_src']]))
for a in albums: print(a['cw'],'|',a['title'][:60],'|',a['episode_count'],a['year_range'],a['locations'][:2],'|',(a['site_title'] or '')[:50])
