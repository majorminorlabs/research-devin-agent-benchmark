#!/usr/bin/env python3
"""Render E008 pre-rerun documents/charts from analyze_experiment_008 outputs."""
import csv,json,statistics,shutil
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont
R=Path(__file__).resolve().parents[1]; A=R/'artifacts/experiment-008'; C=A/'charts'; C.mkdir(exist_ok=True)
def j(n):return json.loads((A/n).read_text())
def filehash(p):return __import__('hashlib').sha256(Path(p).read_bytes()).hexdigest()
def font(s=20,b=False):
 for p in ['/System/Library/Fonts/Supplemental/Arial Bold.ttf' if b else '/System/Library/Fonts/Supplemental/Arial.ttf','/System/Library/Fonts/SFNS.ttf']:
  try:return ImageFont.truetype(p,s)
  except:pass
 return ImageFont.load_default()
def table(headers,rows):return '| '+' | '.join(headers)+' |\n| '+' | '.join(['---']*len(headers))+' |\n'+''.join('| '+' | '.join(map(str,r))+' |\n' for r in rows)
matrix=j('E008-REPLICATION-MATRIX.json'); disc=j('E008-DISCORDANT-CASES.json'); behdoc=j('E008-BEHAVIORAL-DRIFT.json'); beh=behdoc['common_run_metrics']; tracebeh=behdoc['trace_heuristics']; tax=j('E008-FAILURE-TAXONOMY.json'); plan=j('E008-RERUN-MANIFEST.json')
manifest=json.loads((R/'artifacts/experiment-007/E007-MANIFEST.json').read_text())
e7={ (x['case_id'],x['reasoning_effort']):x for x in map(json.loads,(R/'artifacts/experiment-007/E007-RUNS.jsonl').read_text().splitlines()) }
recheck_source=R.parent/'devin-agent-benchmark-e008-private/evaluator-recheck/E008-E007-EVALUATOR-RECHECK.jsonl'
rechecks=[json.loads(x) for x in recheck_source.read_text().splitlines()]
recheck_by={x['run_id']:x for x in rechecks}
shutil.copyfile(recheck_source,A/'E008-E007-EVALUATOR-RECHECK.jsonl')
orows={(x['case_key'],x['condition']):x for x in csv.DictReader((R/'results/publication-v4-runs.csv').open())}
def taxonomy(suites, valid=True):
 if not valid:return 'evaluator/infrastructure anomaly'
 failed=[x for x in ('public','heldout','regression') if suites.get(x) in ('fail','failed')]
 if not failed:return 'successful repair'
 if len(failed)>1:return 'multiple-suite failure ('+' + '.join(failed)+')'
 return {'public':'public-suite failure','heldout':'held-out/incomplete fix','regression':'regression introduced'}[failed[0]]
def condition_key(c,eff):
 exp=c['original_experiment'].replace('experiment-','E'); ident=c['source_case_id'] if exp in ('E002','E006') else c['case_id']; return f'{exp}:{ident}',('M' if eff=='medium' else 'X')
taxgroups={}
for label,version,eff in [('original_medium','original','medium'),('E007_medium','E007','medium'),('original_max','original','max'),('E007_max','E007','max')]:
 count={}
 for c in manifest['cases']:
  if version=='original':
   r=orows[condition_key(c,eff)]; cat=taxonomy({'public':r['public'],'heldout':r['held_out'],'regression':r['regression']},r['evaluation_status']=='OK')
  else:
   r=e7[(c['case_id'],eff)]; rr=recheck_by.get(r['run_id'])
   if rr and rr.get('recheck_status')=='valid':
    ev=rr['evaluator_results']; pub=[v['status'] for k,v in ev.items() if k.startswith('public-')]
    cat=taxonomy({'public':'pass' if pub and all(x=='pass' for x in pub) else 'fail','heldout':ev['held-out']['status'],'regression':ev['regression']['status']},True)
   else:cat=taxonomy({'public':r.get('public_result'),'heldout':r.get('heldout_result'),'regression':r.get('regression_result')},r.get('infrastructure_status')=='OK')
  count[cat]=count.get(cat,0)+1
 taxgroups[label]=count
tax={'taxonomy':'Harmonized evaluator-suite failure classes, not causal diagnosis.','groups':taxgroups,'discordant_case_failure_details':disc}
(A/'E008-FAILURE-TAXONOMY.json').write_text(json.dumps(tax,indent=2,sort_keys=True)+'\n')

recheck_summary={}
all_e7=list(e7.values())
for eff in ('medium','high','max'):
 vals=[x for x in rechecks if x['effort']==eff]
 recorded=sum(x['success'] for x in all_e7 if x['reasoning_effort']==eff)
 corrected=sum((recheck_by[x['run_id']]['task_success'] if x['run_id'] in recheck_by and recheck_by[x['run_id']]['recheck_status']=='valid' else x['success']) for x in all_e7 if x['reasoning_effort']==eff)
 recheck_summary[eff]={'n':len(vals),'valid_evaluator_runs':sum(x['recheck_status']=='valid' for x in vals),'task_successes_after_clean_recheck':sum(x['task_success'] is True for x in vals),'task_failures_after_clean_recheck':sum(x['task_success'] is False for x in vals),'recorded_E007_total_successes':recorded,'corrected_E007_total_successes':corrected}
