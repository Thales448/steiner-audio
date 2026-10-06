'use strict';
const $=s=>document.querySelector(s), esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fmt=s=>{s=Math.round(s||0);const h=Math.floor(s/3600),m=Math.floor(s%3600/60),x=s%60;return h?`${h}:${String(m).padStart(2,'0')}:${String(x).padStart(2,'0')}`:`${m}:${String(x).padStart(2,'0')}`};
const hrs=s=>{const h=s/3600;return h>=1?`${h.toFixed(h<10?1:0)} h`:`${Math.round(s/60)} min`};
const yr=a=>a.year_range?(a.year_range[0]===a.year_range[1]?`${a.year_range[0]}`:`${a.year_range[0]}–${a.year_range[1]}`):'undated';
const cwLabel=a=>a.cw?`CW ${a.cw}`:'Compilation';
const cwNum=a=>a.cw?parseInt(a.cw,10)+(/[a-z]/.test(a.cw)?.5:0)+(a.cw.includes('-')?parseInt(a.cw.split('-')[1],10)/1000:0):9999;
let DB=null,BY={},YEARS=[],state={g:'none',sort:'cw',y:'',sec:'',th:'',loc:''};
const SECTIONS_ORDER=['Written Works','Essays & Collected Writings','Public Lectures','Lectures to Members','Anthroposophical Movement & Esoteric Lessons','Art: Eurythmy, Speech, Music, Architecture, Colour','Education','Medicine & Therapy','Natural Science & Agriculture','Social Life & Economics',"Christian Community (Priests' Courses)",'Lectures to Workers at the Goetheanum','Compilations'];

fetch('data/catalog.json').then(r=>r.json()).then(d=>{DB=d;
  d.albums.forEach(a=>{BY[a.id]=a;a._text=(a.title+' '+(a.site_title||'')+' '+(a.cw?('cw '+a.cw+' ga '+a.cw+' cw'+a.cw+' ga'+a.cw):'')+' '+a.locations.join(' ')+' '+a.section+' '+a.themes.join(' ')).toLowerCase();
    a.tracks.forEach((t,i)=>{t._a=a;t._i=i;t._text=(t.title+' '+(t.location||'')).toLowerCase()})});
  const ys=new Set();d.albums.forEach(a=>(a.years||[]).forEach(y=>ys.add(y)));
  const mn=Math.min(...ys),mx=Math.max(...ys);YEARS=[];for(let y=mn;y<=mx;y++)YEARS.push(y);
  window.addEventListener('hashchange',route);route();restorePlayer();
}).catch(e=>{$('#view').innerHTML=`<div class="loading">Could not load catalog: ${esc(e)}</div>`});

function parseHash(){const h=location.hash.slice(1)||'/';const [p,qs]=h.split('?');return{path:p.split('/').filter(Boolean),qs:new URLSearchParams(qs||'')}}
function setQS(patch){Object.assign(state,patch);const qs=new URLSearchParams();for(const k of ['g','sort','y','sec','th','loc'])if(state[k]&&!(k==='g'&&state[k]==='none')&&!(k==='sort'&&state[k]==='cw'))qs.set(k,state[k]);
  const q=$('#q').value.trim();if(q)qs.set('q',q);const s=qs.toString();const nh='#/'+(s?'?'+s:'');if(location.hash!==nh)history.replaceState(null,'',nh);renderLibrary()}
function route(){const {path,qs}=parseHash();window.scrollTo(0,0);
  if(path[0]==='album'&&BY[path[1]])return renderAlbum(BY[path[1]],path[2]);
  if(path[0]==='ask')return renderAsk();
  if(path[0]==='about')return renderAbout();
  for(const k of ['g','sort','y','sec','th','loc'])state[k]=qs.get(k)||({g:'none',sort:'cw'}[k]||'');
  if(qs.get('q')!==null)$('#q').value=qs.get('q');renderLibrary()}
