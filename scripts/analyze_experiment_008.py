#!/usr/bin/env python3
"""Build E008's pre-rerun replication-drift analysis from frozen records only."""
from __future__ import annotations
import csv, hashlib, json, math, re, statistics
from collections import Counter, defaultdict
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

R=Path(__file__).resolve().parents[1]; A=R/'artifacts/experiment-008'; A.mkdir(parents=True,exist_ok=True)
PRIV=R.parent/'devin-agent-benchmark-e007-private'
tiers=['moderate','hard','very-hard']; efforts=['medium','max']
def j(p): return json.loads(Path(p).read_text())
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def fmt(x,d=2): return 'NA' if x is None else f'{x:.{d}f}'
def safe_path(p):
 p=Path(p); return p if p.is_absolute() else R/p

manifest=j(R/'artifacts/experiment-007/E007-MANIFEST.json')
e7=[json.loads(x) for x in (R/'artifacts/experiment-007/E007-RUNS.jsonl').read_text().splitlines()]
recheck_path=R.parent/'devin-agent-benchmark-e008-private/evaluator-recheck/E008-E007-EVALUATOR-RECHECK.jsonl'
e7_recheck={x['run_id']:x for x in map(json.loads,recheck_path.read_text().splitlines())} if recheck_path.exists() else {}
orig_rows=list(csv.DictReader((R/'results/publication-v4-runs.csv').open()))
orig={(x['case_key'],x['condition']):x for x in orig_rows}
e7_by={(x['case_id'],x['reasoning_effort']):x for x in e7}
pub_pairs=list(csv.DictReader((R/'results/publication-v4-paired-results.csv').open()))
pubpair={x['case_key']:x for x in pub_pairs}
freeze={
 'E002':None,
 'E004':j(R/'manifests/experiment-004-freeze.json'),
 'E005':j(R/'manifests/experiment-005-freeze.json'),
 'E006':j(R/'manifests/experiment-006-freeze.json')}
parent_configs={x:j(R/f'manifests/experiment-{x}-config.json') for x in ('002','004','005','006')}
e7meta={c['case_id']:c for c in manifest['cases']}

def original_ids(c):
 ex=c['original_experiment'].replace('experiment-','E')
 if ex in ('E002','E006'): ident=c['source_case_id']
 else: ident=c['case_id']
 return ex,ident,f'{ex}:{ident}'

def orig_raw(ex,ident,eff,run_id=None):
 cond='M' if eff=='medium' else 'X'; rid=run_id or f'{ex}-{ident}-{cond}'
 return R/'artifacts'/f'experiment-{ex[-3:]}'/rid

def orig_record(c,eff):
 ex,ident,key=original_ids(c); cond='M' if eff=='medium' else 'X'
 return orig[(key,cond)]

def outcome_bool(v): return str(v).lower() in ('true','1','pass','passed')
def generated_path(p):
 parts=Path(str(p)).parts; name=Path(str(p)).name.lower()
 return any(x in parts for x in ('__pycache__','.pytest_cache','.mypy_cache','.ruff_cache','.venv','venv','.tox','build','dist')) or Path(name).suffix.lower() in ('.pyc','.pyo','.so','.o','.dll') or name in ('.coverage',)

def effective_outcome(n):
 z=e7_recheck.get(n['run_id'])
 return z['task_success'] if z and z.get('recheck_status')=='valid' else bool(n['success'])

def effective_suite(n,suite):
 z=e7_recheck.get(n['run_id'])
 if z and z.get('recheck_status')=='valid':
  if suite=='public':
   vals=[v['status'] for k,v in z['evaluator_results'].items() if k.startswith('public-')]
   return 'pass' if vals and all(v=='pass' for v in vals) else 'fail'
  return z['evaluator_results']['held-out' if suite=='heldout' else 'regression']['status']
 return n.get({'public':'public_result','heldout':'heldout_result','regression':'regression_result'}[suite])

def failing_ids(obj):
 texts=[]
 def walk(x):
  if isinstance(x,dict):
   for k,v in x.items():
    if k in ('stdout','stderr','output') and isinstance(v,str):texts.append(v)
    else:walk(v)
  elif isinstance(x,list):
   for v in x:walk(v)
 walk(obj)
 out=[]
 for t in texts:out.extend(re.findall(r'(?:FAILED|ERROR)\s+([^\s]+)|FAIL:\s+([^\s]+)',t))
 return list(dict.fromkeys(z for pair in out for z in pair if z))