(A/'E008-E007-EVALUATOR-RECHECK.json').write_text(json.dumps(recheck_summary,indent=2,sort_keys=True)+'\n')
(A/'E008-E007-EVALUATOR-RECHECK.md').write_text('# E008 Re-evaluation of Existing E007 Very-Hard Workspaces\n\nE007’s saved E006 evaluator outputs for some Medium/High/Max workspaces report pytest collection errors: `import file mismatch` because pre-existing `.pyc` files embed the original host evaluator path while the frozen suite is mounted at `/control/evaluation`. This is an evaluator staging/cache error, not a task failure. We made a clean temporary copy of each frozen E006 evaluator directory, removed only generated `__pycache__`, `.pyc`, and pytest cache entries from that copy, and re-ran the frozen public, held-out, and regression commands against the preserved E007 workspaces using the same pinned E006 runtime. No Devin session was launched and E007’s original records were not modified.\n\n'+table(['E007 effort','Rechecked very-hard cases','Valid evaluator runs','Very-hard pass','Very-hard fail','Recorded E007 total','Clean-recheck E007 total'],[[e.title(),recheck_summary[e]['n'],recheck_summary[e]['valid_evaluator_runs'],recheck_summary[e]['task_successes_after_clean_recheck'],recheck_summary[e]['task_failures_after_clean_recheck'],f"{recheck_summary[e]['recorded_E007_total_successes']}/30",f"{recheck_summary[e]['corrected_E007_total_successes']}/30"] for e in ('medium','high','max')])+'\nThe 30 clean adjudications are preserved in `E008-E007-EVALUATOR-RECHECK.jsonl`. The historical E007 totals (16/30, 18/30, 18/30) remain its recorded scores. Clean-recheck totals (22/30, 24/30, 24/30) are an E008 sensitivity analysis, not a rewrite of E007. Six failed-to-pass E007 E006 cells changed for each effort; other outcomes were unchanged.\n')
plan['estimated_direct_overage_usd']=0
plan['cost_estimate_status']='catalog-based, unverified against account billing'
plan['billing_note']='Estimated $0 direct model overage based on E007 authenticated catalog labels (Free); direct billing and unrelated account-level charges are not observable. Verify before launch and stop if projected overage exceeds $50.'
(A/'E008-RERUN-MANIFEST.json').write_text(json.dumps(plan,indent=2,sort_keys=True)+'\n')

# Complete the failure taxonomy document and its cross-condition chart.
taxcats=sorted({c for d in tax['groups'].values() for c in d})
taxrows=[[g,*[tax['groups'][g].get(c,0) for c in taxcats]] for g in ('original_medium','E007_medium','original_max','E007_max')]
(A/'E008-FAILURE-TAXONOMY.md').write_text('# E008 Failure Taxonomy\n\nFailures are grouped by evaluator suite outcomes: public-suite failure, held-out/incomplete fix, regression introduced, multiple-suite failure, evaluator/infrastructure anomaly, or successful repair. These categories identify where the external contract failed, not the underlying agent reasoning. The source ledgers retain detailed labels when recorded; the legacy taxonomies are not sufficiently uniform for a more granular causal comparison.\n\n'+table(['Condition']+taxcats,taxrows)+'\nThe per-case and exact suite-class counts are in `E008-FAILURE-TAXONOMY.json`. A rise in public-suite failures or held-out failures is evidence about the failing contract, not proof of a model drift mechanism.\n')

# Discordant narrative with explicit evidence/interpretation/unknown sections.
lines=['# E008 Discordant Cases','',f"There are **{len(disc)} discordant cases** and {sum(len(x['changed_efforts']) for x in disc)} case-effort outcome changes. The trace counts below are heuristic classifications of preserved tool calls; they do not expose or infer hidden reasoning.",'']
for d in disc:
 lines += [f"## {d['case_id']} ({d['difficulty']})",'']
 for x in d['changed_efforts']:
  ot=x['original_trace']; nt=x['e007_trace']; old='solve' if x['original_outcome'] else 'fail'; new='solve' if x['e007_outcome'] else 'fail'
  lines += [f"### {x['effort'].title()}",'',f"**OBSERVATION:** The original run {x['original_run_id']} was a {old}; E007 run {x['e007_run_id']} was a {new}. Original evaluator note: {x['original_suite_failure'] or 'none preserved'}. E007 evaluator suites: {x['e007_suite_failure']}. E007 failing test identifiers, when printed: {', '.join(x['e007_failing_test_identifiers']) or 'not exposed in runner output'}. Steps: {x['original_steps']} vs {x['e007_steps']}; wall seconds: {x['original_wall_seconds']:.1f} vs {x['e007_wall_seconds'] if x['e007_wall_seconds'] is not None else 'unknown'}; input+output tokens: {x['original_tokens']} vs {x['e007_tokens']}. Source files changed: original {', '.join(x['original_source_files']) or 'not recorded'}, E007 {', '.join(x['e007_source_files_after_generated_filter']) or 'not recorded'} ({x['e007_all_changed_path_count']} total changed paths before generated-file filtering). Heuristic trace counts (exploration/edit/test calls): original {ot.get('exploration_calls_heuristic','NA')}/{ot.get('edit_calls_heuristic','NA')}/{ot.get('test_calls_heuristic','NA')}, E007 {nt.get('exploration_calls_heuristic','NA')}/{nt.get('edit_calls_heuristic','NA')}/{nt.get('test_calls_heuristic','NA')}. First edit steps: {ot.get('first_edit_step_heuristic','NA')} vs {nt.get('first_edit_step_heuristic','NA')}.",'',f"**INTERPRETATION:** The evaluator localizes the observable difference to {x['e007_suite_failure']}. The recorded patch/file list and final pass/fail establish the outcome, but the counts alone do not establish whether localization, diagnosis, implementation, or verification caused it.",'',"**UNRESOLVED:** These are only two observations for this condition. Ordinary stochastic run variance, temporal backend/model drift, and smaller execution-service differences remain unresolved. No causal explanation is assigned from the traces.",'']
