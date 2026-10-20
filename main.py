import os, io, json
from dotenv import load_dotenv
load_dotenv()
from datetime import date, datetime, timedelta
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel, Field
from .db import init_db, connect
from . import services

@asynccontextmanager
async def lifespan(app):
    init_db()
    scheduler=None
    if os.getenv('WEEKLY_REPORT_ENABLED','false').lower()=='true':
        try:
            from apscheduler.schedulers.background import BackgroundScheduler
            scheduler=BackgroundScheduler(daemon=True)
            scheduler.add_job(services.send_weekly_report,'cron',day_of_week=os.getenv('REPORT_DAY','mon'),hour=int(os.getenv('REPORT_HOUR','9')),minute=0,id='weekly-report',replace_existing=True)
            scheduler.start()
            services.log('scheduler','started','Weekly PDF email enabled')
        except Exception as e: services.log('scheduler','failed',str(e))
    yield
    if scheduler: scheduler.shutdown(wait=False)
app=FastAPI(title='Mashhad AI Studio',version='0.5.0',lifespan=lifespan)
class EpisodeIn(BaseModel):
    title:str=Field(min_length=2,max_length=160); premise:str=Field(min_length=5,max_length=5000)
class EpisodeUpdate(BaseModel):
    title:str|None=Field(default=None,min_length=2,max_length=160); premise:str|None=Field(default=None,max_length=5000); script:str|None=None; caption:str|None=None; hashtags:str|None=None; status:str|None=Field(default=None,pattern='^(idea|draft|ready|scheduled|published|archived)$'); scheduled_at:str|None=None
class MetricIn(BaseModel):
    day:str; followers:int|None=Field(default=None,ge=0); reach:int|None=Field(default=None,ge=0); reactions:int|None=Field(default=None,ge=0); comments:int|None=Field(default=None,ge=0); views:int|None=Field(default=None,ge=0); watch_time:float|None=Field(default=None,ge=0)
class BibleIn(BaseModel): world_rules:str=''; characters:str=''; continuity:str=''; forbidden_repeats:str=''
class GenerateIn(BaseModel): episode_id:int|None=None; topic:str|None=None; format:str='3D Arabic micro-drama'; duration_seconds:int=Field(default=45,ge=10,le=180)
class ReportIn(BaseModel): recipient:str|None=None

@app.get('/api/health')
def health():
 return {'status':'ok','app':'Mashhad AI Studio','version':'0.5.0','features':{'local_database':True,'mistral_text_generation':bool(os.getenv('MISTRAL_API_KEY')),'meta_read_api':bool(os.getenv('META_PAGE_ACCESS_TOKEN')),'meta_publishing_enabled':os.getenv('ENABLE_META_PUBLISHING','false').lower()=='true','smtp_configured':bool(os.getenv('SMTP_HOST') and os.getenv('REPORT_EMAIL_TO')),'video_generation':'not configured: requires a chosen provider and credentials'},'publishing_note':'No automatic publishing runs by default; external publishing is not implemented as an unattended action.'}
@app.get('/api/episodes')
def episodes():
 with connect() as c: return [dict(x) for x in c.execute('SELECT * FROM episodes ORDER BY id DESC LIMIT 200')]
@app.post('/api/episodes')
def add_episode(item:EpisodeIn):
 with connect() as c:
  cur=c.execute('INSERT INTO episodes(title,premise) VALUES(?,?)',(item.title,item.premise)); eid=cur.lastrowid
 services.log('create_episode','success',f'id={eid}')
 return {'id':eid,'title':item.title,'status':'idea'}
@app.patch('/api/episodes/{eid}')
def update_episode(eid:int,item:EpisodeUpdate):
 values=item.model_dump(exclude_unset=True)
 if not values: raise HTTPException(400,'No fields supplied')
 values['updated_at']=datetime.utcnow().isoformat(timespec='seconds')
 with connect() as c:
  if not c.execute('SELECT id FROM episodes WHERE id=?',(eid,)).fetchone(): raise HTTPException(404,'Episode not found')
  c.execute('UPDATE episodes SET '+','.join(f'{k}=?' for k in values)+' WHERE id=?',(*values.values(),eid))
 return {'saved':True,'id':eid}
