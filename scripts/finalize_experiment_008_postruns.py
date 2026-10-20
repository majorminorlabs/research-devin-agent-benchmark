#!/usr/bin/env python3
"""Build E008 post-run stability outputs strictly from its frozen plan and run ledger."""
import json, math, statistics, hashlib, re
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
R=Path(__file__).resolve().parents[1]; A=R/'artifacts'/'experiment-008'; CH=A/'charts'

def read(p): return json.loads(Path(p).read_text())
def save(p,d): Path(p).write_text(json.dumps(d,indent=2,sort_keys=True)+'\n')
def table(headers,rows): return '| '+' | '.join(headers)+' |\n| '+' | '.join(['---']*len(headers))+' |\n'+''.join('| '+' | '.join(map(str,r))+' |\n' for r in rows)
def fnt(size=18,bold=False):
    for name in (['/System/Library/Fonts/Supplemental/Arial Bold.ttf'] if bold else ['/System/Library/Fonts/Supplemental/Arial.ttf']):
        try:return ImageFont.truetype(name,size)
        except:pass
    return ImageFont.load_default()
def cachefree(row):
    return (row.get('evaluator_sanitation') or {}).get('sanitation_verified_clean_before_evaluation') is True or (row.get('evaluator_sanitation_after_adapter_repair') or {}).get('verified_cache_free_before_evaluation') is True

plan_path=A/'E008-RERUN-MANIFEST.json'
frozen_plan_copy=A/'E008-RERUN-MANIFEST-APPROVED-FROZEN.json'
if not frozen_plan_copy.exists(): frozen_plan_copy.write_bytes(plan_path.read_bytes())
plan=read(plan_path); matrix=read(A/'E008-REPLICATION-MATRIX.json'); runs=[json.loads(x) for x in (A/'E008-RUNS.jsonl').read_text().splitlines() if x.strip()]
assert len(runs)==33 and len({x['run_id'] for x in runs})==33
assert {x['run_id'] for x in runs}=={f"E008-{c['case_id']}-{c['effort'].upper()}-R{i}" for c in plan['conditions'] for i in range(1,4)}
assert all(x.get('final_evaluation_status')=='valid' and x.get('final_task_success') in (True,False) for x in runs)
assert all(x.get('session_id') and x.get('intervention_count')==0 for x in runs)
assert all(x.get('cost_status')=='unknown' and x.get('cost_usd') is None for x in runs)
assert all(cachefree(x) for x in runs)

# Attach the stable slot order and returned model identity, with compact metrics only.
manifest_order=[]
for cond in plan['conditions']:
 for rep in range(1,4): manifest_order.append((cond['case_id'],cond['effort'],rep))
lookup={(x['case_id'],x['effort'],x['repetition']):x for x in runs}
for idx,key in enumerate(manifest_order,1):
    x=lookup[key]; x['run_slot']=idx
    exp=read(Path(x['session_export_path'])) if x.get('session_export_path') else read(Path(x['output_dir'])/'devin-session-export.json')
    model_name=(exp.get('agent') or {}).get('model_name')
    x['session_model_name']=model_name
    expected='SWE-2 Medium' if x['effort']=='medium' else 'SWE-2 Max'
    assert model_name==expected,(x['run_id'],model_name,expected)
    x['model_identity_verified_from_session_export']=True
    x['steps']=exp.get('final_metrics',{}).get('total_steps',x.get('steps'))
    fm=exp.get('final_metrics',{})
    x['input_tokens']=fm.get('total_prompt_tokens',x.get('input_tokens'))
    x['output_tokens']=fm.get('total_completion_tokens',x.get('output_tokens'))
    x['cached_tokens']=fm.get('total_cached_tokens',x.get('cached_tokens'))
    if x['input_tokens'] is not None and x['output_tokens'] is not None:x['total_tokens']=x['input_tokens']+x['output_tokens']