(A/'E008-DISCORDANT-CASES.md').write_text('\n'.join(lines)+'\n')

# Comparability detail generated from E007 manifest hashes and parent frozen records.
audit=[]
for c in j(R/'artifacts/experiment-007/E007-MANIFEST.json')['cases']:
 exp=c['original_experiment'].replace('experiment-','E'); cid=c['case_id']; ident=c['source_case_id']; freeze_path=R/f"manifests/{c['original_experiment']}-freeze.json"
 parent_hash={}
 if freeze_path.exists():
  fm=json.loads(freeze_path.read_text()); parent_hash=fm.get('case_hashes',{}).get(cid,{})
 original_prompt=parent_hash.get('prompt_sha256')
 e7_prompt=c.get('prompt_sha256')
 if not e7_prompt and c.get('prompt'):
  pp=(R/c['prompt']).resolve(); e7_prompt=filehash(pp) if pp.is_file() else None
 if exp=='E002':
  key=f"E002:{ident}"; orig_run=next(x for x in csv.DictReader((R/'results/publication-v4-runs.csv').open()) if x['case_key']==key and x['condition']=='M')
  md=json.loads((R/'artifacts/experiment-002'/orig_run['run_id']/'run-metadata.json').read_text()); original_prompt=md.get('prompt_sha256')
 audit.append([cid,c['difficulty'],exp,'identical' if original_prompt and original_prompt==e7_prompt else 'unknown',parent_hash.get('buggy_tree_sha256') or c.get('source_commit','parent manifest'),parent_hash.get('heldout_test_sha256') or parent_hash.get('heldout_tests_sha256') or 'same referenced evaluator path',parent_hash.get('regression_test_sha256') or parent_hash.get('regression_tests_sha256') or 'same referenced evaluator path'])
(A/'E008-COMPARABILITY-AUDIT.md').write_text('# E008 Comparability Audit\n\n'+table(['Dimension','Classification','Evidence / limit'],[
 ['Canonical cases, IDs, difficulty','IDENTICAL','All 30 parent cases and 10 cases per tier are present in the E007 manifest.'],
 ['Source repository/base','IDENTICAL or EQUIVALENT','Parent manifests/freeze records preserve repository/commit or frozen tree hashes; E007 stages the same frozen source snapshots.'],
 ['Task prompt','IDENTICAL','Prompt SHA-256 reconciles for each case.'],
 ['Held-out and regression tests','IDENTICAL','E007 calls the parent evaluator assets; frozen hashes or unchanged referenced evaluator paths are recorded below.'],
 ['Scoring logic','EQUIVALENT','Primary TASK_SUCCESS still requires public, held-out, and regression suites to pass; evaluator implementation is parent-specific and reused.'],
 ['Model and effort','IDENTICAL','Exact original/E007 Medium and Max selectors and returned generation model IDs agree.'],
 ['Isolation/permissions','EQUIVALENT','Fresh Docker workspaces; Linux/arm64; dangerous/Bypass; read-only root; dropped capabilities; no control repo<HOME>/ socket; evaluator unavailable until session close.'],
 ['CLI/runtime','EQUIVALENT','CLI 3000.10.21 (611c1cba). E006 uses frozen e006 image; other parent tiers use e002 image with same case-specific setup.'],
 ['Execution date','CHANGED','Original sessions were on Sep 15–16, 2026; E007 ran Sep 25, 2026.'],
 ['Private backend deployment revision','UNKNOWN','Not exposed per session.'],
 ['E007 very-hard evaluator result','CHANGED / evaluator-invalid for affected cells','E007 pytest collection used host-path-cached bytecode. Clean-copy rechecks of preserved workspaces changed six outcomes per effort; see E008-E007-EVALUATOR-RECHECK.md. E007 records remain unmodified.'],
 ['E007 wrapper/setup incidents','CHANGED','One High-only wrapper record is incomplete; rejected pre-session catalog attempts and proxy recovery occurred before accepted runs. The wrapper gap is outside Medium/Max.'],
 ['Billing','UNKNOWN','No direct billing data. Catalog labels SWE-2 variants Free; account-level cost was not observable.']])+'\n## Case-by-case frozen identity checks\n\n'+table(['Case','Tier','Parent experiment','Prompt SHA-256','Base/tree evidence','Held-out evidence','Regression evidence'],audit)+'\n**Verdict:** Frozen task definitions and the scoring contract are comparable, but E007’s original E006 evaluator results are invalid for affected cells because of a test-collection artifact. E008 uses clean-copy re-evaluation of the preserved E007 workspaces as a separate corrected-outcome sensitivity analysis. The date changed and private backend revision is unknown, so attribution between stochastic variation and temporal service drift remains unresolved.\n')

