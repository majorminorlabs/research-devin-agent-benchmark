#!/usr/bin/env python3
"""Recompute E007 analyses and publication charts from frozen run records."""
from __future__ import annotations
import json, math, random, re, statistics
from collections import Counter, defaultdict
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

REPO=Path(__file__).resolve().parents[1]; A=REPO/'artifacts'/'experiment-007'; PRIV=REPO.parent/'devin-agent-benchmark-e007-private'; CH=A/'charts'
EFFORTS=['medium','high','max']; TIERS=['moderate','hard','very-hard']; COLORS={'medium':'#3572A5','high':'#E19B32','max':'#7C5AA6'}; BG='#FFFFFF'; INK='#202A35'; MUTED='#687583'; GRID='#DCE2E8'
def readj(p): return json.loads(p.read_text())
def pct(x,n): return x/n if n else None
def fmt(x,d=3): return 'NA' if x is None else f'{x:.{d}f}'
def cp_interval(k,n,alpha=.05):
    if n==0:return [None,None]
    # Clopper-Pearson via inverse regularized incomplete beta.
    def betacf(a,b,x):
        qab=a+b; qap=a+1; qam=a-1; c=1.; d=1-qab*x/qap
        if abs(d)<1e-300:d=1e-300
        d=1/d; h=d
        for m in range(1,301):
            m2=2*m; aa=m*(b-m)*x/((qam+m2)*(a+m2)); d=1+aa*d
            if abs(d)<1e-300:d=1e-300
            c=1+aa/c
            if abs(c)<1e-300:c=1e-300
            d=1/d; h*=d*c; aa=-(a+m)*(qab+m)*x/((a+m2)*(qap+m2)); d=1+aa*d
            if abs(d)<1e-300:d=1e-300
            c=1+aa/c
            if abs(c)<1e-300:c=1e-300
            d=1/d; delta=d*c; h*=delta
            if abs(delta-1)<3e-14:break
        return h
    def ibeta(a,b,x):
        if x<=0:return 0.
        if x>=1:return 1.
        bt=math.exp(math.lgamma(a+b)-math.lgamma(a)-math.lgamma(b)+a*math.log(x)+b*math.log1p(-x))
        if x<(a+1)/(a+b+2):return bt*betacf(a,b,x)/a
        return 1-bt*betacf(b,a,1-x)/b
    def invbeta(p,a,b):
        lo,hi=0.,1.
        for _ in range(90):
            mid=(lo+hi)/2
            if ibeta(a,b,mid)<p:lo=mid
            else:hi=mid
        return (lo+hi)/2
    lo=0. if k==0 else invbeta(alpha/2,k,n-k+1)
    hi=1. if k==n else invbeta(1-alpha/2,k+1,n-k)
    return [lo,hi]
def binom_cdf(k,n):
    return sum(math.comb(n,i) for i in range(max(0,k)+1))* (0) if False else sum(math.comb(n,i) for i in range(max(0,k)+1))
def exact_binom_two_sided(k,n):
    if n==0:return 1.
    small=min(k,n-k); tail=sum(math.comb(n,i) for i in range(small+1))/(2**n)
    return min(1.,2*tail)
def pair_boot_ci(a,b,reps=20000,seed=7007):
    dif=[int(x)-int(y) for x,y in zip(a,b)]; n=len(dif)
    if not n:return [None,None]
    rng=random.Random(seed+n+sum((i+1)*v for i,v in enumerate(dif))); vals=[]
    for _ in range(reps): vals.append(sum(dif[rng.randrange(n)] for __ in range(n))/n)
    vals.sort(); return [vals[int(.025*reps)],vals[min(reps-1,int(.975*reps))]]
def paired(a,b):
    both=sum(x and y for x,y in zip(a,b)); aonly=sum(x and not y for x,y in zip(a,b)); bonly=sum((not x) and y for x,y in zip(a,b)); bothfail=len(a)-both-aonly-bonly
    return {'both_solve':both,'first_only':aonly,'second_only':bonly,'both_fail':bothfail,'first_effort':sum(a),'second_effort':sum(b),'n':len(a),'rate_difference_first_minus_second':(sum(a)-sum(b))/len(a) if a else None,'paired_bootstrap_95_ci':pair_boot_ci(a,b),'mcnemar_exact_two_sided_p':exact_binom_two_sided(aonly,aonly+bonly)}
