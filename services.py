import os, json, smtplib, urllib.request, urllib.error
from email.message import EmailMessage
from datetime import datetime, timezone
from .db import connect

def log(task,status,details=''):
    with connect() as c: c.execute('INSERT INTO task_log(task,status,details) VALUES(?,?,?)',(task,status,str(details)[:4000]))

def mistral_chat(prompt, system=None):
    key=os.getenv('MISTRAL_API_KEY','').strip()
    if not key: raise RuntimeError('MISTRAL_API_KEY is not configured. Add it in the hosting environment; no API call was made.')
    payload={'model':os.getenv('MISTRAL_MODEL','mistral-small-latest'),'temperature':0.85,'messages':[{'role':'system','content':system or 'أنت كاتب محترف لقصص عربية أصلية قصيرة. اكتب بالعربية، حافظ على الاستمرارية، ولا تدّعِ أن أي محتوى نُشر.'},{'role':'user','content':prompt}]}
    req=urllib.request.Request('https://api.mistral.ai/v1/chat/completions',data=json.dumps(payload).encode(),headers={'Authorization':f'Bearer {key}','Content-Type':'application/json'},method='POST')
    try:
        with urllib.request.urlopen(req,timeout=60) as r: data=json.loads(r.read().decode())
        return data['choices'][0]['message']['content']
    except urllib.error.HTTPError as e:
        detail=e.read().decode(errors='replace')[:800]
        raise RuntimeError(f'Mistral API returned HTTP {e.code}: {detail}')

def meta_read(path):
    token=os.getenv('META_PAGE_ACCESS_TOKEN','').strip()
    if not token: raise RuntimeError('META_PAGE_ACCESS_TOKEN is not configured; no request was made.')
    url='https://graph.facebook.com/v23.0/'+path+('&' if '?' in path else '?')+'access_token='+token
    req=urllib.request.Request(url,headers={'User-Agent':'MashhadAIStudio/1.0'})
    with urllib.request.urlopen(req,timeout=30) as r: return json.loads(r.read().decode())

def send_email(subject,body,attachment=None,filename='report.pdf'):
    host=os.getenv('SMTP_HOST','').strip(); recipient=os.getenv('REPORT_EMAIL_TO','').strip()
    if not host or not recipient: raise RuntimeError('Configure SMTP_HOST and REPORT_EMAIL_TO first.')
    msg=EmailMessage(); msg['Subject']=subject; msg['From']=os.getenv('SMTP_FROM',os.getenv('SMTP_USER','')); msg['To']=recipient; msg.set_content(body)
    if attachment: msg.add_attachment(attachment,maintype='application',subtype='pdf',filename=filename)
    with smtplib.SMTP(host,int(os.getenv('SMTP_PORT','587')),timeout=30) as s:
        s.starttls(); user=os.getenv('SMTP_USER',''); password=os.getenv('SMTP_PASSWORD','')
        if user: s.login(user,password)
        s.send_message(msg)


def weekly_report_pdf():
    import io
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    from datetime import datetime
    out=io.BytesIO(); p=canvas.Canvas(out,pagesize=A4); w,h=A4; y=h-50
    with connect() as c:
        eps=[dict(r) for r in c.execute('SELECT id,title,status,created_at FROM episodes ORDER BY id DESC LIMIT 20')]
        mets=[dict(r) for r in c.execute("SELECT * FROM metrics WHERE day>=date('now','-7 day') ORDER BY day")]
        logs=[dict(r) for r in c.execute('SELECT task,status,details,created_at FROM task_log ORDER BY id DESC LIMIT 15')]
    p.setTitle('Mashhad AI Studio - Weekly Report'); p.setFont('Helvetica-Bold',16); p.drawString(40,y,'Mashhad AI Studio - Weekly Report'); y-=28
    p.setFont('Helvetica',10); p.drawString(40,y,'Page: خلف الحقيقة'); y-=18; p.drawString(40,y,'Generated: '+datetime.now().strftime('%Y-%m-%d %H:%M')); y-=30
    for title, lines in [('Recent episodes',[f"#{e['id']} [{e['status']}] {e['title']}" for e in eps]),('Metrics recorded in last 7 days',[f"{m['day']} | followers={m['followers']} | reach={m['reach']} | views={m.get('views')} | reactions={m['reactions']} | comments={m['comments']}" for m in mets]),('Recent system activity',[f"{x['created_at']} | {x['task']} | {x['status']}" for x in logs])]:
        p.setFont('Helvetica-Bold',12); p.drawString(40,y,title); y-=18; p.setFont('Helvetica',9)
        for line in lines or ['No recorded data.']:
            if y<55: p.showPage(); y=h-50; p.setFont('Helvetica',9)
            p.drawString(44,y,line[:115]); y-=13
        y-=14
    p.save(); return out.getvalue()

def send_weekly_report():
    pdf=weekly_report_pdf()
    send_email('تقرير أسبوعي — خلف الحقيقة','مرفق التقرير الأسبوعي الآلي من Mashhad AI Studio. تنبيه: التقرير يعرض البيانات التي سجلها النظام فقط، وقد تكون المقاييس ناقصة إذا لم تُزامَن بيانات Meta.',pdf,'mashhad-weekly-report.pdf')
    log('weekly_report_email','success','PDF report sent to configured recipient')