@app.delete('/api/episodes/{eid}')
def delete_episode(eid:int):
 with connect() as c: cur=c.execute('DELETE FROM episodes WHERE id=?',(eid,))
 if not cur.rowcount: raise HTTPException(404,'Episode not found')
 services.log('delete_episode','success',f'id={eid}'); return {'deleted':True}
@app.get('/api/story-bible')
def get_bible():
 with connect() as c: return dict(c.execute('SELECT * FROM story_bible WHERE id=1').fetchone())
@app.put('/api/story-bible')
def save_bible(item:BibleIn):
 with connect() as c: c.execute('UPDATE story_bible SET world_rules=?,characters=?,continuity=?,forbidden_repeats=?,updated_at=CURRENT_TIMESTAMP WHERE id=1',(item.world_rules,item.characters,item.continuity,item.forbidden_repeats))
 return {'saved':True}
@app.get('/api/metrics')
def metrics():
 with connect() as c: return [dict(x) for x in c.execute('SELECT * FROM metrics ORDER BY day DESC LIMIT 180')]
@app.post('/api/metrics')
def add_metrics(item:MetricIn):
 with connect() as c:
  c.execute('INSERT INTO metrics(day,followers,reach,reactions,comments,views,watch_time) VALUES(?,?,?,?,?,?,?)',(item.day,item.followers,item.reach,item.reactions,item.comments,item.views,item.watch_time))
 return {'saved':True}
@app.post('/api/generate')
def generate(item:GenerateIn):
 with connect() as c:
  bible=dict(c.execute('SELECT * FROM story_bible WHERE id=1').fetchone())
  if item.episode_id:
   ep=c.execute('SELECT * FROM episodes WHERE id=?',(item.episode_id,)).fetchone()
   if not ep: raise HTTPException(404,'Episode not found')
   topic=ep['title']+'\nPremise: '+ep['premise']
  else: topic=item.topic or 'ابتكر فكرة جديدة وغير مكررة'
  recent='\n'.join(f"- {r['title']}: {r['premise'][:200]}" for r in c.execute('SELECT title,premise FROM episodes ORDER BY id DESC LIMIT 12'))
 prompt=f'''أنشئ حزمة إنتاج كاملة لحلقة أصلية لصفحة فيسبوك «خلف الحقيقة». الجمهور شمال أفريقيا، اللغة عربية طبيعية ومفهومة. الشكل: دراما ثلاثية الأبعاد أصلية، مدة {item.duration_seconds} ثانية، التنسيق {item.format}.\nالموضوع: {topic}\nقواعد العالم: {bible['world_rules']}\nالشخصيات: {bible['characters']}\nأحداث سابقة يجب احترامها: {bible['continuity']}\nممنوع تكراره: {bible['forbidden_repeats']}\nأفكار حديثة لتجنب التشابه: {recent}\nأخرج النتيجة بهذه العناوين: 1) عنوان جذاب 2) خطاف أول ثانيتين 3) تقسيم زمني للمشاهد مع وصف بصري وكلام/تعليق صوتي 4) برومبت مستقل لكل مشهد لتوليد الفيديو 5) وصف الصوت والمؤثرات 6) تعليق منشور قصير 7) ثلاثة هاشتاغات فقط 8) سؤال تفاعل مثبت 9) فحص استمرارية الشخصيات 10) قائمة فحص جودة. لا تدّع أنك أنشأت ملف فيديو؛ أنت تنشئ خطة ونصوصًا فقط. أجب بالعربية.'''
 try: result=services.mistral_chat(prompt)
 except Exception as e: services.log('generate_script','failed',str(e)); raise HTTPException(503,str(e))
 if item.episode_id:
  with connect() as c: c.execute("UPDATE episodes SET script=?,status='draft',updated_at=CURRENT_TIMESTAMP WHERE id=?",(result,item.episode_id))
 services.log('generate_script','success',f'episode={item.episode_id or "new"}')
 return {'generated':True,'episode_id':item.episode_id,'content':result,'video_file_created':False}