def cochran_q(vectors):
    n=len(vectors[0]); k=len(vectors); col=[sum(x) for x in vectors]; row=[sum(v[i] for v in vectors) for i in range(n)]; den=k*sum(row)-sum(x*x for x in row)
    q=(k-1)*(k*sum(x*x for x in col)-sum(col)**2)/den if den else None
    # Asymptotic chi-square survival, df=k-1 (for three conditions df=2).
    p=math.exp(-q/2) if q is not None and k==3 else None
    return {'Q':q,'df':k-1,'asymptotic_p':p}
def summarize(xs):
    vals=[x for x in xs if isinstance(x,(int,float)) and not isinstance(x,bool)]
    return {'n_available':len(vals),'mean':statistics.mean(vals) if vals else None,'median':statistics.median(vals) if vals else None,'sum':sum(vals) if vals else None}
def norm_result(v):
    if isinstance(v,bool):return v
    if isinstance(v,str):return v.lower() in ('pass','passed','success','true')
    return bool(v)

m=readj(A/'E007-MANIFEST.json'); rows=[json.loads(x) for x in (A/'E007-RUNS.jsonl').read_text().splitlines()]; assert len(rows)==90
assert all(x['run_status']=='complete' for x in rows), 'all cells must have evaluator outputs'
cases={c['case_id']:c for c in m['cases']}; by=defaultdict(dict)
for r in rows: by[r['case_id']][r['reasoning_effort']]=r
assert len(by)==30 and all(set(v)==set(EFFORTS) for v in by.values())
okval=lambda x: bool(x['success'])
scores={e:{'successes':sum(okval(v[e]) for v in by.values()),'n':30,'rate':sum(okval(v[e]) for v in by.values())/30,'exact_95_ci':cp_interval(sum(okval(v[e]) for v in by.values()),30)} for e in EFFORTS}
tier_scores={d:{e:{'successes':sum(okval(v[e]) for k,v in by.items() if cases[k]['difficulty']==d),'n':10,'rate':sum(okval(v[e]) for k,v in by.items() if cases[k]['difficulty']==d)/10,'exact_95_ci':cp_interval(sum(okval(v[e]) for k,v in by.items() if cases[k]['difficulty']==d),10)} for e in EFFORTS} for d in TIERS}
pairs={}; pairvectors={}
for a,b in [('medium','high'),('medium','max'),('high','max')]:
 key=f'{a}_vs_{b}'; av=[okval(by[k][a]) for k in by]; bv=[okval(by[k][b]) for k in by]; pairs[key]=paired(av,bv); pairvectors[key]=(av,bv)
 for d in TIERS:
  ks=[k for k in by if cases[k]['difficulty']==d]; pairs[key][d]=paired([okval(by[k][a]) for k in ks],[okval(by[k][b]) for k in ks])
orig={}
for e,field in [('medium','original_medium_success'),('max','original_max_success')]:
 o=[bool(cases[k][field]) for k in by]; z=[okval(by[k][e]) for k in by]; both=sum(x and y for x,y in zip(o,z)); oo=sum(x and not y for x,y in zip(o,z)); no=sum((not x) and y for x,y in zip(o,z)); agree=sum(x==y for x,y in zip(o,z))
 orig[e]={'original_successes':sum(o),'e007_successes':sum(z),'n':30,'both_solve':both,'both_fail':30-both-oo-no,'original_only_solves':oo,'e007_only_solves':no,'exact_case_agreement':agree,'exact_case_agreement_rate':agree/30,'overall_rate_difference_e007_minus_original':(sum(z)-sum(o))/30,'case_results':{k:{'original':o[i],'e007':z[i],'match':o[i]==z[i]} for i,k in enumerate(by)}}
coch=cochran_q([[okval(by[k][e]) for k in by] for e in EFFORTS])
coch_by_tier={d:cochran_q([[okval(by[k][e]) for k in by if cases[k]['difficulty']==d] for e in EFFORTS]) for d in TIERS}
unique={e:[k for k in by if okval(by[k][e]) and sum(okval(by[k][x]) for x in EFFORTS)==1] for e in EFFORTS}
higher={}
for a,b in [('medium','high'),('high','max'),('medium','max')]:
 higher[f'{a}_to_{b}']={'failure_to_success':[k for k in by if not okval(by[k][a]) and okval(by[k][b])],'success_to_failure':[k for k in by if okval(by[k][a]) and not okval(by[k][b])]}

