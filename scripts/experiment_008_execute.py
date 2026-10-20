#!/usr/bin/env python3
"""Execute the frozen E008 targeted repeats sequentially with per-run sanitation."""
from __future__ import annotations
import hashlib, json, os, re, shutil, subprocess, sys, time
from datetime import datetime, timezone
from pathlib import Path

REPO=Path(__file__).resolve().parents[1]
ART=REPO/'artifacts'/'experiment-008'
MAN=ART/'E008-RERUN-MANIFEST.json'
E7=REPO/'artifacts'/'experiment-007'/'E007-MANIFEST.json'
PRIVATE=REPO.parent/'devin-agent-benchmark-e008-private'
CREDENTIAL=Path.home()/'.local/share/devin/credentials.toml'


def readj(p): return json.loads(p.read_text())
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def now(): return datetime.now(timezone.utc).isoformat()
def ignore_generated(_directory,names):
    return {n for n in names if n in {'__pycache__','.pytest_cache'} or n.endswith('.pyc')}
def cache_paths(root):
    found=[]
    for p in root.rglob('*'):
        if p.is_dir() and p.name in {'__pycache__','.pytest_cache'}:
            found.append(p); continue
        if p.is_file() and p.suffix=='.pyc': found.append(p)
    return found
def clean_generated(root):
    removed=[]
    for p in sorted(cache_paths(root),key=lambda x:len(x.parts),reverse=True):
        if not p.exists(): continue
        removed.append(str(p.relative_to(root)))
        if p.is_dir(): shutil.rmtree(p,ignore_errors=True)
        else: p.unlink(missing_ok=True)
    return removed
def sanitize_evaluator(source,destination):
    shutil.copytree(source,destination,ignore=ignore_generated)
    removed=clean_generated(destination)
    remaining=[str(p.relative_to(destination)) for p in cache_paths(destination)]
    record={'source':str(source),'source_tree_sha256':tree_hash(source),'clean_evaluator_path':str(destination),'removed_cache_paths':removed,'remaining_cache_paths_before_evaluation':remaining,'sanitation_verified_clean_before_evaluation':not remaining}
    (destination.parent/'evaluator-sanitation.json').write_text(json.dumps(record,indent=2,sort_keys=True)+'\n')
    if remaining: raise RuntimeError('evaluator copy is not cache-clean after sanitation')
    return removed
def tree_hash(root):
    h=hashlib.sha256()
    for p in sorted(root.rglob('*')):
        rel=p.relative_to(root).as_posix()
        if any(part in {'.git','__pycache__','.pytest_cache'} for part in p.relative_to(root).parts) or p.suffix=='.pyc': continue
        if p.is_symlink(): h.update(b'L'+rel.encode()+b'\0'+os.readlink(p).encode()+b'\0')
        elif p.is_file(): h.update(b'F'+rel.encode()+b'\0'+sha(p).encode()+b'\0')
    return h.hexdigest()
def case_source(c):
    e=c['original_experiment']; cid=c['case_id']; src=c['source_case_id']
    if e=='experiment-002': return REPO.parent/'devin-agent-benchmark-cases-work'/src
    if e=='experiment-004': return REPO.parent/'devin-agent-benchmark-e004-private'/'cases'/cid/'buggy'
    if e=='experiment-005': return REPO/'.benchmarks'/'experiment-005-private'/'agent-workspaces'/cid
    if e=='experiment-006':
        if cid.endswith(tuple(f'K{i:02d}' for i in range(1,6))): return REPO/'.benchmarks'/'experiment-006-private'/'historical-cases'/cid/'agent-workspace'
        return REPO/'.benchmarks'/'experiment-006-private'/'cases'/cid/'buggy'
    raise ValueError(e)
