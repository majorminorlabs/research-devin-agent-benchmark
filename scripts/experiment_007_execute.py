#!/usr/bin/env python3
"""Execute E007's frozen case-condition matrix in fresh Docker workspaces."""
from __future__ import annotations
import argparse, hashlib, json, os, shutil, subprocess, sys, time
from datetime import datetime, timezone
from pathlib import Path

REPO=Path(__file__).resolve().parents[1]
ROOT=REPO/'artifacts'/'experiment-007'
PRIVATE=REPO.parent/'devin-agent-benchmark-e007-private'
MANIFEST=ROOT/'E007-MANIFEST.json'
CREDENTIAL=Path.home()/'.local/share/devin/credentials.toml'

def readj(p): return json.loads(p.read_text())
def source_for(c):
 exp=c['original_experiment']; cid=c['case_id']; srcid=c['source_case_id']
 if exp=='experiment-002': return REPO.parent/'devin-agent-benchmark-cases-work'/srcid
 if exp=='experiment-004': return REPO.parent/'devin-agent-benchmark-e004-private'/'cases'/cid/'buggy'
 if exp=='experiment-005': return REPO/'.benchmarks'/'experiment-005-private'/'agent-workspaces'/cid
 if exp=='experiment-006':
  if cid.endswith(tuple(f'K{i:02d}' for i in range(1,6))): return REPO/'.benchmarks'/'experiment-006-private'/'historical-cases'/cid/'agent-workspace'
  return REPO/'.benchmarks'/'experiment-006-private'/'cases'/cid/'buggy'
 raise ValueError(exp)
def prompt_path(c):
 p=c['prompt']; return (REPO/p).resolve() if not p.startswith('../') else (REPO/p).resolve()
def duration(c): return {'experiment-002':3600,'experiment-004':3600,'experiment-005':5400,'experiment-006':7200}[c['original_experiment']]
def docker_cmd(c,run,workspace,out):
 exp=c['original_experiment']; image='devin-e006:3000.10.21-r7' if exp=='experiment-006' else 'devin-e002:3000.10.21'
 lim=duration(c); net='e002-internal'; proxy='http://egress-proxy:3128'
 cmd=['docker','run','--rm','--init','--platform','linux/arm64','--read-only','--cap-drop','ALL','--security-opt','no-new-privileges:true','--pids-limit','512','--memory','4g','--cpus','4','--workdir','/workspace','--network',net,'--mount',f'type=bind,src={workspace},dst=/workspace','--mount',f'type=bind,src={out},dst=/artifacts','--mount',f'type=bind,src={CREDENTIAL},dst=/run/devin-data/devin/credentials.toml,ro','--tmpfs','/run:rw,noexec,nosuid,size=512m','--tmpfs','/tmp:rw,noexec,nosuid,size=1g','--env','HOME=/root','--env','XDG_CONFIG_HOME=/run/devin-config','--env','XDG_DATA_HOME=/run/devin-data']
 if exp=='experiment-006':
  cfg=readj(REPO/'manifests/experiment-006-config.json'); rt=cfg['runtime']['case_environments'][c['case_id']]
  base='/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin'
  cmd += ['--env','PATH=/opt/e006/venvs/'+rt['venv']+'/bin:'+base,'--env','LD_LIBRARY_PATH='+rt['runtime_lib'],'--env','E006_CASE_ID='+c['case_id']]
 cmd += ['--env',f'HTTPS_PROXY={proxy}','--env',f'HTTP_PROXY={proxy}','--env','NO_PROXY=localhost,private-network',image,'--model',run['model'],'--print','--prompt-file','<WORKDIR>/TASK.md','--export','/artifacts/devin-session-export.json','--permission-mode','dangerous','--respect-workspace-trust','false']
 return cmd

