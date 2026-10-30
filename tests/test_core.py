import unittest
import tempfile
from pathlib import Path
import sqlite3
from hub.db import *

class Core(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.path=Path(self.tmp.name)/'db.sqlite3'; init(self.path); self.c=connect(self.path)
    def tearDown(self):
        self.c.close(); self.tmp.cleanup()
    def source(self,**kw):
        v=dict(code='ANON-1',title='匿名測試文件',source_type='測試',provider='',date='',url='',file_path='',sha256=None,confidentiality='內部',notes='',confirmed=0); v.update(kw)
        return save_document(self.c,v,['INT-01'],['TW-LOG-001'])
    def test_seed_and_repeat(self):
        init(self.path)
        self.assertEqual(self.c.execute('SELECT count(*) FROM vendors').fetchone()[0],12)
        self.assertEqual(self.c.execute('SELECT count(*) FROM logs').fetchone()[0],8)
        self.assertFalse(self.c.execute("SELECT name FROM sqlite_master WHERE name LIKE '%visit%'").fetchall())
    def test_interview_edit_persist_search(self):
        with self.c:
            i=save_interview(self.c,'INT-01','2026-01-02','測試','匿名需求','待確認','匿名摘要')
            save_interview(self.c,'INT-01','2026-01-02','測試','修改需求','待確認','修改摘要',i)
        with connect(self.path) as c:
            self.assertEqual(c.execute("SELECT summary FROM interviews WHERE vendor_code LIKE '%INT-01%'").fetchone()[0],'修改摘要')
    def test_invalid_date_and_vendor(self):
        for vendor,date in [('INT-99','2026-01-01'),('INT-01','2026-02-30')]:
            with self.assertRaises(ValueError): save_interview(self.c,vendor,date,'','','','')
    def test_duplicate_and_rollback(self):
        with self.c: self.source()
        with self.assertRaises(sqlite3.IntegrityError):
            with self.c: self.source()
        self.assertEqual(self.c.execute('SELECT count(*) FROM documents').fetchone()[0],1)
    def test_history_requires_manual_verification(self):
        with self.assertRaises(ValueError): self.source(notes='TW-VISIT-001')
    def test_unconfirmed_source(self):
        with self.assertRaises(ValueError): self.source(confirmed=1)
        d=self.source()
        with self.assertRaises(ValueError): save_evidence(self.c,d,'匿名原文','第1段','摘要','待確認資訊','待確認','已確認','2026-01-01','',[],[], '')
    def test_evidence_relations_and_immutable(self):
        with self.c:
            d=self.source()
            e=save_evidence(self.c,d,'匿名原文','第1段','摘要','研究分析','研究推論','待確認','','',['INT-01'],[1,5],'物流、技術')
        self.assertEqual(self.c.execute('SELECT count(*) FROM evidence_kpis WHERE evidence_id=?',(e,)).fetchone()[0],2)
        self.assertEqual(self.c.execute('SELECT document_id FROM evidence WHERE id=?',(e,)).fetchone()[0],d)
        with self.assertRaises(sqlite3.IntegrityError): self.c.execute('UPDATE evidence SET original=? WHERE id=?',('覆寫',e))
    def test_database_backup(self):
        with self.c: save_interview(self.c,'INT-02','2026-01-01','測試','','','匿名')
        target=Path(self.tmp.name)/'backup.sqlite3'
        with sqlite3.connect(target) as b: self.c.backup(b)
        with connect(target) as b: self.assertEqual(b.execute('SELECT count(*) FROM interviews').fetchone()[0],1)

if __name__=='__main__': unittest.main()