let qt;$('#q').addEventListener('input',()=>{clearTimeout(qt);qt=setTimeout(()=>{if(parseHash().path[0])location.hash='#/?q='+encodeURIComponent($('#q').value);else setQS({})},150)});

function filtered(){const q=$('#q').value.trim().toLowerCase(),terms=q.split(/\s+/).filter(Boolean);
  let list=DB.albums.filter(a=>(!state.y||(a.years||[]).includes(+state.y))&&(!state.sec||a.section===state.sec)&&(!state.th||a.themes.includes(state.th))&&(!state.loc||a.locations.includes(state.loc)));
  let eps=[];
  if(terms.length){const albumHit=a=>terms.every(t=>a._text.includes(t));
    eps=list.flatMap(a=>a.tracks).filter(t=>terms.every(w=>t._text.includes(w)||t._a._text.includes(w)));
    const epAlbums=new Set(eps.map(t=>t._a.id));list=list.filter(a=>albumHit(a)||epAlbums.has(a.id));
    eps=eps.filter(t=>!albumHit(t._a)||terms.every(w=>t._text.includes(w)))}
  const S={cw:(a,b)=>cwNum(a)-cwNum(b),year:(a,b)=>(a.year||9999)-(b.year||9999)||cwNum(a)-cwNum(b),title:(a,b)=>a.title.localeCompare(b.title),
    added:(a,b)=>b.released_last.localeCompare(a.released_last),size:(a,b)=>b.episode_count-a.episode_count};
  list.sort(S[state.sort]||S.cw);return{list,eps}}
function count(key,list){const c={};list.forEach(a=>[].concat(a[key]).forEach(v=>c[v]=(c[v]||0)+1));return c}
function card(a){return `<a class="card" href="#/album/${a.id}"><div class="art"><img loading="lazy" src="${a.cover}" alt="${esc(a.title)}"><span class="badge">${esc(cwLabel(a))}</span><button class="playov" data-play="${a.id}" title="Play">▶</button></div>
  <div class="t">${esc(a.title)}</div><div class="s">${yr(a)} · ${a.episode_count} ${a.episode_count==1?'track':'tracks'} · ${hrs(a.total_duration_s)}</div></a>`}