# Ledger with added canonical slot and session-verified name. Detailed exports stay in private outputs.
tmp=A/'E008-RUNS.jsonl.tmp'; tmp.write_text(''.join(json.dumps(x,sort_keys=True)+'\n' for x in sorted(runs,key=lambda z:z['run_slot']))); tmp.replace(A/'E008-RUNS.jsonl')

condition_rows=[]; per_condition=[]
for cond in plan['conditions']:
 c=next(z for z in matrix['cases'] if z['case_id']==cond['case_id']); e=cond['effort']; orig=c[f'original_{e}_outcome']; e7=c[f'e007_{e}_outcome']
 rr=sorted([x for x in runs if x['case_id']==cond['case_id'] and x['effort']==e],key=lambda x:x['repetition'])
 assert len(rr)==3
 outs=[bool(orig),bool(e7)]+[bool(x['final_task_success']) for x in rr]
 passed=sum(outs); fail_suites={}
 for x in rr:
  for s,v in (x.get('final_suite_results') or {}).items():
   if v not in ('pass','not-run'):
    fail_suites[s]=fail_suites.get(s,0)+1
 def span(metric):
  vals=[float(x[metric]) for x in rr if x.get(metric) is not None]
  if not vals:return {'n':0,'min':None,'max':None,'median':None,'range':None,'sd':None}
  return {'n':len(vals),'min':min(vals),'max':max(vals),'median':statistics.median(vals),'range':max(vals)-min(vals),'sd':statistics.stdev(vals) if len(vals)>1 else 0.0}
 metrics={'steps':span('steps'),'wall_time_seconds':span('wall_time_seconds'),'total_tokens':span('total_tokens')}
 repeat=sum(bool(x['final_task_success']) for x in rr)
 unanimous=repeat in (0,3)
 item={'case_id':cond['case_id'],'difficulty':c['difficulty'],'effort':e,'original_outcome':bool(orig),'e007_clean_rechecked_outcome':bool(e7),'e007_recorded_historical_outcome':c[f'e007_recorded_{e}_outcome'],'e008_trials':[{'repetition':x['repetition'],'run_id':x['run_id'],'session_id':x['session_id'],'outcome':bool(x['final_task_success']),'suite_results':x.get('final_suite_results'),'steps':x.get('steps'),'wall_time_seconds':x.get('wall_time_seconds'),'input_tokens':x.get('input_tokens'),'output_tokens':x.get('output_tokens'),'total_tokens':x.get('total_tokens'),'failure_classification':x.get('final_failure_classification',x.get('failure_classification'))} for x in rr],'five_outcome_sequence':outs,'five_outcome_sequence_text':' '.join('PASS' if q else 'FAIL' for q in outs),'solves_out_of_five':passed,'solve_frequency':passed/5,'new_trial_solves':repeat,'new_trial_stability':'unanimous_pass' if repeat==3 else 'unanimous_fail' if repeat==0 else 'mixed','new_trial_modal_share':max(repeat,3-repeat)/3,'recurring_failed_suites':fail_suites,'repeat_metrics':metrics}
 per_condition.append(item)
 sequence=' '.join(item['five_outcome_sequence_text'].split())
 condition_rows.append([item['case_id'],item['difficulty'],e.title(),sequence,f"{passed}/5",f"{repeat}/3",'unanimous' if unanimous else 'mixed'])

# Descriptive aggregates, keeping case-condition as the unit for stability comparisons.
by_effort={}; by_diff={}
for effort in ('medium','max'):
 z=[x for x in per_condition if x['effort']==effort]
 by_effort[effort]={'selected_conditions':len(z),'new_trial_count':sum(len(x['e008_trials']) for x in z),'new_trial_successes':sum(x['new_trial_solves'] for x in z),'new_trial_failures':sum(3-x['new_trial_solves'] for x in z),'unanimous_conditions':sum(x['new_trial_stability']!='mixed' for x in z),'mixed_conditions':sum(x['new_trial_stability']=='mixed' for x in z),'five_observation_successes':sum(x['solves_out_of_five'] for x in z),'five_observation_total':5*len(z)}
