from contextlib import closing
import sqlite3
import json
from pathlib import Path
from datetime import datetime, timezone

VENDORS = ['碳基科技','中光電智能機器人','璿元科技','漢翔','銘旺科技','田屋科技','ZenaDrone','睿智創新','政秀企業','奧榮科技','歐特明電子','旺來AI']
LOGS = ['運輸研究所相關研究（待核對）'] * 3 + ['2026 民航局無人機物流工作坊（待核對）','無人機物流參考資料彙整（待核對）','Drone Industry Insights 2026 相關研究（待核對）','DroneII 產業情報資料庫（待核對）','AI 熱影像及邊緣運算技術案例（待核對）']
KPIS = ['無人機產業盤點與相關研究分析','XPONENTIAL 國際展會及產業鏈結','國際場域、驗證機制與營運模式研究','國內產業交流及活動辦理','國內業者訪談與產業需求、合作機會分析']

def now():
    return datetime.now(timezone.utc).isoformat()

def connect(path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(path)
    c.row_factory = sqlite3.Row
    c.execute('PRAGMA foreign_keys=ON')
    return c

def init(path):
    with closing(connect(path)) as c, c:
        version = c.execute('PRAGMA user_version').fetchone()[0]
        if version > 1:
            raise ValueError('資料庫版本較新，請使用新版程式開啟，勿降級。')
        c.executescript('''
        CREATE TABLE IF NOT EXISTS vendors(code TEXT PRIMARY KEY, name TEXT NOT NULL, positioning TEXT DEFAULT '', technology TEXT DEFAULT '', updated_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS logs(code TEXT PRIMARY KEY, hint TEXT NOT NULL, title TEXT DEFAULT '', provider TEXT DEFAULT '', publication_year TEXT DEFAULT '', kind TEXT DEFAULT '單篇', notes TEXT DEFAULT '', updated_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS interviews(id INTEGER PRIMARY KEY, vendor_code TEXT NOT NULL REFERENCES vendors(code), date TEXT NOT NULL, format TEXT, needs TEXT, opportunities TEXT, summary TEXT, updated_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS documents(id INTEGER PRIMARY KEY, code TEXT UNIQUE NOT NULL, title TEXT NOT NULL, source_type TEXT, provider TEXT, date TEXT, imported_at TEXT NOT NULL, url TEXT, file_path TEXT, sha256 TEXT UNIQUE, confidentiality TEXT NOT NULL, notes TEXT, confirmed INTEGER NOT NULL DEFAULT 0, updated_at TEXT NOT NULL, CHECK(confirmed=0 OR (provider<>'' AND date<>'' AND (url<>'' OR file_path<>''))));
        CREATE TABLE IF NOT EXISTS document_vendors(document_id INTEGER REFERENCES documents(id), vendor_code TEXT REFERENCES vendors(code), PRIMARY KEY(document_id,vendor_code));
        CREATE TABLE IF NOT EXISTS document_logs(document_id INTEGER REFERENCES documents(id), log_code TEXT REFERENCES logs(code), PRIMARY KEY(document_id,log_code));
        CREATE TABLE IF NOT EXISTS interview_documents(interview_id INTEGER REFERENCES interviews(id), document_id INTEGER REFERENCES documents(id), PRIMARY KEY(interview_id,document_id));
        CREATE TABLE IF NOT EXISTS kpis(id INTEGER PRIMARY KEY, title TEXT NOT NULL, target INTEGER, criteria TEXT DEFAULT '待依契約確認');
        CREATE TABLE IF NOT EXISTS evidence(id INTEGER PRIMARY KEY, document_id INTEGER NOT NULL REFERENCES documents(id), original TEXT NOT NULL, locator TEXT NOT NULL, summary TEXT, fact_type TEXT, maturity TEXT, status TEXT, review_date TEXT, notes TEXT, updated_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS evidence_vendors(evidence_id INTEGER REFERENCES evidence(id), vendor_code TEXT REFERENCES vendors(code), PRIMARY KEY(evidence_id,vendor_code));
        CREATE TABLE IF NOT EXISTS evidence_kpis(evidence_id INTEGER REFERENCES evidence(id), kpi_id INTEGER REFERENCES kpis(id), PRIMARY KEY(evidence_id,kpi_id));
        CREATE TABLE IF NOT EXISTS topics(id INTEGER PRIMARY KEY, name TEXT UNIQUE NOT NULL);
        CREATE TABLE IF NOT EXISTS evidence_topics(evidence_id INTEGER REFERENCES evidence(id), topic_id INTEGER REFERENCES topics(id), PRIMARY KEY(evidence_id,topic_id));
        CREATE TABLE IF NOT EXISTS reports(id INTEGER PRIMARY KEY, title TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS chapters(id INTEGER PRIMARY KEY, report_id INTEGER REFERENCES reports(id), title TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS evidence_chapters(evidence_id INTEGER REFERENCES evidence(id), chapter_id INTEGER REFERENCES chapters(id), PRIMARY KEY(evidence_id,chapter_id));
        CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY, entity TEXT, entity_id TEXT, action TEXT, timestamp TEXT, details TEXT);
        CREATE TRIGGER IF NOT EXISTS immutable_original BEFORE UPDATE OF original,document_id,locator ON evidence BEGIN SELECT RAISE(ABORT,'原文及來源定位不可覆寫；請建立新的證據'); END;
        PRAGMA user_version=1;
        ''')
        for i, name in enumerate(VENDORS,1):
            c.execute('INSERT OR IGNORE INTO vendors(code,name,updated_at) VALUES(?,?,?)',(f'INT-{i:02}',name,now()))
        for i,hint in enumerate(LOGS,1):
            c.execute('INSERT OR IGNORE INTO logs(code,hint,updated_at) VALUES(?,?,?)',(f'TW-LOG-{i:03}',hint,now()))
        for i,title in enumerate(KPIS,1):
            c.execute('INSERT OR IGNORE INTO kpis(id,title) VALUES(?,?)',(i,title))

def rows(c, sql, args=()):
    return [dict(r) for r in c.execute(sql,args)]

def audit(c, entity, identity, action):
    c.execute('INSERT INTO audit(entity,entity_id,action,timestamp) VALUES(?,?,?,?)',(entity,str(identity),action,now()))

def valid_date(value, required=False):
    if not value and not required:
        return
    try:
        if datetime.strptime(value,'%Y-%m-%d').strftime('%Y-%m-%d') != value:
            raise ValueError()
    except (ValueError, TypeError):
        raise ValueError('日期請填寫 YYYY-MM-DD 格式的有效日期。')

def save_interview(c, vendor, date, form, needs, opportunities, summary, identity=None, documents=()):
    valid_date(date,True)
    if not c.execute('SELECT 1 FROM vendors WHERE code=?',(vendor,)).fetchone():
        raise ValueError('訪談必須選擇既有 INT 編碼。')
    action='修改' if identity else '新增'
    values=(vendor,date,form,needs,opportunities,summary,now())
    if identity:
        c.execute('UPDATE interviews SET vendor_code=?,date=?,format=?,needs=?,opportunities=?,summary=?,updated_at=? WHERE id=?',values+(identity,))
        c.execute('DELETE FROM interview_documents WHERE interview_id=?',(identity,))
    else:
        identity=c.execute('INSERT INTO interviews(vendor_code,date,format,needs,opportunities,summary,updated_at) VALUES(?,?,?,?,?,?,?)',values).lastrowid
    c.executemany('INSERT INTO interview_documents VALUES(?,?)',[(identity,d) for d in documents])
    audit(c,'interview',identity,action)
    return identity

def save_document(c, values, vendors, logs):
    if any('TW-VISIT' in str(v).upper() for v in values.values()):
        raise ValueError('包含歷史 TW-VISIT 編碼，請先人工核對 INT 對應後再歸檔。')
    if not values['code'].strip() or not values['title'].strip():
        raise ValueError('文件編碼及名稱為必填。')
    valid_date(values['date'])
    if values['confirmed'] and not (values['provider'].strip() and values['date'] and (values['url'].strip() or values['file_path'].strip())):
        raise ValueError('已確認來源須有提供單位、日期及網址或原始檔案位置。')
    keys=list(values)
    identity=c.execute(f"INSERT INTO documents({','.join(keys)},imported_at,updated_at) VALUES({','.join('?' for _ in range(len(keys)+2))})", tuple(values.values())+(now(),now())).lastrowid
    c.executemany('INSERT INTO document_vendors VALUES(?,?)',[(identity,v) for v in vendors])
    c.executemany('INSERT INTO document_logs VALUES(?,?)',[(identity,v) for v in logs])
    audit(c,'document',identity,'新增')
    return identity

def save_evidence(c, doc, original, locator, summary, fact, maturity, status, review, notes, vendors, kpis, tags, identity=None):
    if not original.strip() or not locator.strip():
        raise ValueError('原文及頁碼／段落定位為必填，請依原始文件輸入。')
    valid_date(review)
    source=c.execute('SELECT confirmed FROM documents WHERE id=?',(doc,)).fetchone()
    if not source or (status=='已確認' and not source[0]):
        raise ValueError('原始來源尚未確認，證據不可標示已確認。')
    if status=='已確認' and not review:
        raise ValueError('已確認證據須填寫審核日期。')
    if identity:
        c.execute('UPDATE evidence SET summary=?,fact_type=?,maturity=?,status=?,review_date=?,notes=?,updated_at=? WHERE id=?',(summary,fact,maturity,status,review,notes,now(),identity))
    else:
        identity=c.execute('INSERT INTO evidence(document_id,original,locator,summary,fact_type,maturity,status,review_date,notes,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)',(doc,original,locator,summary,fact,maturity,status,review,notes,now())).lastrowid
    for table in ['evidence_vendors','evidence_kpis','evidence_topics']:
        c.execute(f'DELETE FROM {table} WHERE evidence_id=?',(identity,))
    c.executemany('INSERT INTO evidence_vendors VALUES(?,?)',[(identity,v) for v in vendors])
    c.executemany('INSERT INTO evidence_kpis VALUES(?,?)',[(identity,k) for k in kpis])
    for tag in set(t.strip() for t in tags.split('、') if t.strip()):
        c.execute('INSERT OR IGNORE INTO topics(name) VALUES(?)',(tag,))
        c.execute('INSERT INTO evidence_topics VALUES(?,(SELECT id FROM topics WHERE name=?))',(identity,tag))
    audit(c,'evidence',identity,'新增或修改')
    return identity

def update_document_metadata(c, identity, title, provider, date, url, confidentiality, notes, confirmed):
    valid_date(date)
    old=c.execute('SELECT file_path FROM documents WHERE id=?',(identity,)).fetchone()
    if not old: raise ValueError('找不到來源。')
    if not title.strip(): raise ValueError('文件名稱不可空白。')
    if any('TW-VISIT' in str(v).upper() for v in [title,provider,url,notes]):
        raise ValueError('歷史編碼須人工核對後歸檔。')
    if confirmed and not (provider.strip() and date and (url.strip() or old['file_path'])):
        raise ValueError('來源不完整，不能確認。')
    if not confirmed and c.execute("SELECT 1 FROM evidence WHERE document_id=? AND status='已確認'",(identity,)).fetchone():
        raise ValueError('請先將此來源的已確認證據改為待確認，才可撤回來源確認。')
    c.execute('UPDATE documents SET title=?,provider=?,date=?,url=?,confidentiality=?,notes=?,confirmed=?,updated_at=? WHERE id=?',(title,provider,date,url,confidentiality,notes,int(confirmed),now(),identity))
    audit(c,'document',identity,'修改書目與確認狀態')