function renderLibrary(){const {list,eps}=filtered(),all=DB.albums;
  const yc={};all.filter(a=>(!state.sec||a.section===state.sec)&&(!state.th||a.themes.includes(state.th))).forEach(a=>(a.years||[]).forEach(y=>yc[y]=(yc[y]||0)+1));
  const mx=Math.max(1,...Object.values(yc));
  const th=count('themes',all),sec=count('section',all),loc=count('locations',all);
  const totalEp=list.reduce((s,a)=>s+a.episode_count,0),totalS=list.reduce((s,a)=>s+a.total_duration_s,0);
  let h=`<div class="stats"><b>${list.length}</b> books & lecture cycles · <b>${totalEp}</b> recordings · <b>${Math.round(totalS/3600)}</b> hours — Rudolf Steiner Audio, read by Dale B. Brunsvold</div>
  <div class="controls"><span class="lbl">Group</span><div class="seg" id="seg-g">${[['none','Series (CW)'],['year','Year'],['section','GA section'],['theme','Topic'],['loc','Place']].map(([k,l])=>`<button data-g="${k}" class="${state.g===k?'on':''}">${l}</button>`).join('')}</div>
  <span class="lbl">Sort</span><select id="sort">${[['cw','CW / GA number'],['year','Lecture year'],['title','Title'],['added','Recently added'],['size','Most tracks']].map(([k,l])=>`<option value="${k}" ${state.sort===k?'selected':''}>${l}</option>`).join('')}</select>
  <select id="sec"><option value="">All GA sections</option>${SECTIONS_ORDER.filter(s=>sec[s]).map(s=>`<option ${state.sec===s?'selected':''}>${esc(s)}</option>`).join('')}</select>
  <select id="loc"><option value="">All places</option>${Object.entries(loc).filter(([,n])=>n>1).sort((a,b)=>b[1]-a[1]).map(([s,n])=>`<option value="${esc(s)}" ${state.loc===s?'selected':''}>${esc(s)} (${n})</option>`).join('')}</select>
  ${(state.y||state.sec||state.th||state.loc||$('#q').value)?'<button class="chip" id="clear">✕ Clear filters</button>':''}</div>
  <div class="timeline">${YEARS.map(y=>`<div class="bar ${state.y==y?'on':''} ${yc[y]?'':'zero'}" data-y="${y}" title="${y}: ${yc[y]||0} cycles" style="height:${yc[y]?8+92*yc[y]/mx:3}%"></div>`).join('')}</div>
  <div class="tl-labels">${YEARS.map(y=>`<span>${y%5==0||state.y==y?y:''}</span>`).join('')}</div>
  <div class="chips">${Object.entries(th).sort((a,b)=>b[1]-a[1]).map(([t,n])=>`<span class="chip ${state.th===t?'on':''}" data-th="${esc(t)}">${esc(t)}<span class="n">${n}</span></span>`).join('')}</div>`;
  if(!list.length)h+='<div class="loading">Nothing matches.</div>';
  else if(state.g==='none')h+=`<div class="grid">${list.map(card).join('')}</div>`;
  else{const groups=new Map();const key={year:a=>[a.year||'Undated'],section:a=>[a.section],theme:a=>a.themes,loc:a=>a.locations.length?[a.locations[0]]:['Unknown place']}[state.g];
    list.forEach(a=>key(a).forEach(k=>{if(!groups.has(k))groups.set(k,[]);groups.get(k).push(a)}));
    let keys=[...groups.keys()];
    if(state.g==='year')keys.sort((a,b)=>(a==='Undated')-(b==='Undated')||a-b);else if(state.g==='section')keys.sort((a,b)=>SECTIONS_ORDER.indexOf(a)-SECTIONS_ORDER.indexOf(b));else keys.sort((a,b)=>groups.get(b).length-groups.get(a).length);
    h+=keys.map(k=>{const g=groups.get(k);return `<section class="group"><h2>${esc(k)}<small>${g.length} · ${g.reduce((s,a)=>s+a.episode_count,0)} recordings</small></h2><div class="grid">${g.map(card).join('')}</div></section>`}).join('')}
  if(eps.length)h+=`<section class="eplist-search"><h2>Matching recordings <small style="color:var(--mut)">(${eps.length})</small></h2><div class="tracks">${eps.slice(0,80).map(t=>trackRow(t,true)).join('')}</div></section>`;
  $('#view').innerHTML=h;
  $('#seg-g').onclick=e=>{const b=e.target.closest('button');if(b)setQS({g:b.dataset.g})};
  $('#sort').onchange=e=>setQS({sort:e.target.value});$('#sec').onchange=e=>setQS({sec:e.target.value});$('#loc').onchange=e=>setQS({loc:e.target.value});
  document.querySelectorAll('.bar[data-y]').forEach(b=>b.onclick=()=>{if(b.classList.contains('zero'))return;setQS({y:state.y==b.dataset.y?'':b.dataset.y})});
  document.querySelectorAll('.chip[data-th]').forEach(c=>c.onclick=()=>setQS({th:state.th===c.dataset.th?'':c.dataset.th}));
  const cl=$('#clear');if(cl)cl.onclick=()=>{$('#q').value='';setQS({y:'',sec:'',th:'',loc:''})};bindPlay()}
