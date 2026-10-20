#!/usr/bin/env python3
"""Rebuild E007-RUNS.jsonl from frozen matrix records and captured outputs."""
import json
from pathlib import Path
R=Path(__file__).resolve().parents[1]; A=R/'artifacts'/'experiment-007'; P=R.parent/'devin-agent-benchmark-e007-private'
m=json.loads((A/'E007-MANIFEST.json').read_text()); records=[]
for run in m['run_order']:
 p=P/'outputs'/run['run_id']; w=P/'workspaces'/run['run_id']; meta=p/'container-run-result.json'; sess=p/'devin-session-export.json'; ev=p/'evaluation'/'evaluation-result.json'
 rec={**run,'run_status':'not_started','start_timestamp':None,'end_timestamp':None,'wall_clock_seconds':None,'success':None,'heldout_result':None,'regression_result':None,'public_result':None,'infrastructure_status':'not_started','failure_classification':None,'session_model_name':None,'generation_model_ids':[],'agent_steps':None,'input_tokens':None,'output_tokens':None,'cached_tokens':None,'total_tokens':None,'billed_usage':None,'direct_cost':None,'files_changed':None,'lines_added':None,'lines_removed':None,'commands_executed':None,'intervention_count':0,'evaluator_output':None,'session_export':str(sess) if sess.exists() else None}
 if w.exists() or p.exists(): rec['run_status']='running'
 if meta.exists():
  x=json.loads(meta.read_text()); rec.update({'start_timestamp':x.get('started_at_utc'),'end_timestamp':x.get('ended_at_utc'),'wall_clock_seconds':x.get('wall_time_seconds'),'container_returncode':x.get('returncode'),'timed_out':x.get('timed_out'),'intervention_count':x.get('intervention_count',0),'infrastructure_status':'pending_evaluator' if x.get('returncode')==0 else 'pending_classification'})
  rec['run_status']='awaiting_evaluator' if x.get('returncode')==0 else 'container_error'
 if sess.exists():
  s=json.loads(sess.read_text()); agent=s.get('agent') or {}; steps=s.get('steps') or []; fm=s.get('final_metrics') or {}
  rec['session_model_name']=agent.get('model_name'); rec['generation_model_ids']=sorted({z.get('extra',{}).get('generation_model') for z in steps if isinstance(z,dict) and z.get('extra',{}).get('generation_model')})
  rec.update({'agent_steps':fm.get('total_steps',len(steps)),'input_tokens':fm.get('total_prompt_tokens'),'output_tokens':fm.get('total_completion_tokens'),'cached_tokens':fm.get('total_cached_tokens')})
  if rec['input_tokens'] is not None and rec['output_tokens'] is not None: rec['total_tokens']=rec['input_tokens']+rec['output_tokens']
  # A desktop/control-plane interruption can occur after Devin has emitted a
  # complete final response but before the outer Docker wrapper writes its
  # timing/exit-code record. Preserve that session for evaluation while
  # explicitly marking the missing execution metadata; never invent a return
  # code or duration.
  if sess.exists() and not meta.exists() and isinstance(s.get('steps'),list) and s.get('steps') and s.get('final_metrics'):
   rec['run_status']='awaiting_evaluator'; rec['infrastructure_status']='execution_metadata_incomplete'
   rec['execution_record_missing']=True
 if ev.exists():
  e=json.loads(ev.read_text()); rec.update({'run_status':'complete','success':bool(e.get('task_success')),'public_result':(e.get('tests_after') or e.get('public') or {}).get('overall') or (e.get('public') or {}).get('status'),'heldout_result':(e.get('heldout_tests') or e.get('heldout') or {}).get('overall') or (e.get('heldout') or {}).get('status'),'regression_result':(e.get('regression_tests') or e.get('regression') or {}).get('overall') or (e.get('regression') or {}).get('status'),'infrastructure_status':e.get('evaluation_status'),'failure_classification':e.get('failure_classification') or e.get('failure_summary') or ([k for k,v in [('public',e.get('tests_after') or e.get('public')),('heldout',e.get('heldout_tests') or e.get('heldout')),('regression',e.get('regression_tests') or e.get('regression'))] if isinstance(v,dict) and (v.get('overall') or v.get('status')) not in ('pass','passed')] if not e.get('task_success') else None),'evaluator_output':str(ev)})
  patch=e.get('patch') or {}; rec['files_changed']=patch.get('changed_files'); rec['lines_added']=(patch.get('line_counts') or {}).get('additions',patch.get('additions')); rec['lines_removed']=(patch.get('line_counts') or {}).get('deletions',patch.get('deletions'))
 records.append(rec)
(A/'E007-RUNS.jsonl').write_text(''.join(json.dumps(x,sort_keys=True)+'\n' for x in records))
complete=[x for x in records if x['run_status']=='complete']
def score(rows): return {'successes':sum(x['success'] is True for x in rows),'n':len(rows)}
summary={'experiment_id':'E007','status':'complete' if len(complete)==90 else 'in_progress','planned_runs':90,'completed_runs':len(complete),'pending_runs':90-len(complete),'scores':{e:score([x for x in complete if x['reasoning_effort']==e]) for e in ('medium','high','max')},'tier_scores':{d:{e:score([x for x in complete if x['difficulty']==d and x['reasoning_effort']==e]) for e in ('medium','high','max')} for d in ('moderate','hard','very-hard')},'infrastructure_errors':sum(x['run_status']=='container_error' for x in records)}
(A/'E007-RESULTS.json').write_text(json.dumps(summary,indent=2)+'\n')
print(json.dumps({'runs':len(records),'complete':len(complete),'awaiting_evaluator':sum(x['run_status']=='awaiting_evaluator' for x in records),'running':sum(x['run_status']=='running' for x in records),'container_errors':summary['infrastructure_errors']}))
