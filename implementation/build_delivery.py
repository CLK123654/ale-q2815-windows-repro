from __future__ import annotations
import argparse,atexit,csv,json,shutil,subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parent
REQUIRED={
 'README.txt','service_values.csv','hook_catalog.csv','release_policy.json',
 'starter_chart/Chart.yaml','starter_chart/values.yaml',
 'starter_chart/templates/workload.yaml','starter_chart/templates/tests.yaml'
}

def rows(path):
 with path.open(encoding='utf-8-sig',newline='') as handle:return list(csv.DictReader(handle))
def run(command):
 result=subprocess.run(command,text=True,capture_output=True,timeout=180)
 if result.returncode:raise RuntimeError(result.stdout+result.stderr)
 return result.stdout
def write_csv(path,fields,data):
 with path.open('w',encoding='utf-8',newline='') as handle:
  writer=csv.DictWriter(handle,fieldnames=fields,lineterminator='\n');writer.writeheader();writer.writerows(data)
def write_values(path,stage,hooks,policy):
 values=[
  'release:',f"  stage: {stage['stage']}",'workload:','  image:',
  f"    repository: {stage['workload_image']}",f"    tag: {stage['workload_tag']}",
  'service:',f"  port: {stage['service_port']}",f"  containerPort: {stage['container_port']}",
  'tests:','  image:',f"    repository: {stage['test_image']}",f"    tag: {stage['test_tag']}",
  f"  credentialSecret: {policy['credential_secret']}",f"  credentialKey: {policy['credential_key']}",
  f"  hookEvent: {policy['hook_event']}",'  deletePolicy:'
 ]
 values.extend(f'    - {item}' for item in policy['delete_policy'])
 values.extend([
  f"  activeDeadlineSeconds: {policy['active_deadline_seconds']}",
  f"  backoffLimit: {policy['backoff_limit']}",f"  restartPolicy: {policy['restart_policy']}",'  hooks:'
 ])
 for hook in hooks:
  values.extend([
   f"    - hookId: {hook['hook_id']}",f"      jobSuffix: {hook['job_suffix']}",
   f"      weight: {hook['weight']}",f"      path: {hook['path']}",
   f"      expectedStatus: {hook['expected_status']}",
   f"      requiresToken: {str(hook['requires_token'].lower()=='true').lower()}"
  ])
 path.write_text('\n'.join(values)+'\n',encoding='utf-8')
def main():
 parser=argparse.ArgumentParser();parser.add_argument('--input',required=True);parser.add_argument('--output',required=True);parser.add_argument('--helm',required=True);args=parser.parse_args()
 source=Path(args.input).resolve();output=Path(args.output).resolve()
 if output.exists():shutil.rmtree(output)
 ok={'value':False}
 def cleanup():
  if not ok['value'] and output.exists():shutil.rmtree(output)
 atexit.register(cleanup)
 present={p.relative_to(source).as_posix() for p in source.rglob('*') if p.is_file()}
 if present!=REQUIRED:raise ValueError('发布材料集合发生变化')
 stages=rows(source/'service_values.csv');hooks=rows(source/'hook_catalog.csv');policy=json.loads((source/'release_policy.json').read_text(encoding='utf-8'))
 if not stages or set(stages[0])!={'stage','release_name','namespace','workload_image','workload_tag','test_image','test_tag','service_port','container_port'}:raise ValueError('发布批次字段不完整')
 if not hooks or set(hooks[0])!={'hook_id','job_suffix','weight','path','expected_status','requires_token'}:raise ValueError('钩子目录字段不完整')
 if [x['stage'] for x in stages]!=policy['rollout_order']:raise ValueError('发布批次与分批顺序不一致')
 if len({x['stage'] for x in stages})!=len(stages) or len({x['release_name'] for x in stages})!=len(stages):raise ValueError('发布批次键重复')
 if len({x['hook_id'] for x in hooks})!=len(hooks) or len({x['weight'] for x in hooks})!=len(hooks):raise ValueError('钩子业务键或权重重复')
 if hooks!=sorted(hooks,key=lambda x:int(x['weight'])):raise ValueError('钩子目录未按权重排列')
 if any(x['requires_token'].lower() not in {'true','false'} for x in hooks):raise ValueError('凭据需求字段无效')
 if any(x['workload_tag']=='latest' or x['test_tag']=='latest' for x in stages):raise ValueError('发布镜像不能使用latest')
 if policy['active_deadline_seconds']!=policy['waiting_budget_seconds']:raise ValueError('等待预算与Job时限不一致')
 output.mkdir(parents=True);shutil.copytree(ROOT/'chart',output/'chart/stream-gateway');(output/'values').mkdir();(output/'renders').mkdir();(output/'reports').mkdir()
 inventory=[]
 for stage in stages:
  values=output/f"values/{stage['stage']}.yaml";write_values(values,stage,hooks,policy)
  run([args.helm,'lint',str(output/'chart/stream-gateway'),'-f',str(values),'--strict'])
  manifest=run([args.helm,'template',stage['release_name'],str(output/'chart/stream-gateway'),'-f',str(values),'--namespace',stage['namespace']])
  (output/f"renders/{stage['stage']}.yaml").write_text(manifest.replace('\r\n','\n'),encoding='utf-8')
  for hook in hooks:
   inventory.append({
    'stage':stage['stage'],'release_name':stage['release_name'],'namespace':stage['namespace'],
    'hook_id':hook['hook_id'],'job_name':stage['release_name']+'-'+hook['job_suffix'],
    'weight':hook['weight'],'path':hook['path'],'expected_status':hook['expected_status'],
    'requires_token':hook['requires_token'].lower(),'hook_event':policy['hook_event'],
    'delete_policy':','.join(policy['delete_policy']),'active_deadline_seconds':policy['active_deadline_seconds']
   })
 write_csv(output/'reports/hook_inventory.csv',['stage','release_name','namespace','hook_id','job_name','weight','path','expected_status','requires_token','hook_event','delete_policy','active_deadline_seconds'],inventory)
 plan=[]
 for order,stage in enumerate(stages,1):
  plan.append({
   'rollout_order':order,'stage':stage['stage'],'release_name':stage['release_name'],'namespace':stage['namespace'],
   'change_window_start':policy['change_window']['start'],'change_window_end':policy['change_window']['end'],
   'impact':policy['impact'],'waiting_budget_seconds':policy['waiting_budget_seconds'],
   'observation_minutes':policy['observation_minutes'],'observation_items':'、'.join(policy['observation_items']),
   'rollback':policy['rollback']
  })
 write_csv(output/'reports/release_plan.csv',['rollout_order','stage','release_name','namespace','change_window_start','change_window_end','impact','waiting_budget_seconds','observation_minutes','observation_items','rollback'],plan)
 (output/'RELEASE-NOTES.md').write_text(
  f"维护窗口为{policy['change_window']['start']}至{policy['change_window']['end']}，影响范围是{policy['impact']}。先处理{stages[0]['stage']}批次，观察{policy['observation_minutes']}分钟，再决定是否处理{stages[1]['stage']}批次。观察{('、'.join(policy['observation_items']))}。异常时{policy['rollback']}。\n",
  encoding='utf-8')
 (output/'README.txt').write_text('chart保存发布Chart，values与renders按发布批次区分。hook_inventory.csv供发布经理审阅钩子对象，release_plan.csv用于安排窗口和批次。集群操作人员接手后执行Job并检查端点状态。\n',encoding='utf-8')
 ok['value']=True
if __name__=='__main__':main()