function trackRow(t,showAlbum){const a=t._a;const now=P.t===t;
  return `<div class="tr ${now?'now':''}" data-a="${a.id}" data-i="${t._i}"><div class="no">${t.lecture_no??(t._i+1)}</div>
  <div><div class="tt">${esc(t.short||t.title)}</div><div class="ts">${[showAlbum?`<a href="#/album/${a.id}">${esc(cwLabel(a))} · ${esc(a.title)}</a>`:'',t.lecture_date||t.lecture_year||'',t.location||''].filter(Boolean).map(x=>typeof x==='string'&&x.startsWith('<a')?x:esc(x)).join(' · ')}${t.end_of_book?' · <i>end of book</i>':''}</div></div>
  <div class="d">${fmt(t.duration_s)}</div><div class="ops"><button class="ib" data-mp3="${a.id}:${t._i}" title="Play full recording (MP3)">▶ Play</button>${t.spotify_id?`<button class="ib sp" data-sp="${t.spotify_id}" title="Load in Spotify player">Spotify</button>`:''}</div></div>`}
function bindPlay(){document.querySelectorAll('[data-play]').forEach(b=>b.onclick=e=>{e.preventDefault();e.stopPropagation();playAlbum(BY[b.dataset.play],0)});
  document.querySelectorAll('[data-mp3]').forEach(b=>b.onclick=e=>{e.preventDefault();const [id,i]=b.dataset.mp3.split(':');playAlbum(BY[id],+i)});
  document.querySelectorAll('[data-sp]').forEach(b=>b.onclick=e=>{e.preventDefault();const em=$('#embed');if(em){em.innerHTML=spEmbed(b.dataset.sp);em.scrollIntoView({behavior:'smooth',block:'center'})}else window.open('https://open.spotify.com/episode/'+b.dataset.sp,'_blank')})}
const spEmbed=id=>`<iframe src="https://open.spotify.com/embed/episode/${id}?utm_source=generator&theme=0" height="232" allow="autoplay; clipboard-write; encrypted-media; fullscreen; picture-in-picture" loading="lazy"></iframe>`;
function renderAlbum(a,ti){document.title=`${a.title} — Steiner Audio Library`;
  const first=a.tracks.find(t=>t.spotify_id);const rel=DB.albums.filter(b=>b!==a&&(b.section===a.section)&&b.year&&a.year&&Math.abs(b.year-a.year)<=1).slice(0,12);
  $('#view').innerHTML=`<a class="back" href="javascript:history.length>1?history.back():location.hash='#/'">← Library</a>
  <div class="detail"><div class="cover"><img src="${a.cover}" alt="${esc(a.title)}"></div><div>
  <div class="lbl">${esc(a.section)}</div><h1>${esc(a.title)}</h1>
  ${a.site_title&&a.site_title!==a.title?`<div class="note" style="margin:0">${esc(a.site_title)}</div>`:''}
  <div class="meta"><a class="pill" href="#/?sort=cw&q=${encodeURIComponent(a.cw?'cw '+a.cw:a.title)}"><b>${esc(cwLabel(a))}</b></a>
  <a class="pill" href="#/?g=year&y=${a.year||''}">Given <b>${yr(a)}</b>${a.year_source&&a.year_source.startsWith('GA')?' (GA ref.)':''}</a>
  ${a.locations.slice(0,4).map(l=>`<a class="pill" href="#/?loc=${encodeURIComponent(l)}">${esc(l)}</a>`).join('')}
  <span class="pill"><b>${a.episode_count}</b> tracks · ${hrs(a.total_duration_s)}</span>${a.complete?'<span class="pill">complete book</span>':''}
  ${a.themes.map(t=>`<a class="pill" href="#/?th=${encodeURIComponent(t)}">${esc(t)}</a>`).join('')}
  <span class="pill">Published ${a.released_first.slice(0,4)}${a.released_last.slice(0,4)!==a.released_first.slice(0,4)?'–'+a.released_last.slice(0,4):''}</span></div>
  <div class="actions"><button class="btn pri" data-play="${a.id}">▶ Play all (full MP3)</button>
  ${first?`<a class="btn sp" target="_blank" rel="noopener" href="https://open.spotify.com/episode/${first.spotify_id}">Open on Spotify ↗</a>`:''}
  ${a.site_url?`<a class="btn" target="_blank" rel="noopener" href="${a.site_url}">rudolfsteineraudio.com ↗</a>`:''}</div>
  ${first?`<div class="embed" id="embed">${spEmbed(first.spotify_id)}</div><div class="note">Spotify player shows one episode at a time — pick any track's “Spotify” button to load it. Full-length playback in the Spotify embed needs you to be logged in to Spotify in this browser; the ▶ Play buttons stream the publisher's full MP3 directly.</div>`:''}
  <div class="tracks">${a.tracks.map(t=>trackRow(t,false)).join('')}</div>
  ${rel.length?`<div class="related"><h3>Same section, around ${a.year}</h3><div class="grid">${rel.map(card).join('')}</div></div>`:''}
  </div></div>`;bindPlay();
  if(ti!==undefined&&a.tracks[+ti])playAlbum(a,+ti)}
