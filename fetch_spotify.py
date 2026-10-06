import json,urllib.request,time
tok=open('/tmp/sptok').read().strip()
out=[];url="https://api.spotify.com/v1/shows/3Ci1JAfMuj3fewAOfSAuKY/episodes?market=US&limit=50"
while url:
    for a in range(5):
        try:
            r=urllib.request.urlopen(urllib.request.Request(url,headers={'Authorization':'Bearer '+tok}),timeout=30);d=json.load(r);break
        except Exception as e: print('retry',e);time.sleep(3)
    out+= [i for i in d['items'] if i]; url=d.get('next')
json.dump(out,open('spotify_episodes.json','w'))
print(len(out))
