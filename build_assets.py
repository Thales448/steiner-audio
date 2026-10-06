"""Download publisher book covers, resize to JPEG, write slim front-end catalog."""
import json,os,io,urllib.request,concurrent.futures as cf
from PIL import Image
d=json.load(open('catalog.json'))
os.makedirs('app/img',exist_ok=True); os.makedirs('app/data',exist_ok=True)
def get(a):
    out=f"img/{a['id']}.jpg"
    try:
        raw=urllib.request.urlopen(urllib.request.Request(a['cover_src'],headers={'User-Agent':'Mozilla/5.0'}),timeout=30).read()
        im=Image.open(io.BytesIO(raw)).convert('RGB')
    except Exception:
        raw=urllib.request.urlopen(a['episode_artwork'],timeout=30).read(); im=Image.open(io.BytesIO(raw)).convert('RGB')
    w,h=im.size; s=420/max(h,1)
    if s<1: im=im.resize((max(1,int(w*s)),420),Image.LANCZOS)
    im.save('app/'+out,'JPEG',quality=82,optimize=True,progressive=True)
    return a['id'],(out,)+im.size
with cf.ThreadPoolExecutor(8) as ex: res=dict(ex.map(get,d['albums']))
for a in d['albums']: a['cover'],a['cover_w'],a['cover_h']=res[a['id']]
json.dump(d,open('catalog.json','w'),ensure_ascii=False,indent=1)
keep_a=['id','title','cw','site_title','site_url','cover','cover_w','cover_h','year','years','year_range','year_source','locations','section','themes','episode_count','total_duration_s','released_first','released_last','complete','episode_artwork']
keep_t=['title','short','lecture_no','lecture_date','lecture_year','location','duration_s','mp3','released','spotify_id','podbean_url','end_of_book']
slim=dict(source=d['source'],albums=[dict({k:a[k] for k in keep_a},tracks=[{k:t[k] for k in keep_t} for t in a['tracks']]) for a in d['albums']])
json.dump(slim,open('app/data/catalog.json','w'),ensure_ascii=False,separators=(',',':'))
print('albums',len(d['albums']))