const ASK_PROMPTS=['What is anthroposophy?','Recommend lectures on karma','What did Steiner say about education?'];
const chat={messages:[],busy:false};
function renderAsk(){document.title='Ask — Steiner Audio Library';
  const thread=chat.messages.map(m=>m.role==='user'
    ?`<div class="msg user"><div class="bubble">${esc(m.text)}</div></div>`
    :`<div class="msg bot"><div class="bubble">${answerHtml(m.data)}</div></div>`).join('');
  $('#view').innerHTML=`<div class="ask"><h1>Ask the library</h1>
  <p class="note">Answers come from a research index of these recordings and the public-domain texts at the Rudolf Steiner Archive. They cite CW numbers and link to the album pages. They are not transcripts of the readings.</p>
  <div class="prompts">${ASK_PROMPTS.map(p=>`<button type="button" class="chip askq">${esc(p)}</button>`).join('')}</div>
  <div id="thread" class="thread">${thread||'<div class="note">Try a question above, or ask about karma, education, the Gospels, or a CW number.</div>'}</div>
  <form id="askform" class="askform"><textarea id="askq" rows="3" placeholder="Ask about a book, a theme, or a lecture…" ${chat.busy?'disabled':''}></textarea>
  <button class="btn pri" type="submit" ${chat.busy?'disabled':''}>${chat.busy?'Thinking…':'Ask'}</button></form></div>`;
  document.querySelectorAll('.askq').forEach(b=>b.onclick=()=>submitAsk(b.textContent));
  $('#askform').onsubmit=e=>{e.preventDefault();const v=$('#askq').value.trim();if(v)submitAsk(v)};
  const box=$('#askq');if(box&&!chat.busy)box.focus()}
function answerHtml(d){if(!d)return '';
  let h=d.notice?`<div class="banner">${esc(d.notice)}</div>`:'';
  h+=`<div class="prose">${esc(d.answer||'')}</div>`;
  if(d.recommendations&&d.recommendations.length){h+=`<h3>Recommended in this library</h3><div class="recs">${d.recommendations.map(r=>{const play=r.track&&r.track.play_href?`<a class="playlink" href="${esc(r.track.play_href)}">Play ${esc(r.track.title||'recording')}</a>`:'';return `<div class="rec"><a class="rec-main" href="${esc(r.href)}"><img src="${esc(r.cover||'')}" alt=""><span><b>${esc(r.cw?('CW '+r.cw):'Compilation')}</b> ${esc(r.title||'')}<span class="s">${esc([r.year_label,r.section].filter(Boolean).join(' · '))}</span></span></a>${play}</div>`}).join('')}</div>`}
  if(d.citations&&d.citations.length){h+=`<h3>Sources</h3><ul class="cites">${d.citations.map(c=>`<li><a href="${esc(c.album_href)}">${esc((c.cw?'CW '+c.cw+' — ':'')+(c.book_title||''))}</a>${c.lecture_title?' · '+esc(c.lecture_title):''}${c.date?' · '+esc(c.date):''}${c.place?' · '+esc(c.place):''}${c.rsarchive_url?` · <a href="${esc(c.rsarchive_url)}" target="_blank" rel="noopener">RS Archive ↗</a>`:''}</li>`).join('')}</ul>`}
  return h}