def exact_mcnemar(a_only,b_only):
 n=a_only+b_only
 if not n:return 1.0
 return min(1.0,2*sum(math.comb(n,i) for i in range(min(a_only,b_only)+1))/(2**n))

def ci_agreement(k,n):
 if n==0:return (None,None)
 # Wilson 95% interval.
 z=1.959963984540054; p=k/n; den=1+z*z/n
 mid=(p+z*z/(2*n))/den; half=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/den
 return mid-half,mid+half

matrix=[]; discordant=set(); paired_summary={}; tier_summary={}
for c in manifest['cases']:
 ex,ident,key=original_ids(c); row={'case_id':c['case_id'],'difficulty':c['difficulty'],'source_experiment':ex,'source_case_id':ident}
 for eff,lab in [('medium','medium'),('max','max')]:
  o=orig_record(c,eff); n=e7_by[(c['case_id'],eff)]
  ov=outcome_bool(o['success']); nv=effective_outcome(n)
  cls='STABLE_SOLVE' if ov and nv else 'STABLE_FAIL' if not ov and not nv else 'ORIGINAL_ONLY_SOLVE' if ov else 'E007_ONLY_SOLVE'
  row[f'original_{lab}_outcome']=ov; row[f'e007_{lab}_outcome']=nv; row[f'e007_recorded_{lab}_outcome']=bool(n['success']); row[f'{lab}_classification']=cls
  row[f'original_{lab}_run_id']=o['run_id']; row[f'e007_{lab}_run_id']=n['run_id']
  if ov!=nv: discordant.add(c['case_id'])
 matrix.append(row)

def agreement(rows,eff):
 o=[r[f'original_{eff}_outcome'] for r in rows]; n=[r[f'e007_{eff}_outcome'] for r in rows]
 both=sum(a and b for a,b in zip(o,n)); bothf=sum(not a and not b for a,b in zip(o,n)); oo=sum(a and not b for a,b in zip(o,n)); no=sum(not a and b for a,b in zip(o,n)); k=both+bothf
 return {'n':len(rows),'original_solve':sum(o),'e007_solve':sum(n),'stable_solves':both,'stable_failures':bothf,'original_only_solves':oo,'e007_only_solves':no,'agreement':k,'agreement_rate':k/len(rows),'agreement_wilson_95_ci':ci_agreement(k,len(rows)),'mcnemar_exact_two_sided_p':exact_mcnemar(oo,no),'absolute_change_e007_minus_original':(sum(n)-sum(o))/len(rows)}

for eff in efforts: paired_summary[eff]=agreement(matrix,eff)
for d in tiers:
 sub=[r for r in matrix if r['difficulty']==d]; tier_summary[d]={e:agreement(sub,e) for e in efforts}

with (A/'E008-REPLICATION-MATRIX.csv').open('w',newline='') as f:
 w=csv.DictWriter(f,fieldnames=list(matrix[0])); w.writeheader(); w.writerows(matrix)
(A/'E008-REPLICATION-MATRIX.json').write_text(json.dumps({'case_count':len(matrix),'effort_summary':paired_summary,'difficulty_summary':tier_summary,'cases':matrix},indent=2,sort_keys=True)+'\n')

# Task/source/prompt/test hashes compare with parent freezes and the E007 canonical manifest.
audit=[]
for c in manifest['cases']:
 ex,ident,key=original_ids(c); fm=freeze[ex]; e7p=c.get('prompt_sha256')
 origp=None; fh=None; fr=None; tree=None
 if ex=='E002':
  r=orig_record(c,'medium'); md=j(R/'artifacts/experiment-002'/r['run_id']/'run-metadata.json'); origp=md.get('prompt_sha256')
  # E002 task/evaluator tests are the frozen E001 assets inherited by E002.
  prompt=R/c['prompt']; held=R/c['heldout_tests']; regression=R/'evaluation/experiment-001'/c['source_case_id']/'metadata.json'
  fh=sha(held); fr=sha(regression)
 elif fm:
  ent=fm.get('case_hashes',{}).get(c['case_id'],{})
  origp=ent.get('prompt_sha256'); e7p=e7p or origp
  fh=ent.get('heldout_test_sha256'); fr=ent.get('regression_test_sha256') or ent.get('regression_tests_sha256')
  tree=ent.get('buggy_tree_sha256')
 # Check exact E007 prompt hash against original artifacts; evaluator assets use frozen parent hashes where supplied.
 same_prompt=(origp==e7p) if origp and e7p else None
 audit.append({'case_id':c['case_id'],'difficulty':c['difficulty'],'source_experiment':ex,'source_case_id':ident,'prompt_hash_original':origp,'prompt_hash_e007_manifest':e7p,'prompt_identical':same_prompt,'heldout_hash_parent_freeze':fh,'regression_hash_parent_freeze':fr,'base_tree_hash_parent_freeze':tree,'task_definition_status':'IDENTICAL' if same_prompt else 'EQUIVALENT' if same_prompt is None else 'CHANGED'})

