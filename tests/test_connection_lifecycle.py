"""確保暫存資料庫清除前已關閉連線，不依賴垃圾回收釋放 Windows 檔案鎖。"""
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from hub import db

class ConnectionLifecycle(unittest.TestCase):
    def test_init_closes_connection(self):
        captured=[]
        real_connect=db.connect
        def capture(path):
            c=real_connect(path)
            captured.append(c)
            return c
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(db,'connect',side_effect=capture):
                db.init(Path(directory)/'test.sqlite3')
            self.assertEqual(len(captured),1)
            with self.assertRaises(sqlite3.ProgrammingError):
                captured[0].execute('SELECT 1')

    def test_init_closes_connection_on_error(self):
        with tempfile.TemporaryDirectory() as directory:
            c=db.connect(Path(directory)/'newer.sqlite3')
            c.execute('PRAGMA user_version=2')
            with patch.object(db,'connect',return_value=c):
                with self.assertRaises(ValueError): db.init(Path(directory)/'newer.sqlite3')
            with self.assertRaises(sqlite3.ProgrammingError): c.execute('SELECT 1')

    def test_environment_checker_subprocess(self):
        root=Path(__file__).resolve().parents[1]
        result=subprocess.run([sys.executable,str(root/'check_environment.py')],cwd=root,capture_output=True,text=True,encoding='utf-8',env={**__import__('os').environ,'PYTHONIOENCODING':'utf-8'})
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertIn('SQLite：正常',result.stdout)
        self.assertIn('檢查完成',result.stdout)
