import json, os, sqlite3
from datetime import datetime, timezone
from pathlib import Path
from flask import Flask, jsonify, request, render_template
from dotenv import load_dotenv
load_dotenv()
app=Flask(__name__); app.config['SECRET_KEY']=os.getenv('SECRET_KEY','local-demo-key')
DB=Path(os.getenv('DATABASE_PATH',Path(__file__).parent/'instance'/'app.db'))
FIELDS=["name", "foreground", "background", "notes"]; LABEL="Palette"; TITLE="Contrast Kit"
def conn():
 DB.parent.mkdir(parents=True,exist_ok=True); c=sqlite3.connect(DB); c.row_factory=sqlite3.Row; c.execute("CREATE TABLE IF NOT EXISTS items(id INTEGER PRIMARY KEY, data TEXT NOT NULL, created TEXT NOT NULL, updated TEXT NOT NULL)"); return c
@app.get('/')
def home(): return render_template('index.html',title=TITLE,domain="Accessibility & design",description="Audit color pairs, save palettes, and keep contrast decisions together.",label=LABEL,fields=FIELDS)
@app.get('/api/items')
def list_items():
 q=request.args.get('q','').strip().lower(); c=conn(); rows=c.execute('SELECT * FROM items ORDER BY updated DESC').fetchall(); c.close(); out=[]
 for r in rows:
  x=json.loads(r['data']); x.update(id=r['id'],created=r['created'],updated=r['updated'])
  if not q or q in json.dumps(x).lower(): out.append(x)
 return jsonify(out)
@app.post('/api/items')
def create_item():
 data=request.get_json(silent=True) or {}; clean={k:str(data.get(k,'')).strip()[:12000] for k in FIELDS}
 if not any(clean.values()): return jsonify(error='Add at least one field before saving.'),400
 now=datetime.now(timezone.utc).isoformat(); c=conn(); cur=c.execute('INSERT INTO items(data,created,updated) VALUES(?,?,?)',(json.dumps(clean),now,now)); c.commit(); result={'id':cur.lastrowid,**clean,'created':now,'updated':now}; c.close(); return jsonify(result),201
@app.put('/api/items/<int:item_id>')
def update_item(item_id):
 data=request.get_json(silent=True) or {}; clean={k:str(data.get(k,'')).strip()[:12000] for k in FIELDS}; now=datetime.now(timezone.utc).isoformat(); c=conn(); cur=c.execute('UPDATE items SET data=?,updated=? WHERE id=?',(json.dumps(clean),now,item_id)); c.commit(); c.close()
 if not cur.rowcount:return jsonify(error='Not found'),404
 return jsonify(id=item_id,**clean,updated=now)
@app.delete('/api/items/<int:item_id>')
def delete_item(item_id):
 c=conn(); cur=c.execute('DELETE FROM items WHERE id=?',(item_id,)); c.commit(); c.close(); return ('',204) if cur.rowcount else (jsonify(error='Not found'),404)
@app.get('/api/summary')
def summary():
 c=conn(); count=c.execute('SELECT count(*) FROM items').fetchone()[0]; rows=c.execute('SELECT data FROM items ORDER BY updated DESC LIMIT 10').fetchall(); c.close(); return jsonify(count=count,recent=[json.loads(r[0]) for r in rows])
@app.post('/api/contrast')
def contrast():
 from re import fullmatch
 data=request.get_json(silent=True) or {}
 def luminance(color):
  if not isinstance(color,str) or not fullmatch(r'#[0-9a-fA-F]{6}',color): raise ValueError('Use six-digit hex colors such as #123456.')
  rgb=[int(color[i:i+2],16)/255 for i in (1,3,5)]; linear=[v/12.92 if v<=0.04045 else ((v+0.055)/1.055)**2.4 for v in rgb]; return .2126*linear[0]+.7152*linear[1]+.0722*linear[2]
 try:
  a,b=luminance(data.get('foreground')),luminance(data.get('background')); ratio=(max(a,b)+.05)/(min(a,b)+.05)
 except ValueError as e:return jsonify(error=str(e)),400
 return jsonify(ratio=round(ratio,2),aa_normal=ratio>=4.5,aa_large=ratio>=3,aaa_normal=ratio>=7,aaa_large=ratio>=4.5)
@app.post('/api/coach')
def coach():
 prompt=(request.get_json(silent=True) or {}).get('prompt','').strip()[:3000]
 if not prompt:return jsonify(error='Enter a question first.'),400
 key=os.getenv('OPENAI_API_KEY')
 if key:
  try:
   from urllib.request import Request,urlopen
   req=Request('https://api.openai.com/v1/responses',data=json.dumps({'model':os.getenv('OPENAI_MODEL','gpt-4.1-mini'),'input':f'You are a practical Accessibility & design assistant inside Contrast Kit. Give specific, concise, safe advice. User: {prompt}'}).encode(),headers={'Authorization':'Bearer '+key,'Content-Type':'application/json'})
   with urlopen(req,timeout=35) as r: payload=json.loads(r.read())
   text=' '.join(part.get('text','') for item in payload.get('output',[]) for part in item.get('content',[]) if part.get('type')=='output_text')
   if text:return jsonify(answer=text,mode='ai')
  except Exception as e: return jsonify(error='AI request failed: '+str(e)),502
 return jsonify(answer=f'Demo coach: For “{prompt}”, start with one small, measurable next action. Save your work here, review it after a week, and adjust based on what actually helped.',mode='demo')
if __name__=='__main__': app.run(host='127.0.0.1',port=int(os.getenv('PORT',5000)),debug=os.getenv('FLASK_DEBUG')=='1')