def stage(c,run):
 source=source_for(c).resolve(); p=prompt_path(c)
 if not source.is_dir(): raise RuntimeError(f'missing frozen source: {source}')
 if not p.is_file(): raise RuntimeError(f'missing frozen prompt: {p}')
 target=PRIVATE/'workspaces'/run['run_id']
 if target.exists(): raise RuntimeError(f'workspace already exists: {target}')
 target.parent.mkdir(parents=True,exist_ok=True)
 shutil.copytree(source,target,symlinks=True,ignore=shutil.ignore_patterns('.git','__pycache__','.pytest_cache'))
 shutil.copyfile(p,target/'TASK.md')
 return target

def main():
 ap=argparse.ArgumentParser(); ap.add_argument('--run-id'); ap.add_argument('--dry-run',action='store_true'); ap.add_argument('--execute',action='store_true'); ap.add_argument('--start-index',type=int,default=0); ap.add_argument('--limit',type=int); args=ap.parse_args()
 m=readj(MANIFEST); runs=m['run_order']; index={r['run_id']:r for r in runs}
 if args.run_id:
  if args.run_id not in index: raise SystemExit('unknown frozen run id')
  runs=[index[args.run_id]]
 else:
  runs=runs[args.start_index:args.start_index+args.limit if args.limit else None]
 cases={c['case_id']:c for c in m['cases']}
 if args.execute and not CREDENTIAL.is_file(): raise SystemExit('authentication blocker: credentials.toml missing')
 for run in runs:
  c=cases[run['case_id']]; source=source_for(c).resolve(); p=prompt_path(c)
  if not source.is_dir() or not p.is_file(): raise SystemExit(f'missing frozen inputs for {run["run_id"]}: {source} {p}')
  workspace=PRIVATE/'workspaces'/run['run_id']; out=PRIVATE/'outputs'/run['run_id']
  if args.dry_run:
   print(json.dumps({'run_id':run['run_id'],'case_id':run['case_id'],'model':run['model'],'source':str(source),'prompt':str(p),'duration_cap_seconds':duration(c),'image':'devin-e006:3000.10.21-r7' if c['original_experiment']=='experiment-006' else 'devin-e002:3000.10.21','devin_invoked':False},sort_keys=True)); continue
  if not args.execute: raise SystemExit('choose --dry-run or --execute')
  workspace=stage(c,run); out.mkdir(parents=True,exist_ok=False)
  cmd=docker_cmd(c,run,workspace,out); started=datetime.now(timezone.utc); mono=time.monotonic(); timed=False
  try:
   proc=subprocess.run(cmd,text=True,capture_output=True,timeout=duration(c),check=False); rc=proc.returncode; stdout=proc.stdout or ''; stderr=proc.stderr or ''
  except subprocess.TimeoutExpired as e:
   timed=True; rc=124; stdout=e.stdout.decode() if isinstance(e.stdout,bytes) else (e.stdout or ''); stderr=e.stderr.decode() if isinstance(e.stderr,bytes) else (e.stderr or '')
  ended=datetime.now(timezone.utc)
  (out/'devin.stdout.txt').write_text(stdout); (out/'devin.stderr.txt').write_text(stderr)
  record={'run_id':run['run_id'],'case_id':run['case_id'],'difficulty':run['difficulty'],'model':run['model'],'effort':run['reasoning_effort'],'cli_version':'3000.10.21 (611c1cba)','container_image':'devin-e006:3000.10.21-r7' if c['original_experiment']=='experiment-006' else 'devin-e002:3000.10.21','started_at_utc':started.isoformat(),'ended_at_utc':ended.isoformat(),'wall_time_seconds':time.monotonic()-mono,'returncode':rc,'timed_out':timed,'intervention_count':0,'infrastructure_status':'pending_classification','evaluator_output':None,'workspace':str(workspace),'output_dir':str(out),'command':cmd,'devin_invoked':True}
  (out/'container-run-result.json').write_text(json.dumps(record,indent=2)+'\n')
  print(json.dumps({'run_id':run['run_id'],'returncode':rc,'timed_out':timed,'wall_time_seconds':record['wall_time_seconds']}),flush=True)
  if rc != 0:
   print('Stopping matrix on nonzero Devin/container exit; classify infrastructure before continuing.',file=sys.stderr,flush=True)
   return rc
if __name__=='__main__': main()
