#!/usr/bin/env python3
"""Wait for E007 run outputs, apply the frozen evaluator, and sync records."""
import json,subprocess,sys,time
from pathlib import Path
REPO=Path(__file__).resolve().parents[1]; A=REPO/'artifacts'/'experiment-007'; P=REPO.parent/'devin-agent-benchmark-e007-private'
m=json.loads((A/'E007-MANIFEST.json').read_text())
for r in m['run_order']:
 raw=P/'outputs'/r['run_id']; meta=raw/'container-run-result.json'
 while not meta.exists():
  time.sleep(10)
 x=json.loads(meta.read_text())
 if x.get('returncode')!=0:
  print(json.dumps({'run_id':r['run_id'],'status':'container_exit_error','returncode':x.get('returncode'),'timed_out':x.get('timed_out')}),flush=True)
  continue
 if not (raw/'devin-session-export.json').exists():
  print(json.dumps({'run_id':r['run_id'],'status':'missing_session_export'}),flush=True); continue
 ev=raw/'evaluation'/'evaluation-result.json'
 if not ev.exists():
  p=subprocess.run([sys.executable,str(REPO/'scripts/evaluate_experiment_007_run.py'),'--run-id',r['run_id']],cwd=REPO.parent,text=True,capture_output=True)
  if p.returncode!=0:
   print(json.dumps({'run_id':r['run_id'],'status':'evaluator_error','returncode':p.returncode,'stderr':p.stderr[-1200:]}),flush=True); continue
  x=json.loads(ev.read_text()); print(json.dumps({'run_id':r['run_id'],'status':'evaluated','success':x.get('task_success')}),flush=True)
 subprocess.run([sys.executable,str(REPO/'scripts/sync_experiment_007_runs.py')],cwd=REPO.parent,capture_output=True,check=False)
print('E007 matrix outputs processed.',flush=True)