# Trace telemetry is extracted without changing agents; command classification is deliberately heuristic.
def trace_for(r):
 p=Path(r['session_export']) if r.get('session_export') else None
 if not p or not p.exists():return {'telemetry_status':'missing_session_export'}
 d=readj(p); steps=d.get('steps') or []; events=[]; toolhist=Counter();
 for s in steps:
  sid=s.get('step_id');
  for t in s.get('tool_calls') or []:
   fn=t.get('function_name',''); arg=t.get('arguments') or {}; cmd=str(arg.get('command','')) if isinstance(arg,dict) else str(arg); low=cmd.lower(); toolhist[fn]+=1
   edit=(fn in ('edit','write','apply_patch','replace_in_file','write_file') or bool(re.search(r'\b(sed\s+-i|perl\s+-i|apply_patch|tee\s+|cat\s+[^|;]*>\s*|python\S*\s+-c[^\n]*(?:write_text|open\([^)]*["\']w))',cmd,re.I)))
   test=bool(re.search(r'\b(pytest|unittest|tox|nox|cargo\s+test|npm\s+test|go\s+test|mvn\s+test|gradle\s+test|nosetests)\b|test_[A-Za-z0-9_]+\.py',low))
   explore=(fn in ('read','grep','search') or (bool(re.search(r'\b(ls|find|rg|grep|git\s+(?:status|log|show|diff)|head|tail|cat|sed)\b',low)) and not edit))
   events.append({'step_id':sid,'function':fn,'command':cmd,'edit':edit,'test':test,'explore':explore})
 edits=[x for x in events if x['edit']]; tests=[x for x in events if x['test']]; first=edits[0]['step_id'] if edits else None; last=edits[-1]['step_id'] if edits else None
 return {'telemetry_status':'partial_trace','tool_calls':len(events),'tool_counts':dict(toolhist),'repo_exploration_calls':sum(x['explore'] for x in events),'implementation_edit_calls':len(edits),'verification_calls':len(tests),'first_substantive_edit_step':first,'steps_before_first_edit':first-1 if first is not None else None,'tests_before_first_edit':sum(x['step_id']<first for x in tests) if first is not None else None,'tests_after_final_edit':sum(x['step_id']>last for x in tests) if last is not None else None,'command_calls':sum(x['function']=='exec' for x in events),'event_classification':'heuristic from preserved tool call names and shell command strings'}
telemetry={r['run_id']:trace_for(r) for r in rows}
for r in rows:
 r.update(telemetry[r['run_id']]); r['commands_executed']=telemetry[r['run_id']].get('command_calls')
(A/'E007-RUNS.jsonl').write_text(''.join(json.dumps(x,sort_keys=True)+'\n' for x in rows))
for r in rows:
 r['execution_record_missing']=bool(r.get('execution_record_missing'))
resource={}
for e in EFFORTS:
 group=[r for r in rows if r['reasoning_effort']==e]
 resource[e]={'attempted_runs':30,'successes':scores[e]['successes'],'wall_clock_seconds_all':summarize([r.get('wall_clock_seconds') for r in group]),'wall_clock_seconds_successful':summarize([r.get('wall_clock_seconds') for r in group if r['success']]),'agent_steps_all':summarize([r.get('agent_steps') for r in group]),'agent_steps_successful':summarize([r.get('agent_steps') for r in group if r['success']]),'input_tokens_all':summarize([r.get('input_tokens') for r in group]),'input_tokens_successful':summarize([r.get('input_tokens') for r in group if r['success']]),'output_tokens_all':summarize([r.get('output_tokens') for r in group]),'output_tokens_successful':summarize([r.get('output_tokens') for r in group if r['success']]),'total_tokens_all':summarize([r.get('total_tokens') for r in group]),'total_tokens_successful':summarize([r.get('total_tokens') for r in group if r['success']]),'direct_cost_all':summarize([r.get('direct_cost') for r in group]),'direct_cost_successful':summarize([r.get('direct_cost') for r in group if r['success']]),'cost_per_attempted_task':None,'cost_per_successful_task':None,'runs_with_missing_execution_record':sum(bool(r.get('execution_record_missing')) for r in group),'first_edit_step_all':summarize([telemetry[r['run_id']].get('first_substantive_edit_step') for r in group])}
behavior_by_effort={e:{k:summarize([telemetry[r['run_id']].get(k) for r in rows if r['reasoning_effort']==e]) for k in ('repo_exploration_calls','implementation_edit_calls','verification_calls','steps_before_first_edit','tests_before_first_edit','tests_after_final_edit','command_calls')} for e in EFFORTS}
ratios={}
for e in ('high','max'):
 ratios[e]={}
 for metric in ('wall_clock_seconds_all','agent_steps_all','input_tokens_all','output_tokens_all','total_tokens_all'):
  a=resource[e][metric]['mean']; b=resource['medium'][metric]['mean']; ratios[e][metric+'_over_medium']=a/b if a is not None and b else None

