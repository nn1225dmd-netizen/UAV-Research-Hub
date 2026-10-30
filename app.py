from contextlib import closing
from pathlib import Path
import os
import sqlite3
import streamlit as st
import pandas as pd
from hub.db import *

ROOT=Path(__file__).resolve().parent
DATA=Path(os.environ.get('UAV_HUB_DATA',str(ROOT/'data')))
DATA.mkdir(parents=True,exist_ok=True)
(DATA/'originals').mkdir(exist_ok=True)
DB=DATA/'hub.sqlite3'
st.set_page_config(page_title='UAV Research Hub',layout='wide')
init(DB)
st.title('無人機產業研究資料庫')
st.caption('UAV Research Hub 1.0｜第一階段基礎版｜本機資料處理')
page=st.sidebar.radio('功能',['首頁總覽','全站資料搜尋','廠商與訪談資料庫','TW-LOG 文獻資料庫','研究證據管理','KPI 成果對照','資料匯入與匯出','備份、還原及系統設定'])
st.sidebar.info('訪談統一採用 INT。索引不代表已完成訪談或已確認來源。')

def table(data):
    if data: st.dataframe(pd.DataFrame(data),hide_index=True,width='stretch')
    else: st.info('目前沒有資料。')

def choose(label, values, display=lambda x:str(x), **kwargs):
    return st.selectbox(label,values,format_func=display,**kwargs)

def linked(c,table,key,identity,col):
    return [r[0] for r in c.execute(f'SELECT {col} FROM {table} WHERE {key}=?',(identity,))]

def source_detail(c,identity):
    d=dict(c.execute('SELECT * FROM documents WHERE id=?',(identity,)).fetchone())
    st.write('原始文件詳細資料',d)
    st.caption('原始位置僅供本機人工核對；第一階段不搬移或上傳原檔。')