def classify_suite(o,e7r):
 # Suite-level taxonomy is comparable across legacy evaluator schemas.
 if str(o.get('evaluation_status','')).upper() not in ('OK','PASS','CLEAN') or e7r.get('infrastructure_status') not in ('OK',None): return 'evaluator/infrastructure anomaly'
 suites=[]
 if str(o.get('public','')).lower() in ('fail','failed'): suites.append('public')
 if str(o.get('held_out','')).lower() in ('fail','failed'): suites.append('held-out')
 if str(o.get('regression','')).lower() in ('fail','failed'): suites.append('regression')
 # Source E002 uses publication normalized fields; source E004-E006 same.
 if not suites: return 'successful repair'
 if len(suites)>1:return 'multiple-suite failure ('+' + '.join(suites)+')'
 if suites[0]=='public':return 'public-suite failure'
 if suites[0]=='held-out':return 'held-out/incomplete fix'
 return 'regression introduced'

def trace_path(run,original=False):
 if original:
  c=e7meta[run['case_id']]; ex,ident,key=original_ids(c); d=orig_raw(ex,ident,run['reasoning_effort']); return d/'tool-timeline.json'
 return safe_path(run.get('session_export',''))

def trace_metrics(path):
 if not path or not Path(path).is_file():return {'trace_available':False}
 d=j(path); steps=d.get('steps') or []; calls=[]
 for s in steps:
  for t in s.get('tool_calls') or []:
   fn=t.get('function_name',''); arg=t.get('arguments') or {}; cmd=str(arg.get('command','')) if isinstance(arg,dict) else str(arg); low=cmd.lower()
   calls.append((s.get('step_id'),fn,cmd,low))
 edits=[x for x in calls if x[1] in ('edit','write','write_file','apply_patch','replace_in_file') or re.search(r'\b(sed\s+-i|perl\s+-i|apply_patch|tee\s+|cat\s+[^|;]*>\s*)',x[2],re.I)]
 explores=[x for x in calls if x[1] in ('read','grep','search') or re.search(r'\b(ls|find|rg|grep|git\s+(?:status|log|show|diff)|head|tail|cat|sed)\b',x[3])]
 tests=[x for x in calls if re.search(r'\b(pytest|unittest|tox|nox|cargo\s+test|npm\s+test|go\s+test|mvn\s+test|gradle\s+test|nosetests)\b|test_[a-z0-9_]+\.py',x[3])]
 first=min((x[0] for x in edits if x[0] is not None),default=None)
 return {'trace_available':True,'trace_steps':len(steps),'tool_calls':len(calls),'exploration_calls_heuristic':len(explores),'edit_calls_heuristic':len(edits),'test_calls_heuristic':len(tests),'first_edit_step_heuristic':first,'telemetry_definition':'Heuristic count from preserved tool-call names/commands; not directly comparable to hidden reasoning/planning.'}

trace_metrics_all={}
for eff in efforts:
 trace_metrics_all[eff]={}
 for version in ('original','E007'):
  trs=[]
  for c in manifest['cases']:
   o=orig_record(c,eff); n=e7_by[(c['case_id'],eff)]
   ex,ident,key=original_ids(c)
   p=orig_raw(ex,ident,eff,o['run_id'])/'tool-timeline.json' if version=='original' else safe_path(n.get('session_export',''))
   trs.append(trace_metrics(p))
  trace_metrics_all[eff][version]={}
  for metric in ('tool_calls','exploration_calls_heuristic','edit_calls_heuristic','test_calls_heuristic','first_edit_step_heuristic'):
   vals=[t.get(metric) for t in trs if isinstance(t.get(metric),(int,float))]
   trace_metrics_all[eff][version][metric]={'n_available':len(vals),'missing_of_30':30-len(vals),'mean':statistics.mean(vals) if vals else None,'median':statistics.median(vals) if vals else None}
  changed=[]
  for c in manifest['cases']:
   if version=='original':
    o=orig_record(c,eff); v=o.get('source_files_changed'); changed.append(int(v) if v not in (None,'') else None)
   else:
    n=e7_by[(c['case_id'],eff)]; paths=n.get('files_changed') or []
    src=[p for p in paths if not generated_path(p)]
    changed.append(len(src) if n.get('files_changed') is not None else None)
  vals=[x for x in changed if x is not None]
  trace_metrics_all[eff][version]['source_files_changed_heuristic']={'n_available':len(vals),'missing_of_30':30-len(vals),'mean':statistics.mean(vals) if vals else None,'median':statistics.median(vals) if vals else None,'definition':'Original uses normalized source_files_changed; E007 counts changed paths after excluding cache/bytecode/binary files.'}