case_table={k:{'difficulty':cases[k]['difficulty'],'original_medium':bool(cases[k]['original_medium_success']),'original_max':bool(cases[k]['original_max_success']),'medium':okval(by[k]['medium']),'high':okval(by[k]['high']),'max':okval(by[k]['max']),'runs':{e:{'run_id':by[k][e]['run_id'],'wall_clock_seconds':by[k][e].get('wall_clock_seconds'),'agent_steps':by[k][e].get('agent_steps'),'total_tokens':by[k][e].get('total_tokens')} for e in EFFORTS}} for k in by}
summary={'experiment_id':'E007','status':'complete','planned_runs':90,'completed_runs':90,'scored_runs':90,'unscored_runs':0,'scores':scores,'tier_scores':tier_scores,'replication':orig,'pairwise':pairs,'cochran_q':coch,'cochran_q_by_tier':coch_by_tier,'unique_solves':unique,'effort_transitions':higher,'efficiency':resource,'resource_multipliers_vs_medium':ratios,'behavioral_metrics_by_effort':behavior_by_effort,'behavioral_telemetry':{'runs_with_trace':sum(t.get('telemetry_status')=='partial_trace' for t in telemetry.values()),'runs_with_execution_metadata_missing':sum(bool(r.get('execution_record_missing')) for r in rows),'interpretation':'Tool-call categories are heuristic; first-edit timing and test ordering can be missing where edit commands were encoded inside opaque scripts. Cost/billing unavailable for every run.'},'infrastructure_errors':sum(r.get('infrastructure_status') not in ('OK','execution_metadata_incomplete') for r in rows),'protocol_deviations':['One E006-K05 High Devin session has a complete final session export and evaluator result, but the outer Docker wrapper record was lost during a Codex API reconnect interruption. Its run remains in the primary cell; duration/start/end and wrapper exit code are null and flagged.'],'case_results':case_table,'trace_telemetry':telemetry}
(A/'E007-RESULTS.json').write_text(json.dumps(summary,indent=2,sort_keys=True)+'\n')

# Shared drawing primitives, using the repository's restrained publication palette.
CH.mkdir(exist_ok=True)
def font(size=22,bold=False):
 paths=['/System/Library/Fonts/Supplemental/Arial Bold.ttf' if bold else '/System/Library/Fonts/Supplemental/Arial.ttf','/System/Library/Fonts/SFNS.ttf']
 for p in paths:
  try:return ImageFont.truetype(p,size)
  except:pass
 return ImageFont.load_default()
def canvas(title,subtitle=''):
 im=Image.new('RGB',(1400,850),BG); d=ImageDraw.Draw(im); d.text((80,42),title,font=font(34,True),fill=INK)
 if subtitle:d.text((80,92),subtitle,font=font(18),fill=MUTED)
 return im,d
def bar_chart(path,title,labels,series,ymax=1,suffix='',subtitle=''):
 im,d=canvas(title,subtitle); left,top,right,bottom=140,180,1300,700; d.line((left,top,left,bottom),fill=INK,width=2); d.line((left,bottom,right,bottom),fill=INK,width=2)
 for j in range(6):
  val=ymax*j/5; y=bottom-(bottom-top)*j/5; d.line((left,y,right,y),fill=GRID,width=1); d.text((35,y-10),f'{val:.0%}' if suffix=='%' else f'{val:g}{suffix}',font=font(16),fill=MUTED)
 groups=len(labels); sw=len(series); gw=(right-left)/max(groups,1); bw=min(75,gw/(sw+1))
 for i,l in enumerate(labels):
  center=left+gw*(i+.5); d.text((center-55,bottom+20),l,font=font(18),fill=INK)
  for j,(name,vals) in enumerate(series.items()):
   val=vals[i]; val=0 if val is None else max(0,val); h=(bottom-top)*min(val/ymax,1); x=center+(j-(sw-1)/2)*bw-bw*.36
   d.rectangle((x,bottom-h,x+bw*.72,bottom),fill=COLORS.get(name.lower(),'#5C8A72'))
   lab=f'{val:.0%}' if suffix=='%' else f'{val:.1f}{suffix}' if val<100 else f'{val:.0f}{suffix}'
   d.text((x-4,bottom-h-26),lab,font=font(15),fill=INK)
 for j,name in enumerate(series):
  x=left+j*180; d.rectangle((x,755,x+22,777),fill=COLORS.get(name.lower(),'#5C8A72')); d.text((x+30,752),name.title(),font=font(17),fill=INK)
 im.save(path)
