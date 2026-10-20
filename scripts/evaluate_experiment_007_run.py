#!/usr/bin/env python3
"""Run the original frozen evaluator for one closed E007 workspace."""
import argparse,hashlib,json,os,shlex,subprocess,sys
from datetime import datetime,timezone
from pathlib import Path
REPO=Path(__file__).resolve().parents[1]; PRIVATE=REPO.parent/'devin-agent-benchmark-e007-private'; OUT=REPO/'artifacts'/'experiment-007'
def readj(p): return json.loads(p.read_text())
def run(cmd,cwd,env=None,timeout=1800):
 p=subprocess.run(cmd,cwd=cwd,env=env,text=True,capture_output=True,timeout=timeout,check=False)
 return {'command':cmd,'cwd':str(cwd),'returncode':p.returncode,'status':'pass' if p.returncode==0 else 'fail','stdout':p.stdout,'stderr':p.stderr}
def main():
 ap=argparse.ArgumentParser(); ap.add_argument('--run-id',required=True); a=ap.parse_args()
 m=readj(OUT/'E007-MANIFEST.json'); r=next((x for x in m['run_order'] if x['run_id']==a.run_id),None)
 if r is None: raise SystemExit('unknown E007 run')
 c=next(x for x in m['cases'] if x['case_id']==r['case_id']); ws=PRIVATE/'workspaces'/r['run_id']; raw=PRIVATE/'outputs'/r['run_id']; dest=raw/'evaluation'
 if not ws.is_dir() or not (raw/'devin-session-export.json').is_file(): raise SystemExit('only a closed run with a session export can be evaluated')
 if dest.exists() and (dest/'evaluation-result.json').exists(): raise SystemExit('evaluation already exists; refusing to overwrite')
 dest.mkdir(parents=True,exist_ok=True); e=c['original_experiment']; case=c['case_id']; result={'schema_version':1,'experiment_id':'E007','run_id':r['run_id'],'case_id':case,'difficulty':c['difficulty'],'model':r['model'],'effort':r['reasoning_effort'],'evaluated_at_utc':datetime.now(timezone.utc).isoformat(),'evaluation_status':'OK'}
 if e=='experiment-002':
  cid=c['source_case_id']; source=REPO.parent/'devin-agent-benchmark-cases-work'/cid; audit=json.loads((source.parent/f'{cid}.leak-audit.json').read_text())
  prompt=(REPO/'prompts/experiment-001'/f'{cid}.md').read_bytes(); assert audit['status']=='pass' and (ws/'TASK.md').read_bytes()==prompt
  (ws.parent/f'{ws.name}.leak-audit.json').write_text(json.dumps({'audit_version':1,'status':'pass','case_id':cid,'basis':'Inherited from passing frozen E002 sanitized source audit. E007 copied unchanged audited input and restored the byte-identical frozen prompt before execution.','parent_audit':str(source.parent/f'{cid}.leak-audit.json'),'parent_export_sha256':audit.get('export_sha256'),'prompt_sha256':hashlib.sha256(prompt).hexdigest(),'problems':[]},indent=2)+'\n')
  rr=readj(raw/'container-run-result.json'); runner={'run_id':r['run_id'],'case_id':cid,'condition':r['reasoning_effort'].upper(),'effort_level':r['reasoning_effort'],'model':r['model'],'started_at':rr.get('started_at_utc'),'ended_at':rr.get('ended_at_utc'),'elapsed_seconds':rr.get('wall_time_seconds'),'steps':None,'interventions':[],'termination_reason':'timeout' if rr.get('timed_out') else 'completed','agent':{'name':'Devin','cli_version':'3000.10.21 (611c1cba)','model':r['model'],'model_family':'SWE-2'}}
  (raw/'runner-result.json').write_text(json.dumps(runner,indent=2)+'\n')
  cmd=[sys.executable,str(REPO/'scripts/evaluate_run.py'),'--manifest',str(REPO/'manifests/experiment-001.json'),'--case-id',cid,'--run-root',str(raw),'--workspace',str(ws),'--output-dir',str(dest),'--baseline-dir',str(REPO.parent/'devin-agent-benchmark-cases-work'/f'{cid}.baseline'),'--heldout-metadata',str(REPO/'evaluation/experiment-001'/cid/'metadata.json'),'--env-root',str(REPO.parent/'devin-agent-benchmark-evaluator-envs/experiment-001')]
  p=subprocess.run(cmd,text=True,capture_output=True,check=False); (dest/'evaluator.stdout.txt').write_text(p.stdout); (dest/'evaluator.stderr.txt').write_text(p.stderr)
  if p.returncode==2: result.update({'evaluation_status':'EVALUATION_ERROR','infrastructure_status':'evaluator_error','error':p.stderr[-2000:]})
  else: return 0
 elif e=='experiment-004':
  ev=REPO.parent/'devin-agent-benchmark-e004-private'/'evaluation'/case; env=os.environ.copy(); env['PYTHONPATH']=os.pathsep.join([str(ws/'src'),str(ev)])
  commands={'public':[sys.executable,'-m','unittest','discover','-s','tests','-v'],'heldout':[sys.executable,'-m','unittest','discover','-s',str(ev),'-p','test_behavior.py','-v'],'regression':[sys.executable,'-m','unittest','discover','-s',str(ev),'-p','test_regression.py','-v']}
  result.update({k:run(v,ws,env) for k,v in commands.items()}); result['task_success']=all(result[k]['status']=='pass' for k in ('public','heldout','regression'))
 elif e=='experiment-005':
  private=REPO/'<WORKDIR>/experiment-005-private'; ev=private/'evaluation'/case; historical=case.startswith('E005-K'); env=os.environ.copy()
  if historical:
   hist=readj(private/'historical-manifest.json'); hc=next(x for x in hist['cases'] if x['case_id']==case); py=private/'venv-py38/bin/python'; env['PYTHONPATH']=str(ws); commands={'public':[([str(py)]+shlex.split(cmd)[1:]) for cmd in hc['test_command']]}
   pycmd=str(py)
  else:
   pycmd=sys.executable; env['PYTHONPATH']=os.pathsep.join([str(ws/'src'),str(ev)])
   commands={'public':[[pycmd,'-m','unittest','discover','-s','tests','-v']]}
  held=[pycmd,'-m','unittest','discover','-s',str(ev),'-p','test_behavior.py','-v']; reg=[pycmd,'-m','unittest','discover','-s',str(ev),'-p','test_regression.py','-v']
  suite=[]
  for cmd in commands['public']:
   suite.append(run(cmd,ws,env))
  result['public']={'status':'pass' if all(x['status']=='pass' for x in suite) else 'fail','commands':suite}
  result['heldout']=run(held,ws,env); result['regression']=run(reg,ws,env); result['task_success']=all(result[k]['status']=='pass' for k in ('public','heldout','regression'))
 elif e=='experiment-006':
  from validate_experiment_006_runtime import commands_for_case,docker_prefix,shell_script,parse_container_output
  cfg=readj(REPO/'manifests/experiment-006-config.json'); priv=REPO/'<WORKDIR>/experiment-006-private'; ev=priv/'evaluation'/case; art=dest/'runtime'; art.mkdir(exist_ok=True)
  histm=readj(priv/'historical-manifest.json'); hc=next((x for x in histm['cases'] if x['case_id']==case),None); cm=next(x for x in cfg['cases'] if x['experiment_case_id']==case)
  pubs=commands_for_case(case,cm,hc); cmds=[(f'public-{i}',s) for i,s in enumerate(pubs,1)]+[('held-out',f'python -m pytest -q /control/evaluation/{case}/test_behavior.py'),('regression',f'python -m pytest -q /control/evaluation/{case}/test_regression.py')]
  script=shell_script(cmds); command=docker_prefix(cfg,ws,ev,art,case)+['-c',script]; p=subprocess.run(command,text=True,capture_output=True,timeout=1800,check=False); textout=p.stdout or ''
  parsed=parse_container_output(textout,cmds); public=[v for k,v in parsed.items() if k.startswith('public-')]; result['public']={'status':'pass' if all(x['status']=='pass' for x in public) else 'fail','commands':public}; result['heldout']=parsed['held-out']; result['regression']=parsed['regression']; result['task_success']=all(result[k]['status']=='pass' for k in ('public','heldout','regression'))
  (art/'evaluator.stdout.txt').write_text(textout); (art/'evaluator.stderr.txt').write_text(p.stderr or '')
 else: raise SystemExit(f'unknown parent experiment: {e}')
 result.setdefault('task_success',bool(result.get('task_success')))
 (dest/'evaluation-result.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n'); print(json.dumps({'run_id':r['run_id'],'success':result.get('task_success'),'evaluation_status':result.get('evaluation_status')})); return 0
if __name__=='__main__': raise SystemExit(main())