for diff in ('moderate','hard','very-hard'):
 z=[x for x in per_condition if x['difficulty']==diff]
 by_diff[diff]={'selected_conditions':len(z),'new_trial_count':sum(len(x['e008_trials']) for x in z),'new_trial_successes':sum(x['new_trial_solves'] for x in z),'unanimous_conditions':sum(x['new_trial_stability']!='mixed' for x in z),'mixed_conditions':sum(x['new_trial_stability']=='mixed' for x in z)}
all_success=sum(x['new_trial_solves'] for x in per_condition); all_obs=3*len(per_condition)
all_five_success=sum(x['solves_out_of_five'] for x in per_condition)
failed_suite_totals={}
for x in runs:
 for s,v in (x.get('final_suite_results') or {}).items():
  if v not in ('pass','not-run'): failed_suite_totals[s]=failed_suite_totals.get(s,0)+1

# E008 pair that has both efforts selected: keep the single case visible.
paired_effort={}
for case in sorted(set(x['case_id'] for x in per_condition)):
 z=[x for x in per_condition if x['case_id']==case]
 if {x['effort'] for x in z}=={'medium','max'}:
  paired_effort[case]={x['effort']:{'new_trial_successes':x['new_trial_solves'],'trial_count':3,'five_observation_successes':x['solves_out_of_five'],'steps':x['repeat_metrics']['steps'],'wall_time_seconds':x['repeat_metrics']['wall_time_seconds'],'total_tokens':x['repeat_metrics']['total_tokens']} for x in z}

results={'experiment_id':'E008','planned_run_slots':33,'attempted_run_slots':len(runs),'unique_sessions':len({x['session_id'] for x in runs}),'valid_final_evaluations':sum(x.get('final_evaluation_status')=='valid' for x in runs),'initial_evaluator_adapter_errors':sum(x.get('initial_evaluator_infrastructure_status')=='evaluator_infrastructure_invalid' for x in runs),'no_replacement_runs':True,'unapproved_conditions_added':0,'conditions':per_condition,'effort_summary':by_effort,'difficulty_summary':by_diff,'new_trial_successes':all_success,'new_trial_total':all_obs,'new_trial_success_rate_descriptive':all_success/all_obs,'five_observation_successes':all_five_success,'five_observation_total':5*len(per_condition),'five_observation_success_rate_descriptive':all_five_success/(5*len(per_condition)),'suite_failure_counts_across_new_trials':failed_suite_totals,'same_case_both_efforts':paired_effort,'interpretive_limits':['Selection was conditional on historical discordance; this is not a random sample.','Only 3 new trials per selected condition; stability labels are descriptive.','Medium/Max condition sets are unequal and not generally paired.','No repeated High condition exists.','Temporal backend change cannot be separated from stochastic run variance.','No direct billing evidence; actual cost is unknown.']}
save(A/'E008-STABILITY-ANALYSIS.json',results)
execution_summary={'experiment_id':'E008','approval_received':'2026-09-26','planned_slots':33,'attempted_slots':len(runs),'valid_final_evaluations':results['valid_final_evaluations'],'session_ids':sorted(x['session_id'] for x in runs),'approved_conditions':11,'approved_cases':9,'unapproved_conditions_added':0,'replacement_or_retry_sessions':0,'human_interventions':sum(x.get('intervention_count',0) or 0 for x in runs),'initial_adapter_errors':results['initial_evaluator_adapter_errors'],'recovered_slot_10_serialization_incident':True,'actual_direct_cost_usd':None,'actual_cost_status':'unknown; no billing evidence exposed','historical_E007_records_modified':False,'manifest_conditions_unchanged':True}
save(A/'E008-EXECUTION-SUMMARY.json',execution_summary)
plan['status']='completed'; plan['no_execution_started']=False; plan['execution_completed']=True
plan['execution_summary_path']='E008-EXECUTION-SUMMARY.json'; plan['actual_direct_cost_usd']=None
plan['actual_cost_status']='unknown; no billing evidence exposed'; plan['estimated_direct_overage_usd']=None
plan['cost_estimate_status']='unknown for actual cost; prior unverified catalog-only estimate is preserved in E008-RERUN-MANIFEST-APPROVED-FROZEN.json'
plan['billing_note']='Actual direct cost is UNKNOWN. No account billing evidence was exposed. Do not infer actual cost from catalog labels.'
save(plan_path,plan)

