"""Versioned configuration resolution without importing analysis runtimes."""
from pathlib import Path
import copy
import json

SCHEMA = 'ntuple-analyzer-analysis/v1'
STAGES = ('select','features','reweight','train','score','templates','fit','observable-fit','plot','efficiency','acceptance','maps','correct','validation')
PATH_KEYS = {'path','config','bridge','mass_config','observable_mass_config','normalization_config','input_dir','output_dir','raw_root','feature_cache','data','study_dir','input_file_manifest'}

def load_config(path, run_dir=None):
    import yaml
    source = Path(path).resolve()
    raw = yaml.safe_load(source.read_text())
    if not isinstance(raw, dict) or raw.get('schema_version') != SCHEMA:
        raise ValueError('Require schema_version: '+SCHEMA)
    cfg = copy.deepcopy(raw)
    if cfg.get('channel') not in ('JJP','JYP','JJY'):
        raise ValueError('Public channel must be JJP, JYP or JJY')
    def resolve(value, key='', in_inputs=False):
        if isinstance(value, dict):
            return {k:resolve(v,k,key=='inputs') for k,v in value.items()}
        if isinstance(value,list): return [resolve(v,key,in_inputs) for v in value]
        is_path = key in PATH_KEYS or key.endswith(('_manifest','_study','_results','_products','_cache','_root','_dir')) or (in_inputs and key not in {'schema','tree','prefix'})
        if isinstance(value,str) and is_path and '://' not in value:
            return str((source.parent / value).resolve())
        return value
    cfg=resolve(cfg)
    cfg['run_dir']=str(Path(run_dir).resolve() if run_dir else Path(cfg.get('run_dir', source.parent/'runs/default')).resolve())
    cfg['_config_path']=str(source)
    return cfg

def stage_config(config, stage):
    groups = {'select':['selection'], 'features':['classifier'],'reweight':['classifier'],'train':['classifier'], 'score':['classifier'], 'templates':['classifier'], 'fit':['classifier','fit'], 'observable-fit':['classifier','fit'], 'plot':['plots'], 'efficiency':['efficiency'], 'acceptance':['efficiency'], 'maps':['efficiency'], 'correct':['efficiency','correct','fit'], 'validation':['validation']}
    result={k:copy.deepcopy(config[k]) for k in ('schema_version','channel','run_dir') if k in config}
    input_groups={'select':['selected_data','raw_data','data_selection_manifest'],'features':['classifier_feature_cache','classifier_raw_root','classifier_mc_manifest'],'reweight':['classifier_study','phi_target'],'train':[],'score':['classifier_study'],'templates':['classifier_study'],'fit':['classifier_study','selected_data','data_selection_manifest'],'observable-fit':['classifier_study','fit_results'],'plot':['fit_results'],'efficiency':['efficiency_products','efficiency_run_a_manifest','efficiency_run_b_manifest','input_file_manifest'],'acceptance':['efficiency_products'],'maps':['efficiency_products'],'correct':['fit_results','efficiency_products','selected_data'],'validation':[]}
    result['inputs']={k:copy.deepcopy(v) for k,v in config.get('inputs',{}).items() if k in input_groups[stage]}
    for k in groups[stage]:
        if k in config: result[k]=copy.deepcopy(config[k])
    return result

def write_if_changed(path, value):
    path=Path(path)
    text=json.dumps(value,indent=2,sort_keys=True)+'\n'
    if not path.exists() or path.read_text()!=text:
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(text)