# Behavioral drift report based on the three common complete metrics only.
br=[]
for e in ('medium','max'):
 for metric in ('steps','wall_seconds','tokens'):
  z=beh[e][metric]; unit='sec' if metric=='wall_seconds' else 'tokens' if metric=='tokens' else 'steps'
  br.append([e.title(),metric,z['n_paired'],z['missing_of_30'],f"{z['original_mean']:.1f}",f"{z['original_median']:.1f}",f"{z['e007_mean']:.1f}",f"{z['e007_median']:.1f}",f"{z['paired_difference_mean_e007_minus_original']:+.1f}",f"{z['paired_difference_median_e007_minus_original']:+.1f}"])
trace_rows=[]
for e in ('medium','max'):
 for m in ('tool_calls','exploration_calls_heuristic','edit_calls_heuristic','test_calls_heuristic','first_edit_step_heuristic','source_files_changed_heuristic'):
  a=tracebeh[e]['original'][m]; b=tracebeh[e]['E007'][m]
  trace_rows.append([e.title(),m,a['n_available'],b['n_available'],f"{a['median']:.1f}" if a['median'] is not None else 'NA',f"{b['median']:.1f}" if b['median'] is not None else 'NA',f"{a['mean']:.1f}" if a['mean'] is not None else 'NA',f"{b['mean']:.1f}" if b['mean'] is not None else 'NA'])
(A/'E008-BEHAVIORAL-DRIFT.md').write_text('# E008 Behavioral Drift\n\n## Common telemetry\n\nOnly steps, wall time, and input-plus-output tokens have complete, consistently recorded per-run values for all 30 original and E007 Medium/Max cells. Each row is case-paired; values are not independent samples.\n\n'+table(['Effort','Metric','N paired','Missing / 30','Original mean','Original median','E007 mean','E007 median','Mean paired Δ','Median paired Δ'],br)+'\nTokens are raw model token counters and not cost. The distributions are skewed, so mean differences are sensitive to a few long/high-token sessions; medians are shown alongside means. The complete 30 paired differences are in `E008-BEHAVIORAL-DRIFT.json`.\n\n## Limits of comparison\n\nOriginal session traces use multiple sanitized schemas; E007 stores raw session exports. Heuristic exploration/edit/test calls are reported only for discordant pairs in `E008-DISCORDANT-CASES.md`, not pooled as equivalent across all 60 conditions. Planning/reasoning step counts are **not comparable**: the source traces differ in what they preserve, and hidden reasoning is not coded. Files inspected and test invocations are also not consistently defined across all parent formats; files changed can be compared only descriptively from patch lists.\n\n## Observation\n\nE007 Medium used a similar median step count and slightly higher median tokens, while its median wall time was close to the original. E007 Max also had a similar median step count and wall time, but a higher median token count; large means reflect skew and case-specific extremes. These are behavioral differences between observed sessions, not proof of an undocumented model change.\n')
trace_table=table(['Effort','Trace metric','Original n','E007 n','Original median','E007 median','Original mean','E007 mean'],trace_rows)
(A/'E008-BEHAVIORAL-DRIFT.md').write_text('# E008 Behavioral Drift\n\n## Common run telemetry\n\nSteps, wall time, and input-plus-output tokens have complete, per-case values for all 30 original and E007 Medium/Max cells. Each row is case-paired; the distributions are right-skewed.\n\n'+table(['Effort','Metric','N paired','Missing / 30','Original mean','Original median','E007 mean','E007 median','Mean paired Δ','Median paired Δ'],br)+'\nTokens are raw model counters, not cost. Complete paired differences are in `E008-BEHAVIORAL-DRIFT.json`.\n\n## Trace-derived measures (heuristic)\n\n'+trace_table+'\nTool-call classes use the same name/command regex for both formats. First edit is the first detected edit/write call. Source-file changes use original normalized source counts and E007 changed paths after excluding cache/bytecode/binaries, so that row is descriptive rather than perfectly definition-identical. Counts of exact unique files inspected cannot be recovered uniformly; exploration calls are only a proxy. Hidden planning/reasoning steps are **not comparable or inferred**. Tests executed are command-level regex counts, not unique test cases passed. See case-level trace rows in `E008-DISCORDANT-CASES.md`.\n\n## Observation\n\nStep and wall-time medians are similar across experiment dates; token medians are higher in E007, especially for Max. Heuristic exploration, edit, test, and first-edit comparisons are descriptive and do not establish a private model change.\n')