bar_chart(CH/'01-solve-rate-by-effort.png','E007 solve rate by reasoning effort',['Overall'],{e:[scores[e]['rate']] for e in EFFORTS},1,'%', '30 paired primary cases; 95% exact binomial intervals are in E007-RESULTS.json')
bar_chart(CH/'02-solve-rate-by-difficulty-effort.png','Solve rate by difficulty and effort',TIERS,{e:[tier_scores[d][e]['rate'] for d in TIERS] for e in EFFORTS},1,'%', 'Ten cases per difficulty tier')
bar_chart(CH/'03-original-vs-e007-medium.png','Original vs E007: Medium', ['Original','E007'],{'medium':[orig['medium']['original_successes']/30,scores['medium']['rate']]},1,'%', 'Case-level agreement: '+fmt(orig['medium']['exact_case_agreement_rate']*100,1)+'%')
bar_chart(CH/'04-original-vs-e007-max.png','Original vs E007: Max',['Original','E007'],{'max':[orig['max']['original_successes']/30,scores['max']['rate']]},1,'%', 'Case-level agreement: '+fmt(orig['max']['exact_case_agreement_rate']*100,1)+'%')
bar_chart(CH/'05-wall-time-by-effort.png','Wall time by effort (mean, minutes)',EFFORTS,{'mean':[resource[e]['wall_clock_seconds_all']['mean']/60 if resource[e]['wall_clock_seconds_all']['mean'] else None for e in EFFORTS]},max(1,max((resource[e]['wall_clock_seconds_all']['mean'] or 0)/60 for e in EFFORTS)*1.18),'m','All attempted runs; missing wrapper duration excluded (n shown in JSON)')
bar_chart(CH/'06-agent-steps-by-effort.png','Agent steps by effort (mean)',EFFORTS,{'mean':[resource[e]['agent_steps_all']['mean'] for e in EFFORTS]},max(1,max(resource[e]['agent_steps_all']['mean'] or 0 for e in EFFORTS)*1.18),'','All attempted runs; session-export counts')
im,d=canvas('Direct cost per successful case','No run exposed billed usage or direct cost; this is unavailable, not $0.')
d.rounded_rectangle((180,260,1220,570),radius=24,outline=GRID,width=3)
d.text((470,375),'Unavailable for all effort settings',font=font(30,True),fill=MUTED)
im.save(CH/'07-cost-per-successful-case.png')
# Case transition heatmap with categorical outcome; rows are fixed canonical manifest order.
im,d=canvas('Case-level effort transitions','Green = solved, red = failed. Rows retain the frozen canonical case order.')
left,top=360,160; cw=245; rh=20; d.text((left,top-35),'Medium',font=font(18,True),fill=INK); d.text((left+cw,top-35),'High',font=font(18,True),fill=INK); d.text((left+2*cw,top-35),'Max',font=font(18,True),fill=INK)
for i,c in enumerate(m['cases']):
 k=c['case_id']; y=top+i*rh; d.text((45,y+1),f"{k}  ({c['difficulty']})",font=font(14),fill=INK)
 for j,e in enumerate(EFFORTS):
  yes=case_table[k][e]; color='#6AA982' if yes else '#D47B78'; x=left+j*cw; d.rectangle((x,y,x+200,y+15),fill=color); d.text((x+210,y-1),'PASS' if yes else 'FAIL',font=font(13),fill=INK)
im.save(CH/'08-case-level-effort-transitions.png')

# Report tables and interpretation inputs.
def score_table():
 out='| Difficulty | Medium | High | Max |\n|---|---:|---:|---:|\n'
 for d in TIERS:out+=f"| {d.title()} | {tier_scores[d]['medium']['successes']}/10 | {tier_scores[d]['high']['successes']}/10 | {tier_scores[d]['max']['successes']}/10 |\n"
 return out
def pair_table():
 out='| Pair | Both solve | First only | Second only | Both fail | Δ first−second | Exact McNemar p |\n|---|---:|---:|---:|---:|---:|---:|\n'
 for key,p in pairs.items():out+=f"| {key.replace('_vs_',' vs ').title()} | {p['both_solve']} | {p['first_only']} | {p['second_only']} | {p['both_fail']} | {p['rate_difference_first_minus_second']:+.1%} | {p['mcnemar_exact_two_sided_p']:.4f} |\n"
 return out
def eval_status(r):
 d=readj(Path(r['evaluator_output']))
 def status(*keys):
  for k in keys:
   x=d.get(k)
   if isinstance(x,dict):
    v=x.get('overall') or x.get('status')
    if v:return v
  return 'NA'
 return {'public':status('tests_after','public'),'heldout':status('heldout_tests','heldout'),'regression':status('regression_tests','regression')}