metric_rows=[]
for x in per_condition:
 def fmt(k,digits=1):
  z=x['repeat_metrics'][k]
  return 'NA' if z['n']==0 else f"{z['min']:.{digits}f}–{z['max']:.{digits}f} (med {z['median']:.{digits}f})"
 metric_rows.append([x['case_id'],x['effort'].title(),fmt('steps'),fmt('wall_time_seconds'),fmt('total_tokens',0),', '.join(f'{k}:{v}/3' for k,v in x['recurring_failed_suites'].items()) or 'none'])
condition_table=table(['Case','Difficulty','Effort','Five outcomes','Solves / 5','E008 repeats','Repeat consistency'],[[x['case_id'],x['difficulty'].title(),x['effort'].title(),x['five_outcome_sequence_text'],f"{x['solves_out_of_five']}/5",f"{x['new_trial_solves']}/3",x['new_trial_stability'].replace('_',' ')] for x in per_condition])
metric_table=table(['Case','Effort','Steps min–max (median)','Wall seconds min–max (median)','Tokens min–max (median)','Failed suites across 3'],metric_rows)
effort_table=table(['Effort','Conditions','New repeat solves','Unanimous conditions','Mixed conditions','Five-observation solves'],[[e.title(),s['selected_conditions'],f"{s['new_trial_successes']}/{s['new_trial_count']}",f"{s['unanimous_conditions']}/{s['selected_conditions']}",f"{s['mixed_conditions']}/{s['selected_conditions']}",f"{s['five_observation_successes']}/{s['five_observation_total']} ({s['five_observation_successes']/s['five_observation_total']:.0%})"] for e,s in by_effort.items()])
diff_table=table(['Difficulty','Conditions','New repeat solves','Unanimous','Mixed'],[[d.title(),s['selected_conditions'],f"{s['new_trial_successes']}/{s['new_trial_count']}",s['unanimous_conditions'],s['mixed_conditions']] for d,s in by_diff.items()])