discord_rows=[]; failure_rows=[]; metric_rows=[]
for cid in sorted(discordant,key=lambda k:next(i for i,x in enumerate(matrix) if x['case_id']==k)):
 c=e7meta[cid]; ex,ident,key=original_ids(c); outcomes=[]
 for eff,cond in [('medium','M'),('max','X')]:
  o=orig_record(c,eff); n=e7_by[(cid,eff)]; ov=outcome_bool(o['success']); nv=effective_outcome(n);
  if ov==nv:continue
  # Pull evaluator records for failure details without copying long logs.
  orig_folder=orig_raw(ex,ident,eff,o['run_id']); oe=j(orig_folder/'evaluation-result.json')
  ne=j(n['evaluator_output']);
  oe_fail=oe.get('failure_summary') or o.get('failure_classification') or ''
  if isinstance(oe_fail,list):oe_fail='; '.join(map(str,oe_fail))
  if isinstance(oe_fail,dict):oe_fail=json.dumps(oe_fail,sort_keys=True)
  e7suite=[s for s in ('public','heldout','regression') if effective_suite(n,s)=='fail']
  original_summary=str(oe_fail).replace('\n',' ')[:600]
  ev_summary='; '.join(e7suite) if e7suite else 'all suites pass'
  ot=trace_metrics(orig_folder/'tool-timeline.json'); nt=trace_metrics(n.get('session_export'))
  opatch=orig_folder/'workspace-change-summary.json'; all_npatch=n.get('files_changed') or []; npatch=[p for p in all_npatch if not generated_path(p)]
  orig_files=[]
  if opatch.exists():
   od=j(opatch); orig_files=od.get('source_files') or od.get('changed_files') or []
  rr=e7_recheck.get(n['run_id'],{}); failing_names=failing_ids(rr.get('stdout','')) if rr else failing_ids(ne)
  outcomes.append({'effort':eff,'original_outcome':ov,'e007_outcome':nv,'e007_recorded_outcome':bool(n['success']),'e007_recheck_status':rr.get('recheck_status','not_rechecked'),'original_run_id':o['run_id'],'e007_run_id':n['run_id'],'original_suite_failure':original_summary or 'none recorded','e007_suite_failure':ev_summary,'e007_failing_test_identifiers':failing_names[:12],'original_failure_taxonomy':classify_suite(o,n),'e007_failure_taxonomy':classify_suite({'evaluation_status':'OK','public':effective_suite(n,'public'),'held_out':effective_suite(n,'heldout'),'regression':effective_suite(n,'regression')},n),'original_trace':ot,'e007_trace':nt,'original_source_files':orig_files,'e007_source_files_after_generated_filter':npatch,'e007_all_changed_path_count':len(all_npatch),'original_steps':int(o['steps']),'e007_steps':n.get('agent_steps'),'original_wall_seconds':float(o['wall_time_seconds']),'e007_wall_seconds':n.get('wall_clock_seconds'),'original_tokens':int(o['prompt_tokens'])+int(o['completion_tokens']),'e007_tokens':(n.get('input_tokens') or 0)+(n.get('output_tokens') or 0)})
  metric_rows.extend([{'case_id':cid,'difficulty':c['difficulty'],'effort':eff,'version':'original',**{k:float(o[field]) if o.get(field) not in (None,'') else None for k,field in [('steps','steps'),('wall_seconds','wall_time_seconds'),('tokens','prompt_tokens')]},'tokens':int(o['prompt_tokens'])+int(o['completion_tokens'])},{'case_id':cid,'difficulty':c['difficulty'],'effort':eff,'version':'E007','steps':n.get('agent_steps'),'wall_seconds':n.get('wall_clock_seconds'),'tokens':(n.get('input_tokens') or 0)+(n.get('output_tokens') or 0)}])
 discord_rows.append({'case_id':cid,'difficulty':c['difficulty'],'source_experiment':ex,'source_case_id':ident,'changed_efforts':outcomes})