def case_prompt(c): return (REPO/c['prompt']).resolve()
def duration(c): return {'experiment-002':3600,'experiment-004':3600,'experiment-005':5400,'experiment-006':7200}[c['original_experiment']]
def docker_agent_cmd(c,run,ws,out):
    e=c['original_experiment']; image='devin-e006:3000.10.21-r7' if e=='experiment-006' else 'devin-e002:3000.10.21'
    cmd=['docker','run','--rm','--init','--platform','linux/arm64','--read-only','--cap-drop','ALL','--security-opt','no-new-privileges:true','--pids-limit','512','--memory','4g','--cpus','4','--workdir','/workspace','--network','e002-internal','--mount',f'type=bind,src={ws},dst=/workspace','--mount',f'type=bind,src={out},dst=/artifacts','--mount',f'type=bind,src={CREDENTIAL},dst=/run/devin-data/devin/credentials.toml,ro','--tmpfs','/run:rw,noexec,nosuid,size=512m','--tmpfs','/tmp:rw,noexec,nosuid,size=1g','--env','HOME=/root','--env','XDG_CONFIG_HOME=/run/devin-config','--env','XDG_DATA_HOME=/run/devin-data']
    if e=='experiment-006':
        cfg=readj(REPO/'manifests/experiment-006-config.json'); rt=cfg['runtime']['case_environments'][c['case_id']]
        base='/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin'
        cmd += ['--env','PATH=/opt/e006/venvs/'+rt['venv']+'/bin:'+base,'--env','LD_LIBRARY_PATH='+rt['runtime_lib'],'--env','E006_CASE_ID='+c['case_id']]
    cmd += ['--env','HTTPS_PROXY=http://egress-proxy:3128','--env','HTTP_PROXY=http://egress-proxy:3128','--env','NO_PROXY=localhost,private-network',image,'--model',run['model'],'--print','--prompt-file','<WORKDIR>/TASK.md','--export','/artifacts/devin-session-export.json','--permission-mode','dangerous','--respect-workspace-trust','false']
    return cmd