@app.get('/api/meta/status')
def meta_status():
 return {'configured':bool(os.getenv('META_PAGE_ACCESS_TOKEN')),'page_id_configured':bool(os.getenv('META_PAGE_ID')),'publish_enabled':os.getenv('ENABLE_META_PUBLISHING','false').lower()=='true','note':'This build performs no automatic posting. Meta credentials are not tested until you explicitly request a read-only test.'}
@app.post('/api/meta/test-read')
def meta_test_read():
 if not os.getenv('META_PAGE_ID'): raise HTTPException(400,'Set META_PAGE_ID in the hosting environment first')
 try: data=services.meta_read(os.getenv('META_PAGE_ID')+'?fields=id,name,fan_count')
 except Exception as e: services.log('meta_read_test','failed',str(e)); raise HTTPException(502,str(e))
 services.log('meta_read_test','success','Read-only page metadata fetched')
 return {'success':True,'page':data}
@app.get('/api/report.pdf')
def report_pdf():
 try: pdf=services.weekly_report_pdf()
 except Exception as e: raise HTTPException(503,str(e))
 return StreamingResponse(io.BytesIO(pdf),media_type='application/pdf',headers={'Content-Disposition':'attachment; filename=mashhad-weekly-report.pdf'})

@app.get('/api/scheduler/status')
def scheduler_status():
 enabled=os.getenv('WEEKLY_REPORT_ENABLED','false').lower()=='true'
 return {'weekly_report_enabled':enabled,'day':os.getenv('REPORT_DAY','mon'),'hour':int(os.getenv('REPORT_HOUR','9')),'smtp_configured':bool(os.getenv('SMTP_HOST') and os.getenv('REPORT_EMAIL_TO')),'note':'Requires persistent hosting; email sending only runs when explicitly enabled and SMTP secrets are configured.'}

@app.get('/api/logs')
def logs():
 with connect() as c: return [dict(r) for r in c.execute('SELECT * FROM task_log ORDER BY id DESC LIMIT 100')]