async function submitAsk(q){if(chat.busy||!q)return;chat.busy=true;chat.messages.push({role:'user',text:q});renderAsk();
  const history=chat.messages.slice(0,-1).filter(m=>m.role==='user'||m.data).slice(-6).map(m=>({role:m.role==='user'?'user':'assistant',content:m.role==='user'?m.text:(m.data&&m.data.answer)||''}));
  try{const res=await fetch('/api/ask',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({question:q,history})});
    const data=await res.json();if(!res.ok)throw new Error(data.error||('HTTP '+res.status));
    chat.messages.push({role:'assistant',data})}
  catch(err){chat.messages.push({role:'assistant',data:{mode:'error',notice:'The research API did not respond, so the library browser is all that is available right now. Locally, start python3 api/server.py with STEINER_STATIC=app.',answer:String(err.message||err),recommendations:[],citations:[]}})}
  chat.busy=false;renderAsk();const thread=$('#thread');if(thread)thread.scrollTop=thread.scrollHeight}
function renderAbout(){const d=DB.source;$('#view').innerHTML=`<div class="about"><h1>About this library</h1>
<p>A visual index of <b>Rudolf Steiner Audio</b> — ${d.episodes_rss} recordings of Rudolf Steiner's books and lecture cycles read by <b>${esc(d.reader)}</b>, grouped into <b>${DB.albums.length}</b> books / lecture cycles.</p>
<table><tr><th>Source</th><th></th></tr><tr><td>Spotify show</td><td><a href="${d.spotify_url}" target="_blank">${d.spotify_url}</a> (${d.episodes_spotify} episodes; ${d.episodes_matched} matched)</td></tr>
<tr><td>Podcast RSS (MP3 audio)</td><td><a href="${d.rss}" target="_blank">${d.rss}</a></td></tr><tr><td>Book covers & titles</td><td><a href="${d.website}" target="_blank">${d.website}</a></td></tr></table>
<h3>How it's grouped</h3><ul><li><b>Series</b> = one book / lecture cycle, keyed by its <b>CW</b> (Collected Works; German <b>GA</b>) number from the episode titles. Two compilations have no CW number.</li>
<li><b>Year</b> = year the lectures were given, parsed from dates in the episode titles (a few written works use the GA reference date). Release dates on Spotify are kept separately.</li>
<li><b>GA section</b> = the standard Gesamtausgabe ranges (1–28 written works, 51–87 public lectures, 88–253 lectures to members, 293–311 education, 312–319 medicine, 347–354 lectures to workers, …).</li>
<li><b>Topic</b> = keyword tags from titles (Christology, Karma, Esoteric Development, Cosmology, Arts, Education, …).</li></ul>
<p>Playback: ▶ buttons stream the full-length MP3 from the publisher's podcast host. The Spotify embed plays full episodes when you're logged into Spotify in this browser.</p>
<p><a href="#/ask">Ask</a> searches a research index of these recordings against the public-domain texts at the Rudolf Steiner Archive. Answers cite CW numbers and open the album pages here. They are not transcripts of the readings. A full written answer needs an API key on the server; without one, Ask still returns the closest books and the indexed summaries.</p>
<p>Please consider supporting the reader: <a href="https://rudolfsteineraudio.com/donations.html" target="_blank">rudolfsteineraudio.com/donations</a>.</p></div>`}
// ---------- player
const A=$('#audio'),P={a:null,i:0,t:null};
function playAlbum(a,i){P.a=a;P.i=i;P.t=a.tracks[i];const t=P.t;
  $('#player').classList.remove('hidden');$('#pl-img').src=a.cover;$('#pl-title').textContent=t.short||t.title;$('#pl-album').textContent=`${cwLabel(a)} · ${a.title}`;$('#pl-album').href='#/album/'+a.id;
  const sp=$('#pl-spotify');if(t.spotify_id){sp.href='https://open.spotify.com/episode/'+t.spotify_id;sp.style.display=''}else sp.style.display='none';
  A.src=t.mp3;A.playbackRate=+$('#pl-rate').value;const pos=+localStorage.getItem('pos:'+t.mp3)||0;
  A.addEventListener('loadedmetadata',()=>{if(pos>5&&pos<A.duration-10)A.currentTime=pos},{once:true});A.play().catch(()=>{});
  localStorage.setItem('last',JSON.stringify({a:a.id,i}));
  document.querySelectorAll('.tr').forEach(r=>r.classList.toggle('now',r.dataset.a===a.id&&+r.dataset.i===i));
  if('mediaSession' in navigator)navigator.mediaSession.metadata=new MediaMetadata({title:t.short||t.title,artist:'Rudolf Steiner — read by Dale B. Brunsvold',album:a.title,artwork:[{src:new URL(a.cover,location.href).href}]})}