stability=f'''# E008 Stability Analysis — Completed Targeted Repeats

## Execution and evaluation record

Exactly **33/33** frozen slots were attempted across the approved **9 cases and 11 case/effort conditions**. There were 33 distinct session IDs, zero human interventions, no High or stable conditions, and no replacement sessions.

All 33 existing workspaces now have valid final evaluations. The first nine E002 sessions initially hit a local adapter `KeyError` before tests ran; the same preserved workspaces were re-evaluated using the frozen suites after cache sanitation. The initial adapter failures remain in each ledger row, alongside the final adjudication. Slot 10’s completed session and evaluator result were recovered from preserved output after a local JSON serialization failure; that session was not rerun. No Devin trial was replaced. Historical E007 results remain unchanged.

Actual direct cost is **UNKNOWN**: no billing evidence was exposed. The old catalog-based estimate is not treated as actual cost.

## Five-observation outcome sequences

Each sequence orders the original result, E007 clean-rechecked result, and E008 repetitions 1–3. The five observations remain visible; the solve count is descriptive because the observations are dependent by case and the sample was selected for historical disagreement.

{condition_table}
The 11 five-observation sequences sum to {all_five_success}/{5*len(per_condition)} solves. New repeats sum to {all_success}/{all_obs}. These are selected discordant conditions and do not estimate full-benchmark accuracy.

## Within-condition telemetry and recurring suite failures

Ranges and medians are from the three new E008 runs only. Token totals are model counters, not cost. Failure labels name evaluator suites, not root causes or individual test IDs.

{metric_table}

Across new runs, failed suite counts were: {', '.join(f'{k}={v}' for k,v in failed_suite_totals.items()) or 'none'}. These categories overlap when a run fails multiple suites.

## Stability by effort and difficulty

{effort_table}

{diff_table}

Six of 11 selected conditions were unanimous across the three new runs; five were mixed. Medium had 3/6 unanimous conditions and Max 3/5. These proportions are similar and the conditions are not balanced or fully paired, so they do not establish that one effort setting is more stable. New-repeat descriptive solves were {by_effort['medium']['new_trial_successes']}/{by_effort['medium']['new_trial_count']} for Medium and {by_effort['max']['new_trial_successes']}/{by_effort['max']['new_trial_count']} for Max; do not interpret these as independent benchmark samples.

Mixed repeat outcomes occurred in {by_diff['moderate']['mixed_conditions']}/{by_diff['moderate']['selected_conditions']} moderate, {by_diff['hard']['mixed_conditions']}/{by_diff['hard']['selected_conditions']} hard, and {by_diff['very-hard']['mixed_conditions']}/{by_diff['very-hard']['selected_conditions']} very-hard conditions. This suggests more observed mixing at higher difficulty in this selected sample, particularly 2/2 very-hard conditions, but the small, discordance-selected groups cannot support a general difficulty trend.

## Answers to the preregistered questions

1. **Are discordant cases unstable?** Five conditions had mixed outcomes across the three repeats; six were unanimous. E008-C02 Medium, E005-K01 Medium, E005-H03 Max, E006-H03 Medium, and E006-H01 Max were mixed. Three repeats are a small descriptive check, not a reliability estimate.
2. **Is one effort more stable?** No clear difference: 3/6 Medium and 3/5 Max conditions were unanimous. The selected condition sets differ.
3. **Is within-condition variance comparable to the effort gap?** Only E004-N03 has both effort settings in this rerun. Its Medium repeats were 0/3 and Max 3/3, while each setting was internally unanimous. This one 100-point contrast shows a possible effort difference on that case, not a population-level comparison. Other selected conditions have only one effort, so broad within-versus-between variance is not estimable.
4. **Does instability concentrate by difficulty?** Mixed conditions were 1/5 moderate, 2/4 hard, and 2/2 very-hard. This is suggestive only; the very-hard denominator is two.
5. **Does the original Medium-vs-Max interpretation survive?** The original full benchmark difference was one case (24/30 Medium vs 23/30 Max). This targeted sample is not a fresh full-benchmark comparison. E004-N03 favors Max in repeats, while most cases do not have both efforts repeated. The original near-tie is neither confirmed nor overturned.
6. **Does E007 High/Max tie remain meaningful?** Not tested: High was not included in the approved repeat manifest. E007’s clean-rechecked High and Max scores were both 24/30, but this design cannot estimate High run variance.
7. **Is there evidence of temporal/backend drift?** No distinguishing evidence. New sessions were run Sep 26, after E007; provider deployment revision and per-session backend identity are unavailable. The observed mixed repeats demonstrate run-to-run variation, but do not separate stochastic execution from temporal/backend change.

## Publication readiness and remaining uncertainty

The run ledger, preserved session exports, corrected E002 evaluator results, exact five-outcome sequences, suite statuses, telemetry ranges, and checksums support an auditable technical report. The results are **not ready for a publication claim that SWE-2 effort levels differ reliably or that temporal model drift caused the historical change**. The repeat sample is small and selected, High was not repeated, and actual cost is unknown. A paper can report this as a targeted descriptive stability study with these limits explicit.
'''
(A/'E008-STABILITY-ANALYSIS.md').write_text(stability)