def evaluator_run(c,run,ws,baseline,out,raw):
    e=c['original_experiment']; cid=c['case_id']; srcid=c['source_case_id']; dest=out/'evaluation'; dest.mkdir(parents=True,exist_ok=True)
    evsource=None; evclean=None; sanitation=[]; commands=[]
    if e=='experiment-002':
        evsource=REPO/'evaluation'/'experiment-001'/srcid
        evclean=out/'clean-evaluator'; sanitation=sanitize_evaluator(evsource,evclean)
        # The public frozen evaluator checks this inherited source audit before scoring.
        source=case_source(c); audit=json.loads((source.parent/f'{srcid}.leak-audit.json').read_text())
        (ws.parent/f'{ws.name}.leak-audit.json').write_text(json.dumps({'audit_version':1,'status':'pass','case_id':srcid,'basis':'Inherited passing frozen E002 sanitized source audit; exact source and prompt re-staged for E008.','parent_audit':str(source.parent/f'{srcid}.leak-audit.json'),'parent_export_sha256':audit.get('export_sha256'),'prompt_sha256':sha(case_prompt(c)),'problems':[]},indent=2)+'\n')
        evresult=dest/'evaluation-result.json'
        rr={'run_id':raw['run_id'],'condition':raw['effort'].upper(),'effort_level':raw['effort'],'started_at':raw['started_at_utc'],'ended_at':raw['ended_at_utc'],'elapsed_seconds':raw['wall_time_seconds'],'steps':raw['steps'],'interventions':[],'termination_reason':'timeout' if raw['timed_out'] else 'completed','agent':{'name':'Devin','cli_version':'3000.10.21 (611c1cba)','model':raw['model'],'model_family':'SWE-2'}}
        (out/'runner-result.json').write_text(json.dumps(rr,indent=2)+'\n')
        cmd=[sys.executable,str(REPO/'scripts/evaluate_run.py'),'--manifest',str(REPO/'manifests/experiment-001.json'),'--case-id',srcid,'--run-root',str(out),'--workspace',str(ws),'--output-dir',str(dest),'--baseline-dir',str(baseline),'--heldout-metadata',str(evclean/'metadata.json'),'--env-root',str(REPO.parent/'devin-agent-benchmark-evaluator-envs/experiment-001')]
        p=subprocess.run(cmd,text=True,capture_output=True,timeout=1800,check=False); (dest/'evaluator.stdout.txt').write_text(p.stdout or ''); (dest/'evaluator.stderr.txt').write_text(p.stderr or '')
        if p.returncode not in (0,1): return {'status':'evaluator_infrastructure_invalid','reason':'E002 evaluator returned infrastructure/error status','returncode':p.returncode,'stdout':p.stdout,'stderr':p.stderr,'result_path':str(evresult)},sanitation,str(evclean)
        d=readj(evresult); suites={'public':d['tests_after']['overall'],'heldout':d['heldout_tests']['overall'],'regression':d['regression_tests']['overall']}
        return {'status':'valid','task_success':d['task_success'],'suites':suites,'returncode':p.returncode,'result_path':str(evresult),'sanitation_verified_clean_before_evaluation':True},sanitation,str(evclean)
    if e=='experiment-004':
        evsource=REPO.parent/'devin-agent-benchmark-e004-private'/'evaluation'/cid
        evclean=out/'clean-evaluator'; sanitation=sanitize_evaluator(evsource,evclean)
        env=os.environ.copy(); env['PYTHONPATH']=os.pathsep.join([str(ws/'src'),str(evclean)])
        commands={'public':[sys.executable,'-m','unittest','discover','-s','tests','-v'],'heldout':[sys.executable,'-m','unittest','discover','-s',str(evclean),'-p','test_behavior.py','-v'],'regression':[sys.executable,'-m','unittest','discover','-s',str(evclean),'-p','test_regression.py','-v']}
        results={k:run_cmd(v,ws if k=='public' else ws,env) for k,v in commands.items()}
        result=suite_record(results,dest); result['sanitation_verified_clean_before_evaluation']=True
        return result,sanitation,str(evclean)
    if e=='experiment-005':
        evsource=REPO/'.benchmarks'/'experiment-005-private'/'evaluation'/cid
        evclean=out/'clean-evaluator'; sanitation=sanitize_evaluator(evsource,evclean)
        historical=cid.startswith('E005-K'); env=os.environ.copy()
        if historical:
            hist=readj(REPO/'.benchmarks'/'experiment-005-private'/'historical-manifest.json'); hc=next(x for x in hist['cases'] if x['case_id']==cid); py=REPO/'.benchmarks'/'experiment-005-private'/'venv-py38/bin/python'; env['PYTHONPATH']=str(ws); pubs=[([str(py)]+__import__('shlex').split(x)[1:]) for x in hc['test_command']]; pycmd=str(py)
        else:
            pycmd=sys.executable; env['PYTHONPATH']=os.pathsep.join([str(ws/'src'),str(evclean)]); pubs=[[pycmd,'-m','unittest','discover','-s','tests','-v']]
        cmds={'public':pubs,'heldout':[[pycmd,'-m','unittest','discover','-s',str(evclean),'-p','test_behavior.py','-v']],'regression':[[pycmd,'-m','unittest','discover','-s',str(evclean),'-p','test_regression.py','-v']]}
        results={k:[run_cmd(cmd,ws,env) for cmd in v] for k,v in cmds.items()}
        flat={k:{'status':'pass' if all(x['status']=='pass' for x in vals) else 'fail','commands':vals} for k,vals in results.items()}
        result=suite_record(flat,dest); result['sanitation_verified_clean_before_evaluation']=True
        return result,sanitation,str(evclean)
    if e=='experiment-006':
        evsource=REPO/'.benchmarks'/'experiment-006-private'/'evaluation'/cid
        evclean=out/'clean-evaluator'; sanitation=sanitize_evaluator(evsource,evclean)
        from validate_experiment_006_runtime import commands_for_case,docker_prefix,shell_script,parse_container_output
        cfg=readj(REPO/'manifests/experiment-006-config.json'); hist=readj(REPO/'.benchmarks'/'experiment-006-private'/'historical-manifest.json'); hc=next((x for x in hist['cases'] if x['case_id']==cid),None); cm=next(x for x in cfg['cases'] if x['experiment_case_id']==cid)
        pubs=commands_for_case(cid,cm,hc); cs=[(f'public-{i}',x) for i,x in enumerate(pubs,1)]+[('held-out',f'python -m pytest -q /control/evaluation/{cid}/test_behavior.py'),('regression',f'python -m pytest -q /control/evaluation/{cid}/test_regression.py')]
        art=dest/'runtime'; art.mkdir(exist_ok=True); p=subprocess.run(docker_prefix(cfg,ws,evclean,art,cid)+['-c',shell_script(cs)],text=True,capture_output=True,timeout=1800,check=False)
        (art/'evaluator.stdout.txt').write_text(p.stdout or ''); (art/'evaluator.stderr.txt').write_text(p.stderr or '')
        try:
            parsed=parse_container_output(p.stdout or '',cs); pub=[v for k,v in parsed.items() if k.startswith('public-')]; suites={'public':'pass' if all(x['status']=='pass' for x in pub) else 'fail','heldout':parsed['held-out']['status'],'regression':parsed['regression']['status']}; status='valid'; ok=all(x=='pass' for x in suites.values())
        except BaseException as ex: return {'status':'evaluator_infrastructure_invalid','reason':str(ex),'returncode':p.returncode,'stdout':p.stdout,'stderr':p.stderr},sanitation,str(evclean)
        result={'status':status,'task_success':ok,'suites':suites,'returncode':p.returncode,'result_path':str(art/'evaluator.stdout.txt'),'sanitation_verified_clean_before_evaluation':True}
        (dest/'evaluation-result.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
        return result,sanitation,str(evclean)
    raise ValueError(e)
def run_cmd(cmd,cwd,env):
    try: p=subprocess.run(cmd,cwd=cwd,env=env,text=True,capture_output=True,timeout=1800,check=False); return {'command':cmd,'cwd':str(cwd),'returncode':p.returncode,'status':'pass' if p.returncode==0 else 'fail','stdout':p.stdout,'stderr':p.stderr}
    except subprocess.TimeoutExpired as ex: return {'command':cmd,'cwd':str(cwd),'returncode':124,'status':'fail','stdout':str(ex.stdout or ''),'stderr':str(ex.stderr or ''),'timed_out':True}
def suite_record(suites,dest):
    ok=all(suites[k]['status']=='pass' for k in ('public','heldout','regression')); result={'status':'valid','task_success':ok,'suites':{k:v['status'] for k,v in suites.items()},'details':suites}; (dest/'evaluation-result.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n'); return result

def preflight():
    if not CREDENTIAL.is_file(): raise RuntimeError('Devin credentials.toml missing')
    if subprocess.run(['docker','network','inspect','e002-internal'],capture_output=True).returncode: raise RuntimeError('frozen network missing')
    if not list(Path('/').glob('never-match')): pass
    versions=subprocess.run(['devin','--version'],capture_output=True,text=True)
    if versions.returncode or '3000.10.21 (611c1cba)' not in versions.stdout+versions.stderr: raise RuntimeError('Devin CLI version mismatch')
    images=subprocess.run(['docker','images','--format','{{.Repository}}:{{.Tag}}'],capture_output=True,text=True).stdout.splitlines()
    for im in ['devin-e002:3000.10.21','devin-e006:3000.10.21-r7']:
        if im not in images: raise RuntimeError('missing pinned image '+im)
    if not any('egress-proxy' in x for x in subprocess.run(['docker','ps','--format','{{.Names}}'],capture_output=True,text=True).stdout.splitlines()): raise RuntimeError('egress proxy is not running')

def main():
    import argparse
    ap=argparse.ArgumentParser(); ap.add_argument('--dry-run',action='store_true'); ap.add_argument('--execute',action='store_true'); ap.add_argument('--start-slot',type=int,default=1); args=ap.parse_args()
    if args.dry_run==args.execute: raise SystemExit('select exactly one of --dry-run or --execute')
    man=readj(MAN); e7=readj(E7); e7c={x['case_id']:x for x in e7['cases']}; cases={x['case_id']:x for x in e7['cases']}
    slots=[]
    for co in man['conditions']:
        c=cases[co['case_id']]
        for rep in range(1,co['new_trials']+1): slots.append((co,c,rep))
    if len(slots)!=33 or len({(x[0]['case_id'],x[0]['effort']) for x in slots})!=11: raise RuntimeError('frozen manifest does not match 33-run approval')
    runs=[]
    ledger=ART/'E008-RUNS.jsonl'
    for co,c,rep in slots:
        runid=f"E008-{co['case_id']}-{co['effort'].upper()}-R{rep}"
        p=case_prompt(c); src=case_source(c)
        if not src.is_dir() or not p.is_file(): raise RuntimeError(f'missing frozen source/prompt for {runid}: {src}, {p}')
        if co['model']!=('swe-2-medium' if co['effort']=='medium' else 'swe-2-max'): raise RuntimeError('model/effort identity mismatch')
        runs.append({'run_id':runid,'case_id':co['case_id'],'effort':co['effort'],'repetition':rep,'model':co['model'],'prompt_path':str(p),'prompt_sha256':sha(p),'source_path':str(src),'source_tree_sha256':tree_hash(src),'source_commit':c.get('source_commit'),'original_experiment':c['original_experiment']})
    if args.dry_run:
        for x in runs: print(json.dumps({**x,'devin_invoked':False}))
        return
    preflight()
    existing=[]
    if ledger.exists(): existing=[json.loads(s) for s in ledger.read_text().splitlines() if s.strip()]
    completed={x['run_id'] for x in existing}
    if completed: print('Resuming; existing run ids will not be repeated:',','.join(sorted(completed)),flush=True)
    PRIVATE.mkdir(parents=True,exist_ok=True)
    for slot,(co,c,rep),meta in zip(range(1,len(slots)+1),slots,runs):
        if slot<args.start_slot or meta['run_id'] in completed: continue
        rid=meta['run_id']; ws=PRIVATE/'workspaces'/rid; out=PRIVATE/'outputs'/rid; base=PRIVATE/'baselines'/rid
        if ws.exists() or out.exists() or base.exists(): raise RuntimeError(f'workspace/output exists for unledgered trial {rid}; refusing overwrite')
        ws.parent.mkdir(parents=True,exist_ok=True); out.mkdir(parents=True,exist_ok=False); base.parent.mkdir(parents=True,exist_ok=True)
        shutil.copytree(meta['source_path'],ws,symlinks=True,ignore=lambda d,names: {n for n in names if n in {'.git','__pycache__','.pytest_cache'} or n.endswith('.pyc')}); shutil.copytree(meta['source_path'],base,symlinks=True,ignore=lambda d,names: {n for n in names if n in {'.git','__pycache__','.pytest_cache'} or n.endswith('.pyc')}); shutil.copyfile(meta['prompt_path'],ws/'TASK.md')
        staged_hash=tree_hash(ws); started=now(); mono=time.monotonic(); cmd=docker_agent_cmd(c,co,ws,out); timeout=duration(c); timed=False
        try: p=subprocess.run(cmd,text=True,capture_output=True,timeout=timeout,check=False); rc=p.returncode; stdout=p.stdout or ''; stderr=p.stderr or ''
        except subprocess.TimeoutExpired as ex: timed=True; rc=124; stdout=ex.stdout.decode(errors='replace') if isinstance(ex.stdout,bytes) else (ex.stdout or ''); stderr=ex.stderr.decode(errors='replace') if isinstance(ex.stderr,bytes) else (ex.stderr or '')
        ended=now(); elapsed=time.monotonic()-mono; (out/'devin.stdout.txt').write_text(stdout); (out/'devin.stderr.txt').write_text(stderr)
        export=out/'devin-session-export.json'; session={}
        if export.exists():
            try: session=readj(export)
            except Exception: pass
        # Sanitize evaluator source and generated workspace caches before any tests execute.
        fm=session.get('final_metrics') or {}; nsteps=fm.get('total_steps') if isinstance(fm,dict) else None
        if nsteps is None: nsteps=len(session.get('steps',[])) if isinstance(session.get('steps'),list) else None
        it=fm.get('total_prompt_tokens') if isinstance(fm,dict) else None; ot=fm.get('total_completion_tokens') if isinstance(fm,dict) else None; ct=fm.get('total_cached_tokens') if isinstance(fm,dict) else None
        workspace_cache=clean_generated(ws); raw={'run_id':rid,'case_id':co['case_id'],'effort':co['effort'],'repetition':rep,'model':co['model'],'started_at_utc':started,'ended_at_utc':ended,'wall_time_seconds':elapsed,'steps':nsteps,'input_tokens':it,'output_tokens':ot,'cached_tokens':ct,'total_tokens':(it or 0)+(ot or 0) if it is not None or ot is not None else None,'session_id':session.get('session_id'),'container_returncode':rc,'timed_out':timed,'intervention_count':0,'workspace':str(ws),'baseline':str(base),'output_dir':str(out),'command':cmd,'devin_invoked':True,'prompt_sha256':meta['prompt_sha256'],'source_tree_sha256_before_run':meta['source_tree_sha256'],'staged_tree_sha256_before_task':staged_hash,'sanitized_agent_workspace_caches_before_evaluation':workspace_cache,'source_commit':meta['source_commit'],'original_experiment':meta['original_experiment'],'cli_version':'3000.10.21 (611c1cba)','session_export_path':str(export),'session_export_sha256':sha(export) if export.exists() else None}
        (out/'container-run-result.json').write_text(json.dumps(raw,indent=2,sort_keys=True)+'\n')
        sanitation=[]; evclean=None
        if rc!=0 and not export.exists(): ev={'status':'agent_or_container_failure','task_success':None,'reason':'nonzero container/Devin exit without session export','returncode':rc}
        else:
            try: ev,sanitation,evclean=evaluator_run(c,co,ws,base,out,raw)
            except Exception as ex:
                ev={'status':'evaluator_infrastructure_invalid','task_success':None,'reason':repr(ex),'traceback':__import__('traceback').format_exc()}
                sanpath=out/'evaluator-sanitation.json'
                if sanpath.exists():
                    san=readj(sanpath); sanitation=san.get('removed_cache_paths',[]); evclean=san.get('clean_evaluator_path')
        remaining=[str(p.relative_to(Path(evclean))) for p in cache_paths(Path(evclean))] if evclean else None
        record={**raw,'session_id':session.get('session_id'),'infrastructure_status':ev['status'],'task_success':ev.get('task_success'),'suite_results':ev.get('suites'),'failure_classification':('success' if ev.get('task_success') is True else 'agent_failure' if ev.get('status')=='valid' else ev['status']),'evaluator_result':ev,'evaluator_sanitation':{'occurred':evclean is not None,'clean_evaluator_path':evclean,'removed_cache_paths':sanitation if evclean else [],'remaining_cache_paths':remaining,'sanitation_verified_clean_before_evaluation':bool(evclean)},'cost_status':'unknown','cost_usd':None}
        with ledger.open('a') as f: f.write(json.dumps(record,sort_keys=True)+'\n'); f.flush(); os.fsync(f.fileno())
        (out/'ledger-record.json').write_text(json.dumps(record,indent=2,sort_keys=True)+'\n')
        print(json.dumps({'slot':slot,'run_id':rid,'status':record['infrastructure_status'],'task_success':record['task_success'],'elapsed_seconds':round(elapsed,2),'session_id':record['session_id'],'cost':'unknown'}),flush=True)

if __name__=='__main__': main()