def failing_tests(r):
 d=readj(Path(r['evaluator_output'])); out=[]
 for keys,label in [(('tests_after','public'),'public'),(('heldout_tests','heldout'),'heldout'),(('regression_tests','regression'),'regression')]:
  x=next((d[k] for k in keys if isinstance(d.get(k),dict)),{})
  if (x.get('overall') or x.get('status')) not in ('fail','failed'):continue
  for c in x.get('commands') or [x]:
   if c.get('status')!='fail':continue
   text=str(c.get('output') or c.get('stderr') or '')
   names=re.findall(r'(?:FAILED|FAIL:)\s+([^\s]+)',text)
   out.append(f"{label}: {', '.join(names) if names else str(c.get('command','test command failed'))}")
 return out
def eff_table():
 out='| Effort | Success | Mean min | Median min | Mean steps | Median steps | Mean input tokens | Mean output tokens | Mean total tokens | Direct cost | First edit step mean |\n|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|\n'
 for e in EFFORTS:
  z=resource[e]; wall=z['wall_clock_seconds_all']; steps=z['agent_steps_all']; inp=z['input_tokens_all']; outp=z['output_tokens_all']; total=z['total_tokens_all']; edit=z['first_edit_step_all']
  out+=f"| {e.title()} | {scores[e]['successes']}/30 | {fmt(wall['mean']/60 if wall['mean'] else None,1)} (n={wall['n_available']}) | {fmt(wall['median']/60 if wall['median'] else None,1)} | {fmt(steps['mean'],1)} | {fmt(steps['median'],1)} | {fmt(inp['mean'],0)} | {fmt(outp['mean'],0)} | {fmt(total['mean'],0)} | unavailable | {fmt(edit['mean'],1)} (n={edit['n_available']}) |\n"
 out+='\n**Successful runs only**\n\n| Effort | Successful runs | Mean min | Median min | Mean steps | Median steps | Mean input tokens | Mean output tokens | Mean total tokens |\n|---|---:|---:|---:|---:|---:|---:|---:|---:|\n'
 for e in EFFORTS:
  z=resource[e]; w=z['wall_clock_seconds_successful']; s=z['agent_steps_successful']; i=z['input_tokens_successful']; o=z['output_tokens_successful']; t=z['total_tokens_successful']
  out+=f"| {e.title()} | {scores[e]['successes']}/30 | {fmt(w['mean']/60 if w['mean'] else None,1)} (n={w['n_available']}) | {fmt(w['median']/60 if w['median'] else None,1)} | {fmt(s['mean'],1)} | {fmt(s['median'],1)} | {fmt(i['mean'],0)} | {fmt(o['mean'],0)} | {fmt(t['mean'],0)} |\n"
 return out
rep='| Condition | Original | E007 | Both solve | Both fail | Original only | E007 only | Exact agreement |\n|---|---:|---:|---:|---:|---:|---:|---:|\n'
for e in ('medium','max'):
 x=orig[e]; rep+=f"| {e.title()} | {x['original_successes']}/30 | {x['e007_successes']}/30 | {x['both_solve']} | {x['both_fail']} | {x['original_only_solves']} | {x['e007_only_solves']} | {x['exact_case_agreement']}/30 ({x['exact_case_agreement_rate']:.1%}) |\n"
trans='| Increasing effort | Failure → success | Success → failure |\n|---|---|---|\n'
for key,x in higher.items():trans+=f"| {key.replace('_to_',' → ').title()} | {', '.join(x['failure_to_success']) or 'none'} | {', '.join(x['success_to_failure']) or 'none'} |\n"
unique_text='\n'.join(f"- **{e.title()} only:** {', '.join(unique[e]) or 'none'}" for e in EFFORTS)
repdoc=f'''# E007 Replication Analysis

## Result

{rep}
Difficulty-specific case-level replication:

| Tier | Medium original → E007 | Agreement | Max original → E007 | Agreement |
|---|---:|---:|---:|---:|
'''
for d in TIERS:
 ks=[k for k in by if cases[k]['difficulty']==d]
 vals=[]
 for e,field in [('medium','original_medium_success'),('max','original_max_success')]:
  agree=sum(bool(cases[k][field])==okval(by[k][e]) for k in ks); old=sum(bool(cases[k][field]) for k in ks); new=sum(okval(by[k][e]) for k in ks); vals.extend([f'{old}/10 → {new}/10',f'{agree}/10 ({agree/10:.0%})'])
 repdoc+=f'| {d.title()} | {vals[0]} | {vals[1]} | {vals[2]} | {vals[3]} |\n'
repdoc+='\nAggregate scores are distinct from exact case-level replication. A match in total solved count does not establish that the same cases were solved.\n'
(A/'E007-REPLICATION-ANALYSIS.md').write_text(repdoc)