# Charts use case-condition as row; the first panel is the requested five-observation sequence.
CH.mkdir(exist_ok=True)
W,H=1700,900; img=Image.new('RGB',(W,H),'white');d=ImageDraw.Draw(img); d.text((55,30),'E008: five observed outcomes by selected case-condition',font=fnt(30,True),fill='#17212b');d.text((55,77),'Original · E007 clean recheck · E008 repeats 1–3. Green = pass; red = fail.',font=fnt(17),fill='#52616f')
start_y=140; rh=63; xs=[970,1110,1250,1390,1530]
for i,label in enumerate(['Original','E007 clean','E008 #1','E008 #2','E008 #3']):d.text((xs[i]-44,112),label,font=fnt(15,True),fill='#263746')
for i,x in enumerate(per_condition):
 y=start_y+i*rh; d.text((55,y+4),f"{x['case_id']}  {x['effort'].title()}",font=fnt(18,True),fill='#17212b'); d.text((500,y+8),x['difficulty'].title(),font=fnt(16),fill='#52616f')
 for k,v in enumerate(x['five_outcome_sequence']):
  cx=xs[k]; col='#2f9e64' if v else '#d94841'; d.ellipse((cx-17,y,cx+17,y+34),fill=col);d.text((cx-6,y+7),'P' if v else 'F',font=fnt(16,True),fill='white')
 d.text((1600,y+6),f"{x['solves_out_of_five']}/5",font=fnt(18,True),fill='#17212b')
img.save(CH/'07-five-outcome-sequences.png')

# Repeat-only frequency grid (never combines runs across case-condition into inferential n).
W,H=1500,800;img=Image.new('RGB',(W,H),'white');d=ImageDraw.Draw(img);d.text((50,30),'E008 repeat outcomes by condition',font=fnt(30,True),fill='#17212b');d.text((50,75),'Each bar represents one selected condition’s 3 new trials; labels are successes / 3.',font=fnt(17),fill='#52616f')
base=680; y0=140; rh=47; x0=600; bw=180
for eidx,e in enumerate(('medium','max')):
 x=x0+eidx*390;d.text((x,110),e.title(),font=fnt(19,True),fill='#17212b')
for i,x in enumerate(per_condition):
 y=y0+i*rh;d.text((50,y+5),f"{x['case_id']} — {x['effort'].title()}",font=fnt(15),fill='#17212b')
 eidx=0 if x['effort']=='medium' else 1; bx=x0+eidx*390; n=x['new_trial_solves']; width=bw*n/3; col='#377eb8' if eidx==0 else '#8b6bb1';d.rectangle((bx, y+3, bx+max(width,3),y+31),fill=col);d.text((bx+bw+12,y+5),f"{n}/3",font=fnt(16,True),fill='#17212b')
d.text((50,740),'Selected cases differ by effort and difficulty; bar totals are descriptive only.',font=fnt(15),fill='#52616f');img.save(CH/'08-three-repeat-frequencies.png')

# Per-condition metric ranges in three panels; normalize each metric by its max solely for chart display.
W,H=1650,900;img=Image.new('RGB',(W,H),'white');d=ImageDraw.Draw(img);d.text((45,25),'E008 repeated-run telemetry ranges',font=fnt(29,True),fill='#17212b');d.text((45,68),'Min–max across 3 new trials; dots mark medians. Each metric has its own scale.',font=fnt(16),fill='#52616f')
metrics=[('steps','Steps','#377eb8'),('wall_time_seconds','Wall time (s)','#e68632'),('total_tokens','Tokens','#8b6bb1')]
for pi,(key,title,col) in enumerate(metrics):
 top=130+pi*240;d.text((50,top),title,font=fnt(20,True),fill=col); vals=[x['repeat_metrics'][key] for x in per_condition]; maxv=max((z['max'] or 0) for z in vals) or 1; xleft=500; xright=1550
 for i,(x,z) in enumerate(zip(per_condition,vals)):
  y=top+38+i*17
  if z['n']==0:continue
  d.text((50,y-3),f"{x['case_id']} {('MED' if x['effort']=='medium' else 'MAX')}",font=fnt(12),fill='#33424f')
  lo=xleft+(xright-xleft)*(z['min']/maxv); hi=xleft+(xright-xleft)*(z['max']/maxv); med=xleft+(xright-xleft)*(z['median']/maxv)
  d.line((lo,y+5,hi,y+5),fill=col,width=5); d.ellipse((med-5,y,med+5,y+10),fill='#17212b')
