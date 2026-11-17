"""Single public entry point; scientific dependencies remain lazy."""
import argparse
import json
from .config import load_config, STAGES
from . import workflow

def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',required=True)
    parser.add_argument('--run-dir')
    commands=parser.add_subparsers(dest='command',required=True)
    for name in ('plan','run'):
        child=commands.add_parser(name);child.add_argument('--target',default='validation')
        if name=='run':child.add_argument('--jobs',type=int,default=1)
    child=commands.add_parser('stage');child.add_argument('name',choices=STAGES)
    commands.add_parser('status')
    args=parser.parse_args(argv)
    try:
        config=load_config(args.config,args.run_dir)
        if args.command=='status':print(json.dumps(workflow.status(config),indent=2));return 0
        if args.command=='plan':
            items=workflow.graph(config,args.target);workflow.validate_run_location(config,items)
            print(json.dumps({'target':args.target,'run_dir':config['run_dir'],'stages':items,'status':workflow.status(config,items)},indent=2,default=str));return 0
        if args.command=='stage':workflow.execute_stage(args.name,config);return 0
        if args.jobs<1:raise ValueError('--jobs must be positive')
        return workflow.run(config,args.target,args.jobs)
    except (ValueError,RuntimeError,OSError,KeyError) as error:
        print('ntuple-analyzer: '+str(error),file=__import__('sys').stderr);return 2
