"""Make graph construction and transactional stage publication."""
from pathlib import Path
import importlib
import json
import os
import shutil
import subprocess
import sys
import time
import uuid
from .config import STAGES,stage_config,write_if_changed

ALIASES={'training':'train','plots':'plot','correction':'correct'}
DEFAULT_DEPS={'features':[],'select':[],'reweight':['features'],'train':['reweight'],'score':['train'],'templates':['score'],'fit':['templates'],'observable-fit':['fit'],'plot':['observable-fit'],'efficiency':[],'acceptance':['efficiency'],'maps':['acceptance'],'correct':['fit','maps'],'validation':['plot']}

def adapter(stage):
    domain='efficiency' if stage in ('efficiency','acceptance','maps','correct','validation') else 'classifier'
    return importlib.import_module('.adapters.'+domain,__package__)

def stage_dir(config, stage): return Path(config['run_dir'])/'stages'/stage

def spec(stage,config):
    if stage not in STAGES: raise ValueError('Unknown stage: '+stage)
    if config['channel']!='JJP': raise ValueError(stage+' currently supports JJP only; '+config['channel']+' is unsupported')
    value=dict(adapter(stage).stage_spec(stage,config,Path(config['run_dir'])))
    for field in ('inputs','outputs','code'): value.setdefault(field,[])
    for output in value['outputs']:
        path=Path(output)
        if path.is_absolute() or '..' in path.parts: raise ValueError('Stage output must be relative: '+str(output))
    value.setdefault('dependencies',DEFAULT_DEPS[stage])
    return value

def graph(config,target):
    target=ALIASES.get(target,target)
    result={}; visiting=set()
    def visit(stage):
        if stage in visiting: raise ValueError('Cyclic stage graph: '+stage)
        if stage in result:return
        visiting.add(stage); item=spec(stage,config)
        for dep in item['dependencies']: visit(dep)
        visiting.remove(stage); result[stage]=item
    visit(target)
    return result

def source_state(config,stage,item=None):
    item=spec(stage,config) if item is None else item
    paths=list(item['inputs'])+list(item['code'])+[__file__,str(Path(__file__).with_name('config.py'))]
    state={}
    for entry in paths:
        if '://' in str(entry):
            state[str(entry)]='frozen-remote-reference';continue
        path=Path(entry)
        try:
            stat=path.stat();state[str(path)]=[stat.st_mtime_ns,stat.st_size]
        except FileNotFoundError:state[str(path)]=None
    return state

def completion(config,stage):
    path=stage_dir(config,stage)/'.complete.json'
    state=Path(config['run_dir'])/'status'/(stage+'.json')
    if state.exists():
        try:
            if json.loads(state.read_text()).get('status')!='accepted':return None
        except (ValueError,OSError):return None
    if not path.exists():return None
    try:
        value=json.loads(path.read_text())
        if value.get('status')!='accepted':return None
        if value.get('stage')!=stage or not value.get('outputs'):return None
        if not all((path.parent/p).is_file() for p in value.get('outputs',[])):return None
        if value.get('config')!=stage_config(config,stage):return None
        if value.get('sources')!=source_state(config,stage):return None
        for dep in spec(stage,config)['dependencies']:
            previous=completion(config,dep)
            if previous is None:return None
            dep_path=stage_dir(config,dep)/'.complete.json'
            if value.get('dependencies',{}).get(dep)!=dep_path.stat().st_mtime_ns:return None
        return value
    except (ValueError,OSError):return None

def status(config, stages=None):
    out={}
    for stage in stages or STAGES:
        directory=stage_dir(config,stage)
        complete=completion(config,stage)
        state=Path(config['run_dir'])/'status'/(stage+'.json')
        saved=json.loads(state.read_text()).get('status','missing') if state.exists() else 'missing'
        if saved in ('running','failed','partial','rejected'):out[stage]=saved
        elif complete:out[stage]='accepted'
        elif (directory/'.complete.json').exists():out[stage]='stale'
        else:out[stage]=saved
    return out

def validate_run_location(config,items):
    run=Path(config['run_dir']).resolve()
    for item in items.values():
        for entry in item['inputs']:
            if '://' in str(entry):continue
            source=Path(entry).resolve()
            internal=run/'stages' in source.parents
            if not internal and (source==run or source in run.parents or run in source.parents):
                raise ValueError('Run directory overlaps an input tree: '+str(source))