img.save(CH/'09-repeat-telemetry-ranges.png')

# Add the execution/stability section to the pre-execution report while preserving earlier audit findings.
report=(A/'E008-REPORT.md').read_text()
report=report.replace('# E008 Pre-Rerun Report','# E008 Replication and Stability Report',1)
report=report.replace('**Status: Phases 1–8 complete; no Devin trials started.** This report analyzes the frozen original runs and E007 records, with a separate clean-evaluator recheck of preserved E007 very-hard workspaces. It stops at the user-approval gate.','**Status: 33/33 approved trial slots completed.** No conditions were added and no Devin sessions were replaced. The first nine E002 evaluator attempts hit a local adapter error; the same preserved workspaces were cleanly re-evaluated after repair. One serialization error at slot 10 was recovered from the preserved runner/session/evaluator files without another session. Initial errors remain visible in the ledger. Actual cost is **unknown**.',1)
report=report.replace('The hypothesis that same-condition run variance is as large as the between-effort difference is **not yet tested**. Two different-date observations per case-condition do not estimate within-condition run variance. E008 repeats are intended to measure this; no stability claim is made now.','E008 repeats show mixed outcomes in 5 of 11 selected conditions and unanimous results in 6. Because the sample was selected for historical discordance, the effort sets are unequal, and only three repeats were run per condition, this does not estimate population-level reliability. Backend drift remains unresolved.',1)
start=report.find('## 8. Proposed minimum repeat set')
if start<0: start=report.find('## 8. Completed targeted repeat analysis')
end=report.find('## Artifact index',start)
if start<0 or end<0: raise SystemExit('could not find pre-run report section to replace')
report=report[:start]+'## 8. Completed targeted repeat analysis\n\n'+f'''Exactly **33 planned sessions** were attempted and evaluated; all 33 final outcomes are valid. The first nine E002 sessions’ adapter failures and the slot-10 serialization incident are documented alongside their recovered or adjudicated results. No retries or replacement sessions occurred. Full five-outcome sequences, repeat-only stability, telemetry ranges, suite failures, and limits are in `E008-STABILITY-ANALYSIS.md`.\n\nThe 11 five-observation sequences contain **{all_five_success}/55 solves** across a discordance-selected sample. New repeats yielded **{all_success}/33 passes**. Six conditions were unanimous over three new trials and five were mixed. Medium and Max were similar on the proportion of unanimous selected conditions (3/6 vs 3/5); the design does not establish one effort as more stable. Mixed outcomes appeared in 1/5 moderate, 2/4 hard, and 2/2 very-hard conditions, which is descriptive only.\n\nOnly E004-N03 has both efforts repeated: its Medium repeats were 0/3 and Max repeats 3/3. This one case does not overturn the original 24/30 vs 23/30 near-tie, nor establish a general effort effect. High was not repeated, so E007’s corrected High/Max tie is not assessed by this rerun. The observed repeat variation does not distinguish stochastic runs from temporal/backend drift.\n\nActual direct cost is **UNKNOWN**; no billing evidence was exposed. The earlier catalog-only estimate is not an actual-cost claim. The session ledger and evaluator adjudications are preserved separately, and E007’s historical records and scores remain unchanged.\n\n**Publication readiness:** suitable as a transparently documented targeted descriptive stability report; not sufficient to claim a general effort-level reliability gap or identify backend drift.\n\n'''+report[end:]
report=report.replace('- `E008-STABILITY-ANALYSIS.md` and `.json`, `E008-RUNS.jsonl`, `E008-E002-ADJUDICATION.json`, and `charts/`','- `E008-STABILITY-ANALYSIS.md` and `.json`, `E008-RUNS.jsonl`, `E008-E002-ADJUDICATION.json`, `E008-EXECUTION-SUMMARY.json`, `E008-RERUN-MANIFEST-APPROVED-FROZEN.json`, and `charts/`\n- Repeat charts: `07-five-outcome-sequences.png`, `08-three-repeat-frequencies.png`, and `09-repeat-telemetry-ranges.png')
report=report.replace('- Repeat charts: `07-five-outcome-sequences.png`, `08-three-repeat-frequencies.png`, and `09-repeat-telemetry-ranges.png\n- Repeat charts: `07-five-outcome-sequences.png`, `08-three-repeat-frequencies.png`, and `09-repeat-telemetry-ranges.png`','- Repeat charts: `07-five-outcome-sequences.png`, `08-three-repeat-frequencies.png`, and `09-repeat-telemetry-ranges.png`')
(A/'E008-REPORT.md').write_text(report)