effdoc=f'''# E007 Effort Analysis

## Success

| Effort | Overall |\n|---|---:|\n'''
for e in EFFORTS:effdoc+=f"| {e.title()} | {scores[e]['successes']}/30 ({scores[e]['rate']:.1%}; exact 95% CI {scores[e]['exact_95_ci'][0]:.1%}–{scores[e]['exact_95_ci'][1]:.1%}) |\n"
effdoc+='\n'+score_table()+f"\n## Paired comparisons\n\n{pair_table()}\nExact two-sided McNemar p-values use the discordant pairs. Paired bootstrap 95% intervals for the absolute rate difference are in E007-RESULTS.json; solve-rate intervals use exact Clopper–Pearson intervals. Cochran Q across the three efforts: Q={fmt(coch['Q'],3)}, df={coch['df']}, asymptotic p={fmt(coch['asymptotic_p'],4)}.\n\n## Transitions\n\n{trans}\n\n## Cases solved by only one effort\n\n{unique_text}\n\n## Efficiency\n\n{eff_table()}\n"
effdoc+='\nRatios relative to Medium are in `E007-RESULTS.json`. Cochran Q by difficulty tier is also reported there. No run exposed direct billing or account-reported cost, so cost per attempt and per successful case are unavailable, not zero. One recovered E006 K05 High session lacks the wrapper timing record; it contributes to session-derived steps/tokens and outcome but not runtime summaries.\n'
effdoc+='\n## Difficulty × effort\n\n'+score_table()+"\nE007’s observed pattern does not match the parent study: Medium has fewer aggregate solves than both High and Max. Hard and very-hard tier samples are small and should be interpreted descriptively.\n"
(A/'E007-EFFORT-ANALYSIS.md').write_text(effdoc)

# Failure analysis uses evaluator transitions plus observed final reports and trace classes; no aggregate-only causal claims.
faildoc='''# E007 Failure and Behavior Analysis

## Scope and trace limits

Four cases changed outcome across effort levels. The complete final session exports were inspected for all conditions on those cases. Preserved Devin exports contain timestamped agent steps, tool-call names/arguments, observations, and some final responses. The telemetry parser classifies tool calls heuristically; shell commands embedded in opaque scripts can hide edit/test timing. There is no uniform shell transcript for every run, and one E006 K05 High outer wrapper record is missing. Treat mechanism descriptions below as observed process evidence or plausible interpretations, not causal identification.

## Outcome-changing cases

'''
for k in by:
 vals={e:okval(by[k][e]) for e in EFFORTS}
 if len(set(vals.values()))==1:continue
 faildoc+=f"### {k} ({cases[k]['difficulty']})\n\n| Effort | Outcome | Public | Held-out | Regression | Steps | Tool calls | Read/search calls | Edit/write calls | Verification calls | First edit step | Tests before edit | Tests after final edit |\n|---|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|\n"
 for e in EFFORTS:
  r=by[k][e]; t=telemetry[r['run_id']]; st=eval_status(r); faildoc+=f"| {e.title()} | {'pass' if vals[e] else 'fail'} | {st['public']} | {st['heldout']} | {st['regression']} | {r.get('agent_steps')} | {t.get('tool_calls')} | {t.get('repo_exploration_calls')} | {t.get('implementation_edit_calls')} | {t.get('verification_calls')} | {t.get('first_substantive_edit_step')} | {t.get('tests_before_first_edit')} | {t.get('tests_after_final_edit')} |\n"
  for issue in failing_tests(r): faildoc+=f"- **{e.title()} evaluator failure:** {issue}\n"
 faildoc+='\n'
 # Summarize observable final answers, bounded to avoid copying benchmark source/task content.
 for e in EFFORTS:
  p=Path(by[k][e].get('session_export') or '')
  if not p.exists():continue
  steps=readj(p).get('steps') or []; finals=[s.get('message','') for s in steps if s.get('source')=='agent' and s.get('message')]
  if finals:
   tail=re.sub(r'\s+',' ',finals[-1])[:500]
   faildoc+=f"- **{e.title()} observed final report:** {tail}\n"
 faildoc+='\n**Observed behavior:** The public, held-out, regression statuses and failing test identifiers above come from the frozen evaluator outputs. The final agent summaries and tool counts are preserved session-trace facts. On E004-N03, Medium/High passed all visible tests but failed a held-out test about caller mutation after `replace`; Max passed it. On E005-K01, Medium passed public tests but retained a defaulted value under the held-out `exclude_defaults` test; High/Max passed. On E002-C02 Medium, four public cases failed on missing alias keys while both higher effort runs passed. On E002-C04 Max, the held-out disabled sized iterable still had `total=None`; Medium/High passed. **Plausible interpretation:** outcome differences correspond to concrete remaining edge cases in the failed patches, not simply failure to run tests. **Unresolved cause:** effort itself cannot be isolated from stochastic action paths in one run per case-condition.\n\n'