with closing(connect(DB)) as c, c:
    vendors={r['code']:r['name'] for r in c.execute('SELECT * FROM vendors ORDER BY code')}
    logs={r['code']:r['hint'] for r in c.execute('SELECT * FROM logs ORDER BY code')}
    docs={r['id']:r['title'] for r in c.execute('SELECT * FROM documents')}
    kpis={r['id']:r['title'] for r in c.execute('SELECT * FROM kpis')}
    vf=lambda v:f'{v}：{vendors[v]}'
    df=lambda v:f'{v}：{docs[v]}'
    if page=='首頁總覽':
        cols=st.columns(4)
        for col,(label,t) in zip(cols,[('訪談紀錄','interviews'),('來源文件','documents'),('研究證據','evidence'),('已建文獻索引','logs')]):
            col.metric(label,c.execute(f'SELECT count(*) FROM {t}').fetchone()[0])
        st.warning('KPI 目前僅作分類；目標及達成判定須依契約設定，不以文件、證據或廠商數計算達成。')
        st.write('先登錄來源文件，再新增訪談與證據。所有預建文獻索引皆待原始文件核對。')
    elif page=='廠商與訪談資料庫':
        vendor=choose('INT 編碼／廠商',list(vendors),vf)
        v=dict(c.execute('SELECT * FROM vendors WHERE code=?',(vendor,)).fetchone())
        with st.form('vendor'):
            st.write(vf(vendor))
            positioning=st.text_input('產業定位',v['positioning'])
            technology=st.text_area('產品及技術方向',v['technology'])
            if st.form_submit_button('儲存廠商資料'):
                c.execute('UPDATE vendors SET positioning=?,technology=?,updated_at=? WHERE code=?',(positioning,technology,now(),vendor)); audit(c,'vendor',vendor,'修改'); c.commit(); st.success('已儲存')
        entries=rows(c,'SELECT * FROM interviews WHERE vendor_code=? ORDER BY date DESC',(vendor,))
        table(entries)
        selected=choose('新增或修改訪談',[None]+[x['id'] for x in entries],lambda x:'新增訪談' if x is None else f'修改訪談 #{x}')
        old=next((x for x in entries if x['id']==selected),{})
        with st.form('interview'):
            date=st.text_input('訪談日期 YYYY-MM-DD',old.get('date',''))
            form=st.text_input('訪談形式',old.get('format',''))
            needs=st.text_area('產業需求',old.get('needs',''))
            opportunities=st.text_area('合作機會（請註明確認程度）',old.get('opportunities',''))
            summary=st.text_area('訪談摘要（人工確認）',old.get('summary',''))
            attachments=st.multiselect('相關原始文件',list(docs),default=linked(c,'interview_documents','interview_id',selected,'document_id') if selected else [],format_func=df)
            if st.form_submit_button('儲存訪談'):
                try:
                    with c: save_interview(c,vendor,date,form,needs,opportunities,summary,selected,attachments)
                    st.success('訪談已儲存；切換頁面或重新整理即可查看。')
                except (ValueError,sqlite3.Error) as e: st.error(f'未儲存：{e}')
    elif page=='TW-LOG 文獻資料庫':
        code=choose('文獻索引',list(logs),lambda x:f'{x}：{logs[x]}')
        old=dict(c.execute('SELECT * FROM logs WHERE code=?',(code,)).fetchone())
        st.info('以下欄位須依原始文件填寫；索引提示不是正式題名。彙整型紀錄可關聯多個來源文件。')
        with st.form('log'):
            title=st.text_input('正式題名',old['title']); provider=st.text_input('來源／出版單位',old['provider'])
            year=st.text_input('出版年（依原件，未知留空）',old['publication_year'])
            kind=choose('紀錄類型',['單篇','彙整'],index=['單篇','彙整'].index(old['kind']))
            notes=st.text_area('備註',old['notes'])
            if st.form_submit_button('儲存文獻索引'):
                c.execute('UPDATE logs SET title=?,provider=?,publication_year=?,kind=?,notes=?,updated_at=? WHERE code=?',(title,provider,year,kind,notes,now(),code)); audit(c,'log',code,'修改'); c.commit(); st.success('已儲存')
        table(rows(c,'SELECT d.* FROM documents d JOIN document_logs l ON d.id=l.document_id WHERE l.log_code=?',(code,)))
        st.subheader('手動登錄原始來源（可直接關聯 INT 或 TW-LOG）')
        with st.form('source'):
            source_code=st.text_input('文件唯一編碼（例如自訂附件編碼，不是新增訪談編碼）')
            title=st.text_input('文件名稱 *'); source_type=st.text_input('來源類型'); provider=st.text_input('作者／提供單位')
            date=st.text_input('文件日期 YYYY-MM-DD'); url=st.text_input('原始網址'); path=st.text_input('原始檔案位置（完整本機路徑）')
            confidentiality=choose('保密等級',['內部','機密','公開'])
            notes=st.text_area('來源備註'); confirmed=st.checkbox('已人工確認原始來源')
            vs=st.multiselect('關聯 INT',list(vendors),format_func=vf)
            ls=st.multiselect('關聯 TW-LOG',list(logs),default=[code])
            if st.form_submit_button('儲存來源'):
                try:
                    import hashlib
                    digest=None
                    if path:
                        p=Path(path)
                        if not p.is_file(): raise ValueError('找不到原始檔案，請確認本機完整路徑。')
                        h=hashlib.sha256()
                        with p.open('rb') as f:
                            for block in iter(lambda:f.read(1024*1024),b''): h.update(block)
                        digest=h.hexdigest()
                    with c:
                        save_document(c,dict(code=source_code,title=title,source_type=source_type,provider=provider,date=date,url=url,file_path=path,sha256=digest,confidentiality=confidentiality,notes=notes,confirmed=int(confirmed)),vs,ls)
                    st.success('來源已登錄')
                except (ValueError,OSError,sqlite3.Error) as e: st.error(f'未儲存：{e}')
        if docs:
            did=choose('查看或修改原始來源',list(docs),df)
            source_detail(c,did)
            metadata=dict(c.execute('SELECT * FROM documents WHERE id=?',(did,)).fetchone())
            with st.form('edit_source'):
                mt=st.text_input('修訂文件名稱',metadata['title'])
                mp=st.text_input('修訂作者／提供單位',metadata['provider'])
                md=st.text_input('修訂文件日期',metadata['date'])
                mu=st.text_input('修訂原始網址',metadata['url'])
                mc=choose('修訂保密等級',['內部','機密','公開'],index=['內部','機密','公開'].index(metadata['confidentiality']))
                mn=st.text_area('修訂來源備註',metadata['notes'])
                mf=st.checkbox('來源已人工確認',value=bool(metadata['confirmed']))
                if st.form_submit_button('儲存來源修訂'):
                    try:
                        with c: update_document_metadata(c,did,mt,mp,md,mu,mc,mn,mf)
                        st.success('來源修訂已儲存；原檔及雜湊保持不變。')
                    except (ValueError,sqlite3.Error) as e: st.error(f'未儲存：{e}')
    elif page=='研究證據管理':
        if not docs:
            st.info('請先在 TW-LOG 文獻資料庫登錄原始來源（亦可關聯 INT）。')
        else:
            entries=rows(c,'SELECT * FROM evidence ORDER BY id')
            selected=choose('新增或修改證據',[None]+[x['id'] for x in entries],lambda x:'新增證據' if x is None else f'證據 #{x}')
            old=next((x for x in entries if x['id']==selected),{})
            with st.form('evidence'):
                doc=choose('原始來源',list(docs),df,index=list(docs).index(old['document_id']) if selected else 0,disabled=bool(selected))
                original=st.text_area('原文段落（儲存後不可覆寫）',old.get('original',''),disabled=bool(selected))
                locator=st.text_input('頁碼或段落定位（依原件填寫）',old.get('locator',''),disabled=bool(selected))
                summary=st.text_area('研究摘要',old.get('summary',''))
                fact=choose('事實類型',['訪談原始事實','研究分析','待確認資訊'],index=['訪談原始事實','研究分析','待確認資訊'].index(old.get('fact_type','待確認資訊')))
                maturity=choose('合作成熟度',['待確認','已證實合作','潛在合作機會','研究推論'],index=['待確認','已證實合作','潛在合作機會','研究推論'].index(old.get('maturity','待確認')))
                status=choose('查核狀態',['待確認','已確認','需修正'],index=['待確認','已確認','需修正'].index(old.get('status','待確認')))
                review=st.text_input('審核日期 YYYY-MM-DD',old.get('review_date',''))
                notes=st.text_area('備註',old.get('notes',''))
                vs=st.multiselect('相關廠商',list(vendors),default=linked(c,'evidence_vendors','evidence_id',selected,'vendor_code') if selected else [],format_func=vf)
                ks=st.multiselect('KPI 關聯（可複選）',list(kpis),default=linked(c,'evidence_kpis','evidence_id',selected,'kpi_id') if selected else [],format_func=lambda x:kpis[x])
                tags=st.text_input('主題標籤（以頓號「、」分隔）','、'.join(r[0] for r in c.execute('SELECT name FROM topics JOIN evidence_topics ON topics.id=topic_id WHERE evidence_id=?',(selected,))))
                if st.form_submit_button('儲存證據'):
                    try:
                        with c: save_evidence(c,doc,original,locator,summary,fact,maturity,status,review,notes,vs,ks,tags,selected)
                        st.success('證據已儲存')
                    except (ValueError,sqlite3.Error) as e: st.error(f'未儲存：{e}')
            source_detail(c,doc)
    elif page=='全站資料搜尋':
        q=st.text_input('中文關鍵字、廠商名稱、INT 或 TW-LOG 編碼')
        vendor=choose('廠商篩選',['全部']+list(vendors),lambda x:x if x=='全部' else vf(x))
        topic=st.text_input('研究主題'); date=st.text_input('訪談日期（可留空）')
        kpi=choose('KPI 篩選',[None]+list(kpis),lambda x:'全部' if x is None else kpis[x])
        status=choose('查核狀態',['全部','待確認','已確認','需修正'])
        pattern='%'+q+'%'
        st.subheader('廠商與訪談')
        table(rows(c,"SELECT v.code,v.name,i.* FROM vendors v LEFT JOIN interviews i ON i.vendor_code=v.code WHERE (v.code LIKE ? OR v.name LIKE ? OR COALESCE(i.summary,'') LIKE ? OR COALESCE(i.needs,'') LIKE ? OR COALESCE(i.opportunities,'') LIKE ?) AND (?='全部' OR v.code=?) AND (?='' OR i.date=?)",(pattern,)*5+(vendor,vendor,date,date)))
        st.subheader('TW-LOG 索引')
        table(rows(c,'SELECT * FROM logs WHERE code LIKE ? OR title LIKE ? OR hint LIKE ?',(pattern,)*3))
        st.subheader('研究證據與出處')
        result=rows(c,'''SELECT DISTINCT e.*,d.code source_code,d.title source_title,d.file_path,d.url FROM evidence e JOIN documents d ON d.id=e.document_id WHERE (e.original LIKE ? OR e.summary LIKE ? OR d.code LIKE ? OR d.title LIKE ? OR EXISTS(SELECT 1 FROM evidence_vendors ev JOIN vendors v ON v.code=ev.vendor_code WHERE ev.evidence_id=e.id AND (v.code LIKE ? OR v.name LIKE ?)) OR EXISTS(SELECT 1 FROM document_logs dl WHERE dl.document_id=d.id AND dl.log_code LIKE ?)) AND (?='全部' OR EXISTS(SELECT 1 FROM evidence_vendors ev WHERE ev.evidence_id=e.id AND ev.vendor_code=?)) AND (?='全部' OR e.status=?) AND (? IS NULL OR EXISTS(SELECT 1 FROM evidence_kpis ek WHERE ek.evidence_id=e.id AND ek.kpi_id=?)) AND (?='' OR EXISTS(SELECT 1 FROM evidence_topics et JOIN topics t ON t.id=et.topic_id WHERE et.evidence_id=e.id AND t.name LIKE ?)) AND (?='' OR EXISTS(SELECT 1 FROM interview_documents id JOIN interviews i ON i.id=id.interview_id WHERE id.document_id=d.id AND i.date=?))''',(pattern,)*7+(vendor,vendor,status,status,kpi,kpi,topic,'%'+topic+'%',date,date))
        table(result)
        if result:
            item=choose('開啟證據詳細資料',[x['id'] for x in result])
            r=next(x for x in result if x['id']==item)
            st.write('原文',r['original']); st.write('定位',r['locator']); st.write('研究摘要',r['summary']); source_detail(c,r['document_id'])
        st.caption('詳細修改請至各資料管理頁。')
    elif page=='KPI 成果對照':
        st.warning('以下僅為分類與佐證對照，尚未實作成果核定流程，不計算達成數。')
        k=choose('KPI',list(kpis),lambda x:kpis[x]); old=dict(c.execute('SELECT * FROM kpis WHERE id=?',(k,)).fetchone())
        with st.form('kpi'):
            title=st.text_input('契約正式名稱',old['title'])
            target=st.text_input('目標件數（未確認請留空）','' if old['target'] is None else str(old['target']))
            criteria=st.text_area('達成判定依據',old['criteria'])
            if st.form_submit_button('儲存 KPI 設定'):
                try:
                    n=int(target) if target else None
                    if not title.strip() or (n is not None and n<0): raise ValueError()
                    c.execute('UPDATE kpis SET title=?,target=?,criteria=? WHERE id=?',(title,n,criteria,k)); audit(c,'kpi',k,'修改'); c.commit(); st.success('已儲存')
                except ValueError: st.error('請填寫名稱；目標件數須為非負整數或留空。')
        table(rows(c,'SELECT e.* FROM evidence e JOIN evidence_kpis ek ON ek.evidence_id=e.id WHERE ek.kpi_id=?',(k,)))
    elif page=='資料匯入與匯出':
        st.info('本階段僅支援手動登錄。文件／Excel 預覽匯入、範本、公開模式去識別化及 Excel／Word 匯出，列於第二階段；尚未開放，避免誤用未完成的保密處理。')
        st.warning('歷史文件如含 TW-VISIT，須依原件人工核對 INT 後才能歸檔；系統不推定對應。')
    else:
        st.write('資料庫位置',str(DB)); st.write('原始檔案預留資料夾',str(DATA/'originals'))
        st.write('結構版本',c.execute('PRAGMA user_version').fetchone()[0])
        st.caption('原始文件仍保留於登錄的位置；請同時保管原件。完整備份及安全還原於第三階段實作。')
        if st.button('建立資料庫安全備份（不含原始文件）'):
            out=DATA/'backups'; out.mkdir(exist_ok=True)
            dest=out/f"hub-{datetime.now().strftime('%Y%m%d-%H%M%S-%f')}.sqlite3"
            with closing(sqlite3.connect(dest)) as backup: c.backup(backup)
            st.success(f'資料庫備份已建立：{dest}')
        st.subheader('最近操作紀錄')
        table(rows(c,'SELECT * FROM audit ORDER BY id DESC LIMIT 30'))
