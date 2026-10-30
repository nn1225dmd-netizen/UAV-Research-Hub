from contextlib import closing
import sys
import importlib
from pathlib import Path
print('UAV Research Hub 環境檢查')
errors=[]
if sys.version_info < (3,10): errors.append('需要 Python 3.10 或更新版本')
for name in ['streamlit','pandas','openpyxl','docx','pymupdf']:
    try: importlib.import_module(name); print(name+'：正常')
    except ImportError: errors.append(name+' 尚未安裝，請執行首次安裝')
try:
    from hub.db import init,connect
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        p=Path(d)/'test.sqlite3'; init(p)
        with closing(connect(p)) as c: assert c.execute('SELECT count(*) FROM vendors').fetchone()[0]==12
    print('SQLite：正常')
except Exception as e: errors.append('資料庫檢查失敗：'+str(e))
for e in errors: print(e)
print('檢查完成' if not errors else '請先修正上述問題')
sys.exit(bool(errors))
