#!/usr/bin/env python3
"""Score preserved E008 E002 sessions after repairing the local evaluator adapter."""
import hashlib,json,os,shutil,subprocess,sys
from pathlib import Path
from datetime import datetime,timezone
R=Path(__file__).resolve().parents[1]; A=R/'artifacts'/'experiment-008'; LED=A/'E008-RUNS.jsonl'; OUT=R.parent/'devin-agent-benchmark-e008-private'/'outputs'; SOURCE=R/'evaluation'/'experiment-001'

def read(p):return json.loads(Path(p).read_text())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def caches(root):
 out=[]
 for p in Path(root).rglob('*'):
  if p.is_dir() and p.name in {'__pycache__','.pytest_cache'}:out.append(p)
  elif p.is_file() and p.suffix=='.pyc':out.append(p)
 return out
def clean(root):
 gone=[]
 for p in sorted(caches(root),key=lambda x:len(x.parts),reverse=True):
  gone.append(str(p.relative_to(root)))
  if p.is_dir():shutil.rmtree(p,ignore_errors=True)
  else:p.unlink(missing_ok=True)
 return gone
def ignore(_d,names):return {n for n in names if n in {'__pycache__','.pytest_cache'} or n.endswith('.pyc')}
def main():
 rows=[json.loads(x) for x in LED.read_text().splitlines() if x.strip()]
 targets=[r for r in rows if r['run_id'].startswith('E008-E002-')]
 if len(targets)!=9:raise SystemExit(f'expected 9 preserved E002 attempts, got {len(targets)}')
 for row in targets:
  rid=row['run_id']; out=Path(row['output_dir']); ws=Path(row['workspace']); base=Path(row['baseline']); case=next(c for c in read(R/'artifacts/experiment-007/E007-MANIFEST.json')['cases'] if c['case_id']==row['case_id']); cid=case['source_case_id']; prompt=R/case['prompt']
  assert sha(prompt)==row['prompt_sha256'] and (ws/'TASK.md').read_bytes()==prompt.read_bytes()
  export=out/'devin-session-export.json'; assert export.is_file()
  # A new evaluator copy receives only frozen evaluation inputs; remove exactly the cache classes used in E008 clean rechecks.
  src=SOURCE/cid; ev=out/'post-harness-clean-evaluator'
  if ev.exists():raise SystemExit(f'refusing to overwrite prior adjudication evaluator {ev}')
  shutil.copytree(src,ev,ignore=ignore); removed=clean(ev); remaining=[str(p.relative_to(ev)) for p in caches(ev)]
  if remaining:raise SystemExit(f'evaluator sanitation failed for {rid}: {remaining}')
  work_removed=clean(ws)
  audit=ws.parent/f'{ws.name}.leak-audit.json'
  if not audit.is_file():
   parent=R.parent/'devin-agent-benchmark-cases-work'/cid; inherited=read(parent/f'{cid}.leak-audit.json')
   audit.write_text(json.dumps({'audit_version':1,'status':'pass','case_id':cid,'basis':'Inherited passing frozen E002 sanitized source audit; E008 exact source and prompt were re-staged.','parent_audit':str(parent/f'{cid}.leak-audit.json'),'parent_export_sha256':inherited.get('export_sha256'),'prompt_sha256':sha(prompt),'problems':[]},indent=2)+'\n')
  session=read(export); fm=session.get('final_metrics',{})
  rr={'run_id':rid,'condition':row['effort'].upper(),'effort_level':row['effort'],'started_at':row['started_at_utc'],'ended_at':row['ended_at_utc'],'elapsed_seconds':row['wall_time_seconds'],'steps':row['steps'],'interventions':[],'termination_reason':'timeout' if row['timed_out'] else 'completed','agent':{'name':'Devin','cli_version':'3000.10.21 (611c1cba)','model':row['model'],'model_family':'SWE-2'}}
  (out/'runner-result.json').write_text(json.dumps(rr,indent=2)+'\n')
  dest=out/'post-harness-evaluation'; dest.mkdir(exist_ok=True)
  cmd=[sys.executable,str(R/'scripts/evaluate_run.py'),'--manifest',str(R/'manifests/experiment-001.json'),'--case-id',cid,'--run-root',str(out),'--workspace',str(ws),'--output-dir',str(dest),'--baseline-dir',str(base),'--heldout-metadata',str(ev/'metadata.json'),'--env-root',str(R.parent/'devin-agent-benchmark-evaluator-envs/experiment-001')]
  started=datetime.now(timezone.utc).isoformat(); p=subprocess.run(cmd,text=True,capture_output=True,check=False,timeout=1800)
  (dest/'evaluator.stdout.txt').write_text(p.stdout or '');(dest/'evaluator.stderr.txt').write_text(p.stderr or '')
  if p.returncode not in (0,1): raise RuntimeError(f'{rid} clean evaluator infrastructure error: rc={p.returncode}: {(p.stderr or "")[-1200:]}')
  d=read(dest/'evaluation-result.json'); suites={'public':d['tests_after']['overall'],'heldout':d['heldout_tests']['overall'],'regression':d['regression_tests']['overall']}
  result={'run_id':rid,'case_id':row['case_id'],'effort':row['effort'],'session_id':session.get('session_id'),'adjudicated_at_utc':datetime.now(timezone.utc).isoformat(),'initial_local_adapter_status':'evaluator_infrastructure_invalid','initial_error':'KeyError: run_id; E008-to-E001 adapter field mapping failure before test execution','corrected_evaluator_status':'valid','task_success':d['task_success'],'suite_results':suites,'returncode':p.returncode,'evaluator_result_path':str(dest/'evaluation-result.json'),'evaluator_output_sha256':sha(dest/'evaluation-result.json'),'sanitation':{'verified_cache_free_before_evaluation':not remaining,'evaluator_copy':str(ev),'removed_evaluator_cache_paths':removed,'workspace_generated_caches_removed_before_re_evaluation':work_removed,'prompt_sha256_verified':True},'devin_session_rerun':False,'started_at_utc':started}
  (out/'evaluator-adjudication.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
  print(json.dumps({'run_id':rid,'corrected_status':'valid','task_success':d['task_success'],'suites':suites}),flush=True)
 # Add corrected score as an additional field; preserve initial failure status and result in every original ledger row.
 adjud={x['run_id']:read(OUT/x['run_id']/'evaluator-adjudication.json') for x in targets}
 for row in rows:
  if row['run_id'] in adjud:
   a=adjud[row['run_id']]
   row['initial_evaluator_infrastructure_status']=row['infrastructure_status']
   row['initial_evaluator_result']=row.get('evaluator_result')
   row['final_evaluation_status']=a['corrected_evaluator_status']
   row['final_task_success']=a['task_success']
   row['final_suite_results']=a['suite_results']
   row['evaluator_adjudication_path']=str(OUT/row['run_id']/'evaluator-adjudication.json')
   row['evaluator_sanitation_after_adapter_repair']=a['sanitation']
   row['evaluation_adapter_failure_preserved']=True
  else:
   row['final_evaluation_status']=row.get('infrastructure_status')
   row['final_task_success']=row.get('task_success')
   row['final_suite_results']=row.get('suite_results')
 tmp=LED.with_suffix('.jsonl.tmp');tmp.write_text(''.join(json.dumps(x,sort_keys=True)+'\n' for x in rows));os.replace(tmp,LED)
 summary={'planned_trials':33,'preserved_e002_sessions_adjudicated':len(adjud),'new_devin_sessions_for_adjudication':0,'e002_successes':sum(x['task_success'] is True for x in adjud.values()),'e002_failures':sum(x['task_success'] is False for x in adjud.values()),'adjudications':list(adjud.values())}
 (A/'E008-E002-ADJUDICATION.json').write_text(json.dumps(summary,indent=2,sort_keys=True)+'\n')
 print(json.dumps({'adjudicated':len(adjud),'successes':summary['e002_successes'],'failures':summary['e002_failures']}))
if __name__=='__main__':main()