function restorePlayer(){try{const l=JSON.parse(localStorage.getItem('last')||'null');if(l&&BY[l.a]){const a=BY[l.a],t=a.tracks[l.i];if(!t)return;P.a=a;P.i=l.i;P.t=t;$('#player').classList.remove('hidden');$('#pl-img').src=a.cover;$('#pl-title').textContent=t.short||t.title;$('#pl-album').textContent=`${cwLabel(a)} · ${a.title}`;$('#pl-album').href='#/album/'+a.id;A.src=t.mp3;$('#pl-dur').textContent=fmt(t.duration_s);if(t.spotify_id)$('#pl-spotify').href='https://open.spotify.com/episode/'+t.spotify_id;
  A.addEventListener('loadedmetadata',()=>{const p=+localStorage.getItem('pos:'+t.mp3)||0;if(p>5)A.currentTime=p},{once:true})}}catch(e){}}
$('#pl-play').onclick=()=>{if(!P.t)return;A.paused?A.play():A.pause()};
$('#pl-next').onclick=()=>{if(P.a&&P.i<P.a.tracks.length-1)playAlbum(P.a,P.i+1)};$('#pl-prev').onclick=()=>{if(P.a&&A.currentTime<5&&P.i>0)playAlbum(P.a,P.i-1);else A.currentTime=0};
$('#pl-back').onclick=()=>A.currentTime=Math.max(0,A.currentTime-15);$('#pl-fwd').onclick=()=>A.currentTime=Math.min(A.duration||1e9,A.currentTime+30);
$('#pl-rate').onchange=e=>A.playbackRate=+e.target.value;
A.onplay=()=>$('#pl-play').textContent='❚❚';A.onpause=()=>$('#pl-play').textContent='▶';A.onended=()=>{localStorage.removeItem('pos:'+A.src);$('#pl-next').click()};
let lastSave=0;A.ontimeupdate=()=>{const d=A.duration||P.t?.duration_s||0;$('#pl-cur').textContent=fmt(A.currentTime);$('#pl-dur').textContent=fmt(d);if(!seeking)$('#pl-range').value=d?1000*A.currentTime/d:0;
  if(P.t&&Date.now()-lastSave>5000){lastSave=Date.now();localStorage.setItem('pos:'+P.t.mp3,A.currentTime)}};
let seeking=false;$('#pl-range').oninput=()=>{seeking=true};$('#pl-range').onchange=e=>{seeking=false;if(A.duration)A.currentTime=A.duration*e.target.value/1000};
if('mediaSession' in navigator){navigator.mediaSession.setActionHandler('nexttrack',()=>$('#pl-next').click());navigator.mediaSession.setActionHandler('previoustrack',()=>$('#pl-prev').click())}
document.addEventListener('keydown',e=>{if(e.target.matches('input,select,textarea'))return;if(e.code==='Space'&&P.t){e.preventDefault();$('#pl-play').click()}if(e.key==='/'){e.preventDefault();$('#q').focus()}});