def execute_stage(stage,config):
    item=spec(stage,config);validate_run_location(config,{stage:item})
    missing=[str(p) for p in item['inputs'] if '://' not in str(p) and not Path(p).exists()]
    if missing:raise ValueError('Missing stage inputs: '+', '.join(missing))
    directory=stage_dir(config,stage); directory.parent.mkdir(parents=True,exist_ok=True)
    state=Path(config['run_dir'])/'status'/(stage+'.json')
    for dep in item['dependencies']:
        if not completion(config,dep):raise RuntimeError('Prerequisite is not accepted: '+dep)
    before_sources=source_state(config,stage,item)
    before_dependencies={dep:(stage_dir(config,dep)/'.complete.json').stat().st_mtime_ns for dep in item['dependencies']}
    scratch=directory.parent/('.'+stage+'-'+uuid.uuid4().hex)
    lock=directory.parent/('.'+stage+'.lock')
    try:lock.mkdir()
    except FileExistsError:raise RuntimeError('Stage already running; lock exists: '+str(lock))
    write_if_changed(state,{'status':'running','attempt':str(scratch),'started':time.time()})
    try:
        metadata=adapter(stage).execute(stage,config,Path(config['run_dir']),scratch) or {}
        verdict=metadata.get('status')
        if verdict!='accepted':raise RuntimeError('Stage '+stage+' status: '+str(verdict))
        missing=[p for p in item['outputs'] if not (scratch/p).is_file()]
        if missing:raise RuntimeError('Stage missing outputs: '+', '.join(missing))
        outputs=sorted(str(p.relative_to(scratch)) for p in scratch.rglob('*') if p.is_file())
        if any(p.is_symlink() and scratch.resolve() not in p.resolve().parents for p in scratch.rglob('*')):
            raise ValueError('Stage contains a symlink outside its output directory')
        for artifact in metadata.get('artifacts',[]):
            path=Path(artifact)
            if not path.is_absolute():path=scratch/path
            elif directory in path.parents:path=scratch/path.relative_to(directory)
            if not path.is_file():raise ValueError('Missing claimed artifact: '+str(artifact))
        dependencies={dep:(stage_dir(config,dep)/'.complete.json').stat().st_mtime_ns for dep in item['dependencies']}
        if before_sources!=source_state(config,stage,item) or dependencies!=before_dependencies:
            raise RuntimeError('Stage inputs changed during execution')
        write_if_changed(scratch/'.complete.json',{'status':'accepted','stage':stage,'outputs':outputs,'metadata':metadata,'config':stage_config(config,stage),'sources':source_state(config,stage,item),'dependencies':dependencies})
        if directory.exists():
            if not (directory/'.complete.json').exists():raise FileExistsError('Refusing to replace unmanaged stage '+str(directory))
            archive=Path(config['run_dir'])/'attempts'/(stage+'-previous-'+uuid.uuid4().hex)
            archive.parent.mkdir(parents=True,exist_ok=True);directory.rename(archive)
        scratch.rename(directory)
        write_if_changed(state,{'status':'accepted','output':str(directory)})
        return metadata
    except Exception as error:
        failed=Path(config['run_dir'])/'attempts'/(stage+'-failed-'+uuid.uuid4().hex)
        if scratch.exists():failed.parent.mkdir(parents=True,exist_ok=True);scratch.rename(failed)
        verdict=locals().get('verdict','failed')
        write_if_changed(state,{'status':verdict if verdict in ('partial','rejected','failed') else 'failed','error':str(error),'attempt':str(failed)})
        raise
    finally:
        lock.rmdir()

def make_escape(value):
    value=str(value)
    if any(c in value for c in '\n\r'):raise ValueError('Newlines unsupported in Make paths')
    return value.replace('$','$$').replace('#','\\#').replace(' ','\\ ').replace(':','\\:')

def prepare(config,target):
    items=graph(config,target);validate_run_location(config,items)
    run=Path(config['run_dir']); run.mkdir(parents=True,exist_ok=True)
    write_if_changed(run/'resolved_config.json',config)
    # A per-run launcher stores arguments as JSON: no shell interpolation of user values.
    launcher=run/'invoke_stage.py'
    write_if_changed(run/'invocation.json',{'config':str(run/'resolved_config.json'),'repo':str(Path(__file__).resolve().parents[1])})
    launcher_text="import json, pathlib, sys\np=pathlib.Path(__file__).parent\nx=json.loads((p/'invocation.json').read_text())\nsys.path.insert(0,x['repo'])\nfrom ntuple_analyzer.cli import main\nraise SystemExit(main(['--config',x['config'],'stage',sys.argv[1]]))\n"
    if not launcher.exists() or launcher.read_text()!=launcher_text:launcher.write_text(launcher_text)
    lines=['SHELL := /bin/bash','.SHELLFLAGS := -e -o pipefail -c','.DELETE_ON_ERROR:','.PHONY: target FORCE','FORCE:']
    for name,item in items.items():
        cfg=run/'config'/(name+'.json');write_if_changed(cfg,stage_config(config,name))
        outputs=[stage_dir(config,name)/p for p in item['outputs']]+[stage_dir(config,name)/'.complete.json']
        completed=completion(config,name)
        if completed: outputs += [stage_dir(config,name)/p for p in completed['outputs']]
        outputs=list(dict.fromkeys(outputs))
        deps=[cfg,*map(Path,item['inputs']),*map(Path,item['code']),Path(__file__),Path(__file__).with_name('config.py')]
        deps += [stage_dir(config,d)/'.complete.json' for d in item['dependencies']]
        if not completed:deps.append('FORCE')
        lines.append(' '.join(map(make_escape,outputs))+' &: '+' '.join(map(make_escape,deps)))
        # Only controlled stage names enter a recipe. All paths travel through environment.
        lines.append('\t"$$NTUPLE_PYTHON" "$$NTUPLE_LAUNCHER" '+name)
    target=ALIASES.get(target,target)
    lines.append('target: '+make_escape(stage_dir(config,target)/'.complete.json'))
    path=run/'workflow.mk';text='\n'.join(lines)+'\n'
    if not path.exists() or path.read_text()!=text:path.write_text(text)
    return path

def run(config,target,jobs=1):
    path=prepare(config,target)
    env=dict(os.environ,NTUPLE_PYTHON=sys.executable,NTUPLE_LAUNCHER=str(path.parent/'invoke_stage.py'))
    return subprocess.run(['make','--no-print-directory','-f',str(path),'-j',str(jobs),'target'],env=env).returncode
