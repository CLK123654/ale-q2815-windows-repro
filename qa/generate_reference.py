from __future__ import annotations
import os,shutil,subprocess,sys,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];WORK=ROOT/'work-reference';TASK=ROOT/'task';EVIDENCE=ROOT/'evidence'
if WORK.exists():shutil.rmtree(WORK)
WORK.mkdir();EVIDENCE.mkdir(exist_ok=True)
with zipfile.ZipFile(TASK/'输入数据包.zip') as archive:archive.extractall(WORK)
result=subprocess.run([sys.executable,str(ROOT/'implementation/build_delivery.py'),'--input',str(WORK/'input_data'),'--output',str(WORK/'output'),'--helm',os.environ['HELM_PATH']],text=True,capture_output=True,timeout=300)
if result.returncode:raise SystemExit(result.stdout+result.stderr)
with zipfile.ZipFile(EVIDENCE/'reference-candidate.zip','w',zipfile.ZIP_DEFLATED,compresslevel=9) as archive:
 for path in sorted((WORK/'output').rglob('*')):
  if path.is_file():archive.write(path,path.relative_to(WORK).as_posix())
(EVIDENCE/'reference-generation.json').write_text('{"result":"PASS","source":"Windows Helm3.18.4"}\n',encoding='utf-8')