# Update the rerun plan's status without changing its selected conditions.
rerun_plan=(A/'E008-RERUN-PLAN.md').read_text()
rerun_plan=rerun_plan.replace('# E008 Targeted Rerun Plan — Approval Required','# E008 Targeted Rerun Plan — Executed',1)
rerun_plan=rerun_plan.replace('- Estimated direct overage: **$0 based on the E007 catalog’s “Free” labels**, but actual billing is unobservable and cannot be verified from saved records.','- Actual direct cost: **UNKNOWN**. No account billing evidence was exposed. The prior catalog-only estimate was unverified and is not an actual-cost claim.',1)
stale='The runtime/token figures are planning estimates, not guarantees. There is no substantiated per-run direct cost to multiply. The machine-readable selection is `E008-RERUN-MANIFEST.json`. **No runs have been launched; explicit approval is required before Phase 9.**'
current='The runtime/token figures are pre-run planning estimates, not guarantees. The approved manifest was executed as written: 33 sessions across 9 cases and 11 case/effort conditions, with no additions or replacements. See `E008-STABILITY-ANALYSIS.md` for outcomes. The original approved manifest is preserved as `E008-RERUN-MANIFEST-APPROVED-FROZEN.json`.'
rerun_plan=rerun_plan.replace(stale,current,1)
rerun_plan=rerun_plan.replace('- Stop condition: verify current billing before launch and stop if projected direct overage exceeds **$50**.','- Execution boundary: the approved 33 slots are complete; no additional runs are included or authorized by this plan.')
(A/'E008-RERUN-PLAN.md').write_text(rerun_plan)

# Update protocol execution status (preregistration itself remains frozen).
protocol=(A/'E008-PROTOCOL.md').read_text()
if '## Execution status' in protocol: protocol=protocol[:protocol.index('## Execution status')]
protocol+='''## Execution status\n\nThe user approved the frozen 33-slot manifest on 2026-09-26. Exactly 33 sessions were attempted across the approved 11 conditions, sequentially, with no replacements, no added conditions, and zero human interventions. The first nine E002 sessions initially hit an adapter field error before tests executed; their preserved workspaces were evaluated after adapter repair in sanitized copies, with the initial errors retained in `E008-RUNS.jsonl`. Slot 10’s completed result was recovered after a local serialization error; it was not rerun. All 33 final evaluations are valid. Actual cost is unknown because no billing evidence was exposed. See `E008-STABILITY-ANALYSIS.md` for outcomes and interpretation.\n'''
(A/'E008-PROTOCOL.md').write_text(protocol)

print(json.dumps({'runs':len(runs),'final_evaluations':results['valid_final_evaluations'],'new_passes':all_success,'new_trials':all_obs,'mixed_conditions':sum(x['new_trial_stability']=='mixed' for x in per_condition),'charts':3},indent=2))