# Protocol and preregistration.
(A/'E008-PROTOCOL.md').write_text('''# E008 Protocol\n\nE008 is a replication-drift and stability analysis of the frozen 30-case MAJOR//minor Devin SWE-2 benchmark. The primary analysis compares the historical SWE-2 Medium/Max runs with the E007 Medium/Max runs. The historical experiment and E007 records remain immutable.\n\n## Frozen analysis sequence\n\n1. Audit task, prompt, test, evaluator, score, model, runtime, permission, isolation, and date comparability.\n2. Recompute the case-level original-versus-E007 matrix from publication-v4 machine records and E007 run records.\n3. Report overall and difficulty-stratified exact agreement, outcome transitions, exact McNemar tests, and confidence intervals for agreement.\n4. Inspect original and E007 evidence for every discordant case.\n5. Harmonize failure types only to the level supported by evaluator evidence.\n6. Compare telemetry only for common complete fields; label trace-derived counts heuristic.\n7. Propose targeted repeat trials only for discordant case/effort cells.\n8. Stop pending explicit user approval.\n\n## Proposed repeat design\n\nFor each selected case/effort cell, add three independent runs, preserving the exact prompt, source snapshot, test suites, evaluator, selector, environment, isolation, and zero-intervention policy. Keep each observation separate. No stable case is selected. Before any run, verify live account/direct cost conditions and stop if projected new direct overage exceeds $50.\n\n## Execution status\n\nNo E008 agent run has been started. `E008-RUNS.jsonl` is empty. The proposed matrix and resource estimate are in `E008-RERUN-PLAN.md` and `E008-RERUN-MANIFEST.json`.\n''')
(A/'E008-PREREGISTRATION.md').write_text('''# E008 Preregistration\n\n## Question\n\nHow much of the outcome difference between the original SWE-2 benchmark and E007 reflects case-level instability, and what is the smallest targeted repeated-trial set that can characterize those disagreements?\n\n## Outcomes and analysis\n\nPrimary outcome is the frozen binary `TASK_SUCCESS`. The paired case-level matrix is primary for replication. Exact two-sided McNemar tests compare original and E007 outcomes; agreement proportions receive Wilson 95% intervals. Difficulty-stratified results are descriptive at n=10. Secondary telemetry is limited to fields with comparable definitions and adequate coverage. No hidden-reasoning claims or causal drift attribution will be made from observational traces.\n\n## Selection rule\n\nA case/effort setting is eligible only if its original and E007 outcome differs and the cell has valid evaluator output. Select all such Medium/Max cells; do not add stable cases or automatically run High. The frozen default is three new independent trials per selected cell. If any comparability blocker emerges, do not execute the affected cells until resolved.\n\n## Approval gate\n\nExecution is not authorized by this preregistration. Return the completed audit and exact proposed matrix for explicit user approval first. New direct overage must remain at or below $50.\n''')

# Rerun plan, pre-execution stability interpretation, and integrated report.
condrows=[]
for x in plan['conditions']:
 condrows.append([x['case_id'],x['difficulty'].title(),x['effort'].title(),'3',f"original {'solve' if x['existing_observations']['original'] else 'fail'}; E007 {'solve' if x['existing_observations']['E007'] else 'fail'}",x['why']])
(A/'E008-RERUN-PLAN.md').write_text(f'# E008 Targeted Rerun Plan — Approval Required\n\n## Selection\n\nThe analysis identifies **{len(plan["selected_case_ids"])} discordant cases**, with **{plan["selected_case_effort_conditions"]} case/effort conditions** whose original and validated E007 outcomes disagree. The preregistered design proposes three new trials for each changed condition: **{plan["new_runs_required"]} new runs** total. Stable conditions and all High conditions are excluded. Each row provides the reason; the affected E007 E006 outcomes were independently re-evaluated with the frozen tests before selection.\n\n'+table(['Case','Difficulty','Effort','New trials','Existing outcomes','Justification'],condrows)+'\n## Resource estimate\n\n- Estimated sequential wall time: **'+f"{plan['estimated_sequential_wall_clock_hours']:.2f}"+' hours**, using three times each selected E007 run’s observed runtime.\n- Estimated input+output tokens: **'+f"{plan['estimated_total_tokens']:,}"+'**, using three times the corresponding E007 run token totals.\n- Estimated direct overage: **$0 based on the E007 catalog’s “Free” labels**, but actual billing is unobservable and cannot be verified from saved records.\n- Stop condition: verify current billing before launch and stop if projected direct overage exceeds **$50**.\n\nThe runtime/token figures are planning estimates, not guarantees. There is no substantiated per-run direct cost to multiply. The machine-readable selection is `E008-RERUN-MANIFEST.json`. **No runs have been launched; explicit approval is required before Phase 9.**\n')
(A/'E008-STABILITY-ANALYSIS.md').write_text(f'# E008 Stability Analysis — Pre-Execution\n\nE008 has not executed repeats. This artifact records the analysis that motivates the proposed sample, not a stability result. The {plan["selected_case_effort_conditions"]} selected case/effort conditions each have two existing observations (original and validated E007); three proposed new trials would provide up to five observations per condition. After approval and execution, report every observation separately, then summarize solve frequency, failure frequency, steps, runtime, tokens, and within-condition variance. Mixed outcomes will be described as observed instability; 5/5 or 0/5 will be described as empirical observations, not reliability guarantees.\n\nNo repeated-trial outcome chart is generated before trials exist.\n')

# Publication-style charts; all derive from frozen machine-readable rows.
def chart(title,subtitle='',size=(1450,920)):
 im=Image.new('RGB',size,'white'); d=ImageDraw.Draw(im); d.text((60,35),title,font=font(32,True),fill='#202a35'); d.text((60,82),subtitle,font=font(16),fill='#687583'); return im,d
green='#66A87A'; red='#D47B78'; blue='#3572A5'; purple='#7C5AA6'; orange='#E19B32'; ink='#202a35'; grey='#DCE2E8'

