from contextlib import closing
import os
import tempfile
import unittest
from pathlib import Path
from streamlit.testing.v1 import AppTest

class UI(unittest.TestCase):
    def test_all_pages_and_interview(self):
        with tempfile.TemporaryDirectory() as tmp:
            previous=os.environ.get('UAV_HUB_DATA'); os.environ['UAV_HUB_DATA']=tmp
            try:
                from hub.db import init,connect,save_document,save_evidence
                init(Path(tmp)/'hub.sqlite3')
                with closing(connect(Path(tmp)/'hub.sqlite3')) as c, c:
                    d=save_document(c,dict(code='TEST-001',title='匿名來源',source_type='測試',provider='匿名提供者',date='2026-01-01',url='https://example.com/test',file_path='',sha256=None,confidentiality='內部',notes='',confirmed=1),['INT-01'],['TW-LOG-001'])
                    save_evidence(c,d,'匿名原文','第1段','匿名摘要','研究分析','研究推論','已確認','2026-01-02','',['INT-01'],[1,5],'物流')
                at=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py')).run()
                self.assertFalse(at.exception)
                pages=list(at.sidebar.radio[0].options)
                for page in pages:
                    at.sidebar.radio[0].set_value(page).run()
                    self.assertFalse(at.exception,msg=page)
                at.sidebar.radio[0].set_value('廠商與訪談資料庫').run()
                next(x for x in at.text_input if x.label=='訪談日期 YYYY-MM-DD').set_value('2026-01-02')
                next(x for x in at.text_area if x.label=='訪談摘要（人工確認）').set_value('匿名介面測試')
                next(x for x in at.button if x.label=='儲存訪談').click().run()
                self.assertFalse(at.exception)
                self.assertTrue(at.success)
                at.run()
                next(x for x in at.selectbox if x.label=='新增或修改訪談').set_value(1).run()
                next(x for x in at.text_area if x.label=='訪談摘要（人工確認）').set_value('匿名修改完成')
                next(x for x in at.button if x.label=='儲存訪談').click().run()
                self.assertFalse(at.exception)
                from hub.db import connect
                with closing(connect(Path(tmp)/'hub.sqlite3')) as c, c:
                    self.assertEqual(c.execute('SELECT summary FROM interviews').fetchone()[0],'匿名修改完成')
                at.sidebar.radio[0].set_value('全站資料搜尋').run()
                at.text_input[0].set_value('INT-01').run()
                self.assertFalse(at.exception)
                self.assertTrue(any('匿名修改完成' in df.value.to_string() for df in at.dataframe))
            finally:
                if previous is None: os.environ.pop('UAV_HUB_DATA',None)
                else: os.environ['UAV_HUB_DATA']=previous