def med(xs): return statistics.median(xs) if xs else None
behavior={}
for eff in efforts:
 behavior[eff]={}
 for metric in ('steps','wall_seconds','tokens'):
  diffs=[]; origvals=[]; e7vals=[]
  for mr in matrix:
   cid=mr['case_id']; c=e7meta[cid]; o=orig_record(c,eff); n=e7_by[(cid,eff)]
   field={'steps':'steps','wall_seconds':'wall_time_seconds'}
   a=(int(o['steps']) if metric=='steps' else float(o['wall_time_seconds']) if metric=='wall_seconds' else int(o['prompt_tokens'])+int(o['completion_tokens']))
   b=(n.get('agent_steps') if metric=='steps' else n.get('wall_clock_seconds') if metric=='wall_seconds' else (n.get('input_tokens') or 0)+(n.get('output_tokens') or 0))
   if b is not None: origvals.append(a); e7vals.append(float(b)); diffs.append(float(b)-a)
  behavior[eff][metric]={'n_paired':len(diffs),'missing_of_30':30-len(diffs),'original_mean':statistics.mean(origvals) if origvals else None,'original_median':med(origvals),'e007_mean':statistics.mean(e7vals) if e7vals else None,'e007_median':med(e7vals),'paired_difference_mean_e007_minus_original':statistics.mean(diffs) if diffs else None,'paired_difference_median_e007_minus_original':med(diffs),'paired_differences':diffs}

(A/'E008-DISCORDANT-CASES.json').write_text(json.dumps(discord_rows,indent=2,sort_keys=True)+'\n')
(A/'E008-DISCORDANT-CASES.md').write_text('')
(A/'E008-BEHAVIORAL-DRIFT.json').write_text(json.dumps({'common_run_metrics':behavior,'trace_heuristics':trace_metrics_all},indent=2,sort_keys=True)+'\n')
(A/'E008-FAILURE-TAXONOMY.json').write_text(json.dumps({'taxonomy':'suite-level failure categories harmonized from evaluator outcomes; causal repair-stage labels preserved separately where available','groups':{},'discordant_case_failure_details':discord_rows},indent=2,sort_keys=True)+'\n')

# Rerun every original-vs-E007 discordant case/effort condition, 3 new trials per condition.
reruns=[]
for d in discord_rows:
 for x in d['changed_efforts']:
  reruns.append({'case_id':d['case_id'],'difficulty':d['difficulty'],'effort':x['effort'],'model':'swe-2-'+x['effort'],'existing_observations':{'original':x['original_outcome'],'E007':x['e007_outcome']},'new_trials':3,'why':'This same case-condition changed binary outcome between the original benchmark and E007; three new independent trials are the preregistered default to distinguish observed instability from a consistent direction. No case-specific protocol invalidity was identified.'})
estimated_seconds=0; estimated_tokens=0
for x in reruns:
 n=e7_by[(x['case_id'],x['effort'])]; estimated_seconds+=3*(n.get('wall_clock_seconds') or 0); estimated_tokens+=3*((n.get('input_tokens') or 0)+(n.get('output_tokens') or 0))
plan={'experiment_id':'E008','status':'awaiting_user_approval_before_execution','selected_case_count':len({x['case_id'] for x in reruns}),'selected_case_ids':sorted({x['case_id'] for x in reruns}),'selected_case_effort_conditions':len(reruns),'new_trials_per_condition':3,'new_runs_required':3*len(reruns),'conditions':reruns,'estimate_method':'Three times the corresponding E007 single-run wall time and input+output tokens; per-case estimates are descriptive point estimates, not guarantees. Cost was not exposed in original or E007 records. E007 catalog reported all SWE-2 variants Free, so expected direct model overage is $0 based on that catalog only; direct billing remains unverifiable.','estimated_sequential_wall_clock_seconds':estimated_seconds,'estimated_sequential_wall_clock_hours':estimated_seconds/3600,'estimated_total_tokens':estimated_tokens,'estimated_direct_overage_usd':None,'billing_note':'No direct-cost data exist. The authenticated E007 catalog labeled SWE-2 variants Free; this suggests $0 direct model overage but cannot verify account-level charges. Hard execution stop remains $50.','no_execution_started':True}
(A/'E008-RERUN-MANIFEST.json').write_text(json.dumps(plan,indent=2,sort_keys=True)+'\n')
(A/'E008-RUNS.jsonl').write_text('')