# 1 Original vs E007 outcomes by case.
im,d=chart('Original vs E007 outcomes by case','Green = solved; red = failed. Columns: Original Medium, E007 Medium, Original Max, E007 Max.',(1420,950))
labels=['Original M','E007 M','Original Max','E007 Max']; x0=310; colw=260; y0=150; rh=24
for j,l in enumerate(labels):d.text((x0+j*colw,y0-28),l,font=font(17,True),fill=ink)
for i,r in enumerate(matrix['cases']):
 y=y0+i*rh; d.text((42,y+2),r['case_id']+'  '+r['difficulty'],font=font(14),fill=ink)
 vals=[r['original_medium_outcome'],r['e007_medium_outcome'],r['original_max_outcome'],r['e007_max_outcome']]
 for j,v in enumerate(vals):
  x=x0+j*colw; d.rectangle((x,y,x+150,y+17),fill=green if v else red); d.text((x+160,y), 'SOLVE' if v else 'FAIL',font=font(13),fill=ink)
im.save(C/'01-case-outcomes.png')

# 2 overall agreement by effort.
im,d=chart('Replication agreement by effort','Wilson 95% intervals shown as numeric labels; n=30 paired cases.',(1000,650)); base=520; top=160
for i,e in enumerate(('medium','max')):
 s=matrix['effort_summary'][e]; x=300+i*300; h=(base-top)*s['agreement_rate']; d.rectangle((x,base-h,x+130,base),fill=blue if e=='medium' else purple); d.text((x-5,base-h-38),f"{s['agreement']}/30 = {s['agreement_rate']:.1%}",font=font(18,True),fill=ink); d.text((x+20,base+20),e.title(),font=font(20),fill=ink)
d.line((180,base,870,base),fill=ink,width=2); im.save(C/'02-agreement-by-effort.png')

# 3 agreement by effort × difficulty.
im,d=chart('Replication agreement by difficulty','Agreement fraction among ten cases per tier.',(1300,700)); base=540; top=170; bw=48; gap=20; groupgap=130
for gi,t in enumerate(('moderate','hard','very-hard')):
 gx=210+gi*350; d.text((gx,base+30),t.title(),font=font(19,True),fill=ink)
 for ei,e in enumerate(('medium','max')):
  s=matrix['difficulty_summary'][t][e]; x=gx+ei*(bw+gap); h=(base-top)*s['agreement_rate']; d.rectangle((x,base-h,x+bw,base),fill=blue if e=='medium' else purple); d.text((x-7,base-h-28),f"{s['agreement_rate']:.0%}",font=font(15),fill=ink); d.text((x-3,base+5),e[0].upper(),font=font(15),fill=ink)
d.line((120,base,1190,base),fill=ink,width=2); im.save(C/'03-agreement-by-difficulty.png')

# 4 transition composition.
im,d=chart('Original-to-E007 outcome transitions','Stable solve, stable fail, and directional changes.',(1250,700)); cats=['stable_solves','stable_failures','original_only_solves','e007_only_solves']; colors=[green,'#AEB8C2',red,blue]; base=540; top=155
for idx,e in enumerate(('medium','max')):
 s=matrix['effort_summary'][e]; x=300+idx*450; y=base
 for cat,col in zip(cats,colors):
  h=(base-top)*s[cat]/30; d.rectangle((x,y-h,x+150,y),fill=col); d.text((x+164,y-h+max(0,h/2-8)),str(s[cat]),font=font(16,True),fill=ink); y-=h
 d.text((x+25,base+20),e.title(),font=font(20),fill=ink)
for i,(cat,col) in enumerate(zip(cats,colors)): d.rectangle((90+i*270,630,110+i*270,650),fill=col); d.text((118+i*270,627),cat.replace('_',' ').title(),font=font(14),fill=ink)
im.save(C/'04-outcome-transitions.png')

# 5 failure taxonomy distribution as category bars per group.
im,d=chart('Evaluator-suite failure taxonomy','Counts per 30 runs; categories are suite outcomes, not causal labels.',(1500,820)); cats=taxcats; xbase=290; ybase=185; group_h=140; scale=21
for gi,g in enumerate(('original_medium','E007_medium','original_max','E007_max')):
 y=ybase+gi*group_h; d.text((45,y+10),g.replace('_',' ').title(),font=font(17,True),fill=ink); x=xbase
 for cat in cats:
  value=tax['groups'][g].get(cat,0); w=value*scale
  if w:d.rectangle((x,y,x+w,y+45),fill=[blue,purple,orange,red,'#8794A2',green][cats.index(cat)%6]); d.text((x+3,y+12),str(value),font=font(14,True),fill='white')
  x+=w
 d.text((xbase,y+55),'  '.join(f"{k}: {v}" for k,v in tax['groups'][g].items()),font=font(12),fill=ink)
d.text((xbase,770),'Exact category counts appear in E008-FAILURE-TAXONOMY.json.',font=font(15),fill='#687583'); im.save(C/'05-failure-taxonomy.png')

