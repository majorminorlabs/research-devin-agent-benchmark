#!/usr/bin/env python3
"""Re-score existing E007 E006 Medium/Max workspaces with clean frozen evaluator copies."""
import json, pathlib, shutil, subprocess, sys, hashlib
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
from validate_experiment_006_runtime import commands_for_case,docker_prefix,shell_script,parse_container_output
R=pathlib.Path(__file__).resolve().parents[1]; P=R.parent/'devin-agent-benchmark-e007-private'; OUT=R.parent/'devin-agent-benchmark-e008-private'/'evaluator-recheck'; OUT.mkdir(parents=True,exist_ok=True)
config=json.loads((R/'manifests/experiment-006-config.json').read_text()); hist=json.loads((R/'<WORKDIR>/experiment-006-private/historical-manifest.json').read_text()); hist_by={x['case_id']:x for x in hist['cases']}; conf_by={x['experiment_case_id']:x for x in config['cases']}
results=[]
for cdir in sorted((R/'<WORKDIR>/experiment-006-private/evaluation').iterdir()):
 if not cdir.is_dir() or not cdir.name.startswith('E006-'): continue
 cid=cdir.name; clean=OUT/'clean-evaluators'/cid
 if clean.exists(): shutil.rmtree(clean)
 clean.parent.mkdir(parents=True,exist_ok=True)
 shutil.copytree(cdir,clean,ignore=shutil.ignore_patterns('__pycache__','*.pyc','.pytest_cache'))
 hc=hist_by.get(cid); cm=conf_by[cid]
 pubs=commands_for_case(cid,cm,hc)
 commands=[(f'public-{i}',cmd) for i,cmd in enumerate(pubs,1)]+[('held-out',f'python -m pytest -q /control/evaluation/{cid}/test_behavior.py'),('regression',f'python -m pytest -q /control/evaluation/{cid}/test_regression.py')]
 for effort,tag in [('medium','MEDIUM'),('high','HIGH'),('max','MAX')]:
  rid=f'E007-{cid}-{tag}'; ws=P/'workspaces'/rid; out=OUT/'results'/rid; out.mkdir(parents=True,exist_ok=True)
  command=docker_prefix(config,ws,clean,out,cid)+['-c',shell_script(commands)]
  proc=subprocess.run(command,text=True,capture_output=True,timeout=1800,check=False)
  try: parsed=parse_container_output(proc.stdout or '',commands); ok=all(x['status']=='pass' for k,x in parsed.items() if k.startswith('public-')) and parsed['held-out']['status']=='pass' and parsed['regression']['status']=='pass'; status='valid'
  except SystemExit as e: parsed={'parse_error':str(e)}; ok=None; status='evaluator_infrastructure_invalid'
  rec={'run_id':rid,'case_id':cid,'effort':effort,'recheck_status':status,'task_success':ok,'evaluator_results':parsed,'docker_returncode':proc.returncode,'stdout':proc.stdout or '', 'stderr':proc.stderr or '', 'source_evaluator_path':str(cdir),'clean_evaluator_path':str(clean),'cleaned_generated_cache_only':True}
  (out/'recheck.json').write_text(json.dumps(rec,indent=2,sort_keys=True)+'\n'); results.append(rec); print(json.dumps({'run_id':rid,'status':status,'task_success':ok}),flush=True)
(OUT/'E008-E007-EVALUATOR-RECHECK.jsonl').write_text(''.join(json.dumps(x,sort_keys=True)+'\n' for x in results))