@app.get('/',response_class=HTMLResponse)
def home():
 return r'''<!doctype html><html lang="ar" dir="rtl"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>مشهد AI Studio</title><style>
:root{color-scheme:dark}*{box-sizing:border-box}body{margin:0;background:#0c111b;color:#edf2fb;font-family:system-ui,-apple-system,sans-serif}main{max-width:1080px;margin:auto;padding:22px}.hero{padding:24px;border:1px solid #2d394d;border-radius:20px;background:linear-gradient(130deg,#17233a,#111722)}h1{margin:0 0 6px}.muted{color:#a7b6cc}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:14px}.card{background:#141c29;border:1px solid #2a3649;border-radius:16px;padding:18px;margin:14px 0}.wide{grid-column:1/-1}input,textarea,select{width:100%;background:#0c111b;color:#f2f6ff;border:1px solid #3a4860;border-radius:9px;padding:11px;margin:6px 0 12px;font:inherit}textarea{min-height:90px}button,.btn{cursor:pointer;background:#d6e4ff;color:#142033;border:0;border-radius:9px;padding:10px 14px;font-weight:700;margin:3px}button.secondary{background:#29374c;color:#edf2fb}pre{white-space:pre-wrap;overflow-wrap:anywhere;max-height:420px;overflow:auto;background:#0b1019;padding:12px;border-radius:9px;font-size:13px}.pill{display:inline-block;border-radius:99px;background:#28384d;padding:5px 10px;font-size:12px;margin:3px}.episode{padding:12px 0;border-bottom:1px solid #2c3748}.row{display:flex;gap:8px;flex-wrap:wrap}.row>*{flex:1}.status{color:#c5d7ff}@media(max-width:560px){main{padding:12px}.hero{padding:18px}}
</style><main><section class="hero"><h1>مشهد AI Studio</h1><div class="muted">مدير إنتاج المحتوى لصفحة «خلف الحقيقة»</div><p><span class="pill">حفظ محلي</span><span class="pill">توليد نص اختياري عبر Mistral</span><span class="pill">النشر التلقائي متوقف</span></p><div class="row"><button onclick="health()">فحص النظام</button><a class="btn" href="/api/report.pdf">إنشاء تقرير PDF</a><button class="secondary" onclick="metaStatus()">حالة ربط Meta</button></div><pre id="health">جارٍ التحضير...</pre></section>
<div class="grid"><section class="card"><h2>إنشاء فكرة حلقة</h2><label>العنوان</label><input id="title" placeholder="مثال: الباب الذي ظهر في الجدار"><label>ملخص الفكرة</label><textarea id="premise" placeholder="الخطاف، التطور، المفاجأة، النهاية..."></textarea><button onclick="addEpisode()">حفظ الفكرة</button><pre id="addresult"></pre></section>
<section class="card"><h2>إنشاء نص إنتاج بالذكاء الاصطناعي</h2><label>معرّف الحلقة (اختياري)</label><input id="eid" type="number" placeholder="اتركه فارغًا لفكرة جديدة"><label>موضوع الحلقة إذا لم يوجد معرّف</label><input id="topic" placeholder="فكرة جديدة غير مكررة"><label>المدة بالثواني</label><select id="duration"><option>30</option><option selected>45</option><option>60</option><option>90</option></select><button onclick="generate()">توليد حزمة النصوص</button><pre id="generated">تحتاج إلى ضبط MISTRAL_API_KEY في إعدادات الاستضافة.</pre></section>
<section class="card wide"><h2>ذاكرة العالم والشخصيات</h2><p class="muted">احفظ قوانين القصة والشخصيات والأحداث السابقة لمنع التناقض والتكرار.</p><label>قواعد العالم والأسلوب</label><textarea id="world_rules" placeholder="نوع القصص، النبرة، قواعد العالم..."></textarea><label>الشخصيات الثابتة</label><textarea id="characters" placeholder="الأسماء، الشكل، العلاقات، طريقة الكلام..."></textarea><label>استمرارية الأحداث</label><textarea id="continuity" placeholder="ما حدث في الحلقات السابقة وما يجب أن يستمر..."></textarea><label>أفكار أو نهايات ممنوع تكرارها</label><textarea id="forbidden_repeats" placeholder="قائمة مختصرة بما استُخدم سابقًا..."></textarea><button onclick="saveBible()">حفظ الذاكرة</button><pre id="bibleResult"></pre></section>
<section class="card wide"><h2>الحلقات المحفوظة</h2><button onclick="loadEpisodes()">تحديث القائمة</button><div id="episodes"></div></section>
<section class="card"><h2>تسجيل أداء الصفحة</h2><label>التاريخ</label><input id="day" type="date"><label>المتابعون</label><input id="followers" type="number" min="0"><label>الوصول</label><input id="reach" type="number" min="0"><label>المشاهدات</label><input id="views" type="number" min="0"><label>التفاعلات</label><input id="reactions" type="number" min="0"><label>التعليقات</label><input id="comments" type="number" min="0"><button onclick="saveMetric()">حفظ المقاييس</button><pre id="metricResult"></pre></section>
<section class="card"><h2>بيانات الأداء</h2><button onclick="loadMetrics()">عرض آخر المقاييس</button><pre id="metrics"></pre><h3>اختبار قراءة بيانات Meta</h3><p class="muted">قراءة فقط، يتطلب Page Access Token وصلاحيات صالحة. لا ينشر ولا يغيّر شيئًا.</p><button onclick="metaTest()">تنفيذ اختبار القراءة</button><pre id="metaResult"></pre></section></div><section class="card"><h2>سجل النظام</h2><button onclick="loadLogs()">تحديث السجل</button><pre id="logs"></pre><p class="muted">لا يتم إنشاء فيديو فعليًا في هذه النسخة؛ توليد الفيديو يحتاج مزوّد فيديو مستقلًا ومفتاح API. الجدولة والبريد التلقائي لا يُفعّلان قبل إعداد الاستضافة الدائمة وخدمة البريد.</p></section></main><script>
async function api(url,opts={}){let r=await fetch(url,{headers:{'Content-Type':'application/json',...(opts.headers||{})},...opts});let d=await r.json().catch(()=>({error:r.statusText}));if(!r.ok)throw Error(d.detail||d.error||'حدث خطأ');return d}function show(id,v){document.getElementById(id).textContent=typeof v==='string'?v:JSON.stringify(v,null,2)}async function health(){try{show('health',await api('/api/health'))}catch(e){show('health',e.message)}}async function metaStatus(){try{show('health',await api('/api/meta/status'))}catch(e){show('health',e.message)}}async function addEpisode(){try{let x=await api('/api/episodes',{method:'POST',body:JSON.stringify({title:title.value,premise:premise.value})});show('addresult',x);title.value='';premise.value='';loadEpisodes();loadLogs()}catch(e){show('addresult',e.message)}}async function generate(){try{show('generated','جارٍ إنشاء النص...');let x=await api('/api/generate',{method:'POST',body:JSON.stringify({episode_id:eid.value?Number(eid.value):null,topic:topic.value||null,duration_seconds:Number(duration.value)})});show('generated',x.content);loadEpisodes();loadLogs()}catch(e){show('generated','تعذّر التوليد: '+e.message)}}async function loadEpisodes(){try{let xs=await api('/api/episodes');episodes.innerHTML=xs.map(x=>`<div class="episode"><b>#${x.id} — ${esc(x.title)}</b> <span class="pill">${esc(x.status)}</span><p>${esc(x.premise)}</p>${x.script?`<details><summary>عرض النص المولّد</summary><pre>${esc(x.script)}</pre></details>`:''}<div class="row"><button onclick="setStatus(${x.id},'ready')">اعتماد كمسودة جاهزة</button><button class="secondary" onclick="deleteEpisode(${x.id})">حذف</button></div></div>`).join('')||'<p class="muted">لا توجد حلقات محفوظة بعد.</p>'}catch(e){episodes.textContent=e.message}}function esc(s){return String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}async function setStatus(id,status){try{await api('/api/episodes/'+id,{method:'PATCH',body:JSON.stringify({status})});loadEpisodes()}catch(e){alert(e.message)}}async function deleteEpisode(id){if(!confirm('هل تريد حذف هذه الحلقة؟'))return;try{await api('/api/episodes/'+id,{method:'DELETE'});loadEpisodes();loadLogs()}catch(e){alert(e.message)}}async function loadBible(){try{let b=await api('/api/story-bible');for(let k of ['world_rules','characters','continuity','forbidden_repeats'])document.getElementById(k).value=b[k]||''}catch(e){show('bibleResult',e.message)}}async function saveBible(){try{let b={};for(let k of ['world_rules','characters','continuity','forbidden_repeats'])b[k]=document.getElementById(k).value;show('bibleResult',await api('/api/story-bible',{method:'PUT',body:JSON.stringify(b)}))}catch(e){show('bibleResult',e.message)}}async function saveMetric(){try{let x={day:day.value};for(let k of ['followers','reach','views','reactions','comments'])x[k]=document.getElementById(k).value===''?null:Number(document.getElementById(k).value);show('metricResult',await api('/api/metrics',{method:'POST',body:JSON.stringify(x)}));loadMetrics()}catch(e){show('metricResult',e.message)}}async function loadMetrics(){try{show('metrics',await api('/api/metrics'))}catch(e){show('metrics',e.message)}}async function metaTest(){try{show('metaResult',await api('/api/meta/test-read',{method:'POST',body:'{}'}))}catch(e){show('metaResult',e.message)}}async function loadLogs(){try{show('logs',await api('/api/logs'))}catch(e){show('logs',e.message)}}day.value=new Date().toISOString().slice(0,10);health();loadBible();loadEpisodes();
</script></html>'''