# 6 common paired telemetry, median original/E007 by metric.
im,d=chart('Behavioral telemetry: original vs E007 medians','All 30 paired runs available for steps, wall time, and input+output tokens.',(1350,760)); metrics=['steps','wall_seconds','tokens']; x0=250; y0=180; rowh=170
for i,m in enumerate(metrics):
 y=y0+i*rowh; d.text((55,y+35),m.replace('_',' ').title(),font=font(20,True),fill=ink)
 for ei,e in enumerate(('medium','max')):
  z=beh[e][m]; x=x0+ei*520; vals=[z['original_median'],z['e007_median']]; vmax=max(vals) or 1; w1=vals[0]/vmax*340; w2=vals[1]/vmax*340
  d.text((x,y),e.title(),font=font(16,True),fill=ink); d.rectangle((x,y+30,x+w1,y+63),fill=blue); d.text((x+w1+5,y+34),f"orig {vals[0]:.1f}",font=font(14),fill=ink); d.rectangle((x,y+78,x+w2,y+111),fill=purple); d.text((x+w2+5,y+82),f"E007 {vals[1]:.1f}",font=font(14),fill=ink)
im.save(C/'06-behavioral-telemetry.png')

# Decision-ready, pre-rerun report.
effrows=[]
for e in ('medium','max'):
 s=matrix['effort_summary'][e]; lo,hi=s['agreement_wilson_95_ci']
 effrows.append([e.title(),f"{s['original_solve']}/30",f"{s['e007_solve']}/30",s['stable_solves'],s['stable_failures'],s['original_only_solves'],s['e007_only_solves'],f"{s['agreement']}/30 ({s['agreement_rate']:.1%}; 95% CI {lo:.1%}–{hi:.1%})",f"{s['mcnemar_exact_two_sided_p']:.4f}"])
tierrows=[]
for t in ('moderate','hard','very-hard'):
 for e in ('medium','max'):
  s=matrix['difficulty_summary'][t][e]
  tierrows.append([t.title(),e.title(),f"{s['original_solve']}/10",f"{s['e007_solve']}/10",f"{s['absolute_change_e007_minus_original']:+.0%}",s['stable_solves'],s['stable_failures'],s['original_only_solves'],s['e007_only_solves'],f"{s['agreement']}/10"])
behrows=[]
for e in ('medium','max'):
 for m in ('steps','wall_seconds','tokens'):
  z=beh[e][m]; behrows.append([e.title(),m,z['n_paired'],f"{z['original_median']:.1f}",f"{z['e007_median']:.1f}",f"{z['paired_difference_median_e007_minus_original']:+.1f}",f"{z['original_mean']:.1f}",f"{z['e007_mean']:.1f}",f"{z['paired_difference_mean_e007_minus_original']:+.1f}"])
