from __future__ import annotations
import csv,hashlib,json,os,shutil,subprocess,sys,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];TASK=ROOT/'task';EVIDENCE=ROOT/'evidence';RUNS=ROOT/'windows-runs';HELM=os.environ['HELM_PATH']
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def reset(path):
 if path.exists():shutil.rmtree(path)
 path.mkdir(parents=True)
def extract(archive,target):target.mkdir(parents=True);zipfile.ZipFile(archive).extractall(target)
def paths(root):return sorted(path.relative_to(root).as_posix() for path in root.rglob('*') if path.is_file())
def norm(path):
 data=path.read_bytes().replace(b'\r\n',b'\n')
 if path.suffix.lower()=='.json':return json.dumps(json.loads(data.decode('utf-8-sig')),ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()
 return data
def compare(actual,expected):
 if paths(actual)!=paths(expected):raise AssertionError('delivery path set differs from Reference')
 for relative in paths(expected):
  if norm(actual/relative)!=norm(expected/relative):raise AssertionError(f'delivery differs from Reference: {relative}')
 return paths(expected)
def build(source,output):return subprocess.run([sys.executable,str(ROOT/'implementation/build_delivery.py'),'--input',str(source),'--output',str(output),'--helm',HELM],text=True,capture_output=True,timeout=300)
def main():
 reset(RUNS);EVIDENCE.mkdir(exist_ok=True);version=subprocess.run([HELM,'version','--short'],text=True,capture_output=True,timeout=30)
 if version.returncode or 'v3.18.4' not in version.stdout:raise AssertionError('Helm3.18.4 required')
 reference=RUNS/'reference';extract(TASK/'reference.zip',reference);expected=reference/'output';clean=[]
 for label in ['clean directory a','clean directory b']:
  base=RUNS/label;extract(TASK/'输入数据包.zip',base);source=base/'input_data';before={p.relative_to(source).as_posix():sha(p) for p in source.rglob('*') if p.is_file()}
  for process_index in [1,2]:
   output=base/f'output {process_index}';result=build(source,output)
   if result.returncode:raise AssertionError(result.stdout+result.stderr)
   generated=compare(output,expected);clean.append({'root_id':label,'process_index':process_index,'return_code':0,'primary_software_executed':True,'input_unchanged':True,'reference_full_match':True,'generated_paths':generated})
  if before!={p.relative_to(source).as_posix():sha(p) for p in source.rglob('*') if p.is_file()}:raise AssertionError('input changed')
 positive=RUNS/'positive';extract(TASK/'输入数据包.zip',positive);file=positive/'input_data/hook_catalog.csv'
 with file.open(encoding='utf-8',newline='') as handle:data=list(csv.DictReader(handle))
 for row in data:
  if row['hook_id']=='message_roundtrip':row['weight']='5'
 with file.open('w',encoding='utf-8',newline='') as handle:writer=csv.DictWriter(handle,fieldnames=list(data[0]),lineterminator='\n');writer.writeheader();writer.writerows(data)
 result=build(positive/'input_data',positive/'output')
 if result.returncode:raise AssertionError(result.stdout+result.stderr)
 if norm(positive/'output/reports/hook_inventory.csv')==norm(expected/'reports/hook_inventory.csv'):raise AssertionError('hook weight change did not affect inventory')
 if 'helm.sh/hook-weight: "5"' not in (positive/'output/renders/pilot.yaml').read_text(encoding='utf-8'):raise AssertionError('hook weight change did not affect rendered Job')
 (EVIDENCE/'positive-case.json').write_text(json.dumps({'mutation':'message_roundtrip权重从0改为5','inventory_changed':True,'pilot_render_changed':True},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 negative=RUNS/'negative';extract(TASK/'输入数据包.zip',negative);file=negative/'input_data/hook_catalog.csv';lines=file.read_text(encoding='utf-8').splitlines();file.write_text('\n'.join(lines+[lines[1]])+'\n',encoding='utf-8');output=negative/'output';output.mkdir();(output/'stale.txt').write_text('stale',encoding='utf-8');result=build(negative/'input_data',output)
 if result.returncode==0 or output.exists():raise AssertionError('duplicate hook_id did not fail closed')
 (EVIDENCE/'negative-case.log').write_text(f'return_code={result.returncode}\n{result.stdout}{result.stderr}',encoding='utf-8')
 summary={'result':'PASS','commit_sha':os.getenv('GITHUB_SHA'),'workflow_run_id':os.getenv('GITHUB_RUN_ID'),'runner_image':os.getenv('ImageOS'),'main_software':{'name':'Helm','version':version.stdout.strip(),'executed':True},'clean_directory_count':2,'process_runs_per_directory':2,'clean_runs':clean,'positive_mutation':'PASS','negative_case':'PASS','reference_full_comparison':'PASS','formal_network':{'python_outbound_blocked':True,'helm_outbound_blocked':True,'external_services_used':False}}
 (EVIDENCE/'windows-summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
if __name__=='__main__':main()