faildoc+='## Stable cases\n\nThe other 26 cases have identical pass/fail outcomes across all three effort conditions. This does not imply identical work: step, token, and tool traces vary. The available trace parser does not establish a fully comparable planning-versus-implementation taxonomy.\n'
(A/'E007-FAILURE-ANALYSIS.md').write_text(faildoc)

report=f'''# E007 Report

**Status: all 90 primary cells executed and evaluated.** E007 is an independent replication of SWE-2 effort-level behavior with High added; it is not an old-Devin-versus-SWE-2 comparison.

## Execution and provenance

Preserved E002–E006 evidence verified SWE-2 Medium and Max as the original conditions. Current execution used Devin CLI 3000.10.21, `--model swe-2-medium`, `--model swe-2-high`, and `--model swe-2-max`; the authenticated in-container catalog showed all three selectable and labeled Free. All 90 intended cells have evaluator results. There were no container errors and no substantive human interventions. The evaluator ran serially after agent execution.

One E006 K05 High session export contains the full final 54-step session and was evaluated successfully after a Codex API reconnect interrupted the outer process before it wrote container timing/exit metadata. The record has a missing-wrapper flag; its outcome, model identity, steps, and token counts are preserved, while runtime, start/end timestamps, and wrapper return code remain null. This is a documented protocol deviation and is excluded from runtime summaries only.

## Primary results

| Effort | Solved | Exact 95% binomial CI |
|---|---:|---:|
'''
for e in EFFORTS:report+=f"| {e.title()} | {scores[e]['successes']}/30 ({scores[e]['rate']:.1%}) | {scores[e]['exact_95_ci'][0]:.1%}–{scores[e]['exact_95_ci'][1]:.1%} |\n"
report+='\n'+score_table()+f"\n## Replication\n\n{rep}\nE007 Medium and Max each underperformed the original aggregate totals. Case-level agreement is shown above and disaggregated by tier in E007-REPLICATION-ANALYSIS.md.\n\n## Paired effort and statistics\n\n{pair_table()}\nCochran Q={fmt(coch['Q'],3)} (df={coch['df']}; asymptotic p={fmt(coch['asymptotic_p'],4)}). Pairwise exact McNemar tests are shown in the table. Paired bootstrap confidence intervals for absolute differences and exact solve-rate intervals are in E007-RESULTS.json. Small n, especially per tier, limits precision.\n\n## Efficiency and behavior\n\n{eff_table()}\nMean/median resource summaries use observed values only, with the available n retained. Direct cost and billing were not returned by the session exports, so cost per task/success cannot be calculated. Steps before first edit are heuristic session-trace estimates. Eight requested charts are in `charts/`. Detailed outcome-transition trace comparisons are in E007-FAILURE-ANALYSIS.md.\n\n## Interpretation\n\nThe preregistered nonuniform-effort hypothesis is not supported as an aggregate performance curve: Medium solved fewer cases than High and Max, while High and Max tied overall. Only four cases changed outcome across effort settings; 26 were stable. Moderate-tier details and case transitions should be read from machine-derived outputs. No causal account of effort is warranted from a single run per cell.\n\n## Deviations and publication readiness\n\nThe protocol/provenance files record the initial pre-session authentication/proxy recovery, the evaluator path repair, and brief early evaluator overlap. The interrupted E006 K05 High wrapper record is the only scored cell with incomplete execution metadata. All 90 cells have evaluator output; no additional tasks or stochastic repeats were added. Raw session exports and private workspaces are preserved outside the repository.\n\nThe result is publication-ready as a transparently documented single-run replication with High added, subject to independent review of trace-derived telemetry and the explicitly missing wrapper timing record. Recompute from `E007-RUNS.jsonl` using the analysis script before reuse.\n"
(A/'E007-REPORT.md').write_text(report)
print(json.dumps({'runs':len(rows),'scores':{e:scores[e]['successes'] for e in EFFORTS},'tiers':{d:{e:tier_scores[d][e]['successes'] for e in EFFORTS} for d in TIERS},'charts':len(list(CH.glob('*.png'))),'trace_runs':len(telemetry),'run_with_missing_wrapper':summary['behavioral_telemetry']['runs_with_execution_metadata_missing']}))