condition_summary=table(['Effort','Original','E007 clean-recheck','Stable solve','Stable fail','Original only','E007 only','Agreement','Exact McNemar p'],effrows)
recheck_rows=[[e.title(),recheck_summary[e]['recorded_E007_total_successes'],recheck_summary[e]['corrected_E007_total_successes'],recheck_summary[e]['task_successes_after_clean_recheck'],recheck_summary[e]['task_failures_after_clean_recheck']] for e in ('medium','high','max')]
discord_ids=', '.join(x['case_id'] for x in disc) or 'none'
discord_eff='; '.join(x['case_id']+': '+', '.join(y['effort'].title() for y in x['changed_efforts']) for x in disc)
rerun_lines=[[x['case_id'],x['effort'].title(),x['existing_observations']['original'],x['existing_observations']['E007'],'3'] for x in plan['conditions']]
report=f'''# E008 Pre-Rerun Report

**Status: Phases 1–8 complete; no Devin trials started.** This report analyzes the frozen original runs and E007 records, with a separate clean-evaluator recheck of preserved E007 very-hard workspaces. It stops at the user-approval gate.

## 1. Comparability verdict

The 30 case identities, prompts, source snapshots, held-out/regression assets, task score contract, SWE-2 Medium/Max selectors, CLI version, permissions, and isolation are identical or equivalent in frozen records. Execution dates differ (Sep 15–16 versus Sep 25, 2026); private backend deployment revision is unknown.

**A material E007 evaluator staging defect was found in the very-hard tier.** Some original E007 held-out/regression results were pytest collection errors caused by stale `.pyc` files embedding the source evaluator’s host path. We copied the frozen evaluator directories, removed only generated cache files in the copies, and re-evaluated all 30 existing E007 very-hard workspaces using the same pinned runtime and tests. No agent sessions were run and E007’s records were not changed. See `E008-E007-EVALUATOR-RECHECK.md` and its machine-readable outputs.

| Effort | E007 recorded score | E007 after clean evaluator recheck |
|---|---:|---:|
| Medium | 16/30 | {recheck_summary['medium']['corrected_E007_total_successes']}/30 |
| High | 18/30 | {recheck_summary['high']['corrected_E007_total_successes']}/30 |
| Max | 18/30 | {recheck_summary['max']['corrected_E007_total_successes']}/30 |

Each effort had six very-hard runs change from recorded failure to pass after the clean recheck; other very-hard outcomes remained failures. Therefore the recorded E007 16/18/18 triplet materially reflects evaluator cache failures in addition to agent outcomes. Clean-recheck values are E008 sensitivity results, not replacements for the historical E007 record.

## 2. Replication agreement after the clean recheck

{condition_summary}

Intervals are Wilson 95% intervals for case-level agreement. Exact two-sided McNemar p-values use discordant pairs. These are unadjusted paired comparisons, and the 30 cases are a fixed benchmark rather than a random sample of all coding tasks.

The original benchmark reconciles to Medium 24/30 and Max 23/30. E007’s recorded scores reconcile to 16/30 Medium, 18/30 High, and 18/30 Max. After the clean E007 evaluator recheck, the Medium/High/Max totals are 22/30, 24/30, and 24/30.

## 3. Drift by difficulty

{table(['Difficulty','Effort','Original','E007 clean recheck','Absolute change','Stable solves','Stable failures','Original only','E007 only','Agreement'],tierrows)}

Each tier has n=10. The Medium decline is concentrated in moderate cases (10→7); its hard tier is unchanged and very-hard rises 7→8 after recheck. Max is unchanged in moderate, rises 6→8 in hard, and declines 9→8 in very-hard. The sample is too small to infer a difficulty trend.

## 4. Discordant cases

There are **{len(disc)} cases** and **{sum(len(x['changed_efforts']) for x in disc)} case-effort disagreements** after recheck: {discord_ids}.

Changed effort settings: {discord_eff}.

The original-only versus E007-only counts show disagreement runs in both directions. Per-case evaluator statuses, patch files, steps, runtime, tokens, and heuristic trace counts are in `E008-DISCORDANT-CASES.md`. That file separates observation, interpretation, and unresolved cause for every changed cell.

## 5. Failure-mode differences

{table(['Condition','Successful','Public failure','Held-out only','Regression only','Multiple suites'],[[g.replace('_',' ').title(),tax['groups'][g].get('successful repair',0),tax['groups'][g].get('public-suite failure',0),tax['groups'][g].get('held-out/incomplete fix',0),tax['groups'][g].get('regression introduced',0),sum(v for k,v in tax['groups'][g].items() if k.startswith('multiple-suite'))] for g in ('original_medium','E007_medium','original_max','E007_max')])}

Most failed cells are held-out misses; no specific diagnosis-stage category is consistently available across parent experiments. The initial E007 score drop was substantially inflated by evaluator staging errors in the very-hard tier. After recheck, remaining failures are valid evaluator results but do not by themselves establish changed model behavior.

## 6. Behavioral differences

{table(['Effort','Metric','Paired n','Original median','E007 median','Median Δ','Original mean','E007 mean','Mean Δ'],behrows)}

Heuristic trace-derived telemetry across all cases:

{table(['Effort','Trace metric','Original n','E007 n','Original median','E007 median','Original mean','E007 mean'],trace_rows)}

The medians show similar step counts and wall times; token medians are higher in E007, especially for Max. Means are skewed by a few unusually large sessions. All three metrics have 30 paired observations and no missing values. Trace metrics use a common heuristic parser, with available n and missingness shown; exact files inspected and private planning/reasoning cannot be compared. These observations do not identify a private model change.

## 7. What explains the difference?

The strongest concrete explanation is **evaluator/tooling error**, not a model capability change: six recorded E007 failures in each effort’s very-hard tier pass when the same existing workspaces are evaluated with clean copies of the frozen tests. With that correction, original-to-E007 solve-count changes shrink from the recorded differences to Medium −2 cases and Max +1 case, and the sign of the aggregate Medium-versus-Max comparison changes across experiments.

Among the corrected outcomes, ordinary stochastic variance remains plausible because single runs disagree on {sum(len(x['changed_efforts']) for x in disc)} cells. Systematic temporal model/backend drift remains possible because the dates differ and no deployment revision is exposed. The records cannot distinguish the two.

The hypothesis that same-condition run variance is as large as the between-effort difference is **not yet tested**. Two different-date observations per case-condition do not estimate within-condition run variance. E008 repeats are intended to measure this; no stability claim is made now.

## 8. Proposed minimum repeat set — approval required

Proposed **{len(plan['selected_case_ids'])} cases × {plan['selected_case_effort_conditions']} case/effort conditions × 3 trials = {plan['new_runs_required']} new runs**. Only the effort setting whose original and validated E007 outcomes disagree is selected for each condition; no High runs or stable cases are included.

{table(['Case','Effort','Original','E007 clean recheck','New trials'],rerun_lines)}

Estimated usage is **{plan['estimated_sequential_wall_clock_hours']:.2f} sequential hours** and **{plan['estimated_total_tokens']:,} input+output tokens**, extrapolating three times the matching E007 run’s observed usage. Estimated direct model overage is **$0 based on the SWE-2 catalog’s Free label**, but saved records contain no billing evidence, so this is unverified. Before execution, current billing must be checked; stop if projected direct overage exceeds **$50**.

The repeats would provide up to five individual observations per selected case-condition. Since the existing pair is already discordant, possible final frequencies are 1/5 through 4/5. This can show whether additional sessions cluster toward one result or remain mixed, while preserving each observation. It will not by itself distinguish all model-service drift from ordinary randomness.

**STOP:** No paid E008 sessions have been launched. Start Phase 9 only after explicit user approval of the proposed 33-run plan.

## Artifact index

- `E008-COMPARABILITY-AUDIT.md`
- `E008-REPLICATION-MATRIX.csv` and `.json`
- `E008-DISCORDANT-CASES.md`
- `E008-FAILURE-TAXONOMY.md`
- `E008-BEHAVIORAL-DRIFT.md`
- `E008-RERUN-PLAN.md` and `E008-RERUN-MANIFEST.json`
- `E008-E007-EVALUATOR-RECHECK.md` and machine-readable evaluator results
- `E008-STABILITY-ANALYSIS.md`, `E008-RUNS.jsonl`, and `charts/`
'''
(A/'E008-REPORT.md').write_text(report)
