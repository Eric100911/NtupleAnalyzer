"""Bounded orchestration contracts using a tiny on-disk adapter through real Make."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import sys
from ntuple_analyzer.config import load_config, stage_config, write_if_changed
from ntuple_analyzer import workflow

class FakeAdapter:
    def __init__(self, source): self.source=source
    def stage_spec(self,stage,config,run_dir):
        return {'inputs':[self.source], 'code':[], 'outputs':['child.txt'], 'dependencies':[]}
    def execute(self,stage,config,run_dir,output_dir):
        output_dir.mkdir();(output_dir/'child.txt').write_text('ok')
        return {'status':config.get('fake_status','accepted')}

class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.source=self.root/'source.txt';self.source.write_text('input')
        self.cfg={'schema_version':'ntuple-analyzer-analysis/v1','channel':'JJP','run_dir':str(self.root/'run'),'inputs':{},'classifier':{'seed':1},'plots':{'cms_caption':'Work In Progress'}}
    def tearDown(self):self.tmp.cleanup()
    def test_config_paths_and_channel(self):
        path=self.root/'cfg.json';write_if_changed(path,self.cfg|{'run_dir':'out','inputs':{'selected_data':{'path':'data.root','schema':'legacy_selected'}},'efficiency':{'bridge':'bridge.json'}})
        c=load_config(path);self.assertEqual(c['run_dir'],str(self.root/'out'));self.assertEqual(c['inputs']['selected_data']['schema'],'legacy_selected');self.assertEqual(c['efficiency']['bridge'],str(self.root/'bridge.json'))
        with patch.object(workflow,'adapter',return_value=FakeAdapter(self.source)):
            with self.assertRaisesRegex(ValueError,'JJP only'):workflow.graph(c|{'channel':'JYP'},'train')
    def test_plan_is_readonly(self):
        with patch.object(workflow,'adapter',return_value=FakeAdapter(self.source)):workflow.graph(self.cfg,'plot');workflow.status(self.cfg)
        self.assertFalse(Path(self.cfg['run_dir']).exists())
    def test_publication_rejected_and_deleted_child(self):
        with patch.object(workflow,'adapter',return_value=FakeAdapter(self.source)):
            workflow.execute_stage('fit',self.cfg)
            self.assertIsNotNone(workflow.completion(self.cfg,'fit'))
            (workflow.stage_dir(self.cfg,'fit')/'child.txt').unlink()
            self.assertIsNone(workflow.completion(self.cfg,'fit'))
            with self.assertRaisesRegex(RuntimeError,'rejected'):workflow.execute_stage('fit',self.cfg|{'fake_status':'rejected'})
            self.assertEqual(workflow.status(self.cfg)['fit'],'rejected')
            self.assertTrue(list((Path(self.cfg['run_dir'])/'attempts').glob('fit-failed-*')))
    def test_slices_and_write_preserves_mtime(self):
        altered=copy.deepcopy(self.cfg);altered['plots']['cms_caption']='Changed'
        self.assertEqual(stage_config(self.cfg,'train'),stage_config(altered,'train'))
        self.assertNotEqual(stage_config(self.cfg,'plot'),stage_config(altered,'plot'))
        path=self.root/'json';write_if_changed(path,{'a':1});before=path.stat().st_mtime_ns;write_if_changed(path,{'a':1});self.assertEqual(before,path.stat().st_mtime_ns)
    def test_staleness_and_rejected_prerequisite(self):
        fake=FakeAdapter(self.source)
        with patch.object(workflow,'adapter',return_value=fake):
            workflow.execute_stage('fit',self.cfg)
            self.source.write_text('changed input')
            self.assertEqual(workflow.status(self.cfg)['fit'],'stale')
            original=fake.stage_spec
            def dependent(stage,config,run_dir):
                result=original(stage,config,run_dir)
                if stage=='correct':result['dependencies']=['fit']
                return result
            fake.stage_spec=dependent
            with self.assertRaisesRegex(RuntimeError,'Prerequisite is not accepted'):workflow.execute_stage('correct',self.cfg)
            self.assertFalse((workflow.stage_dir(self.cfg,'correct')/'.complete.json').exists())
    def test_overlap(self):
        with self.assertRaisesRegex(ValueError,'overlaps'):workflow.validate_run_location(self.cfg,{'plot':{'inputs':[self.root]}})
    def test_missing_status_and_mutating_input_rejected(self):
        fake=FakeAdapter(self.source)
        original=fake.execute
        def no_status(*args):original(*args);return {}
        with patch.object(workflow,'adapter',return_value=fake):
            fake.execute=no_status
            with self.assertRaisesRegex(RuntimeError,'status: None'):workflow.execute_stage('fit',self.cfg)
            def mutate(*args):
                result=original(*args);self.source.write_text('modified while running');return result
            fake.execute=mutate
            with self.assertRaisesRegex(RuntimeError,'inputs changed'):workflow.execute_stage('fit',self.cfg)
            self.assertIsNone(workflow.completion(self.cfg,'fit'))
    def test_make_incremental_real_cli(self):
        # A fake adapter module is installed in a separate temporary package copy.
        # The generated Make recipe launches the actual CLI in a new process.
        package=self.root/'repo'/'ntuple_analyzer';package.mkdir(parents=True)
        import shutil
        for source in Path(workflow.__file__).parent.glob('*.py'):shutil.copy(source,package/source.name)
        adapters=package/'adapters';adapters.mkdir();(adapters/'__init__.py').write_text('')
        (adapters/'classifier.py').write_text('from pathlib import Path\ndef stage_spec(stage,config,run_dir):\n return {"inputs":[],"outputs":["child.txt"],"code":[],"dependencies":["fit"] if stage=="plot" else ["train"] if stage=="fit" else []}\ndef execute(stage,config,run_dir,output_dir):\n output_dir.mkdir();(output_dir/"child.txt").write_text("accepted");return {"status":"accepted"}\n')
        config=self.root/'cli.json';write_if_changed(config,self.cfg)
        import os,subprocess
        env=dict(os.environ,PYTHONPATH=str(package.parent)+os.pathsep+os.environ.get('PYTHONPATH',''))
        cmd=[sys.executable,'-m','ntuple_analyzer','--config',str(config),'run','--target','plot']
        one=subprocess.run(cmd,cwd=package.parent,env=env,capture_output=True,text=True);self.assertEqual(one.returncode,0,one.stdout+one.stderr)
        output=workflow.stage_dir(self.cfg,'plot')/'child.txt';before=output.stat().st_mtime_ns
        two=subprocess.run(cmd,cwd=package.parent,env=env,capture_output=True,text=True);self.assertEqual(two.returncode,0,two.stdout+two.stderr);self.assertEqual(before,output.stat().st_mtime_ns)
        trained=workflow.stage_dir(self.cfg,'train')/'child.txt';trained_before=trained.stat().st_mtime_ns
        changed=copy.deepcopy(self.cfg);changed['plots']['cms_caption']='Changed caption';write_if_changed(config,changed)
        styled=subprocess.run(cmd,cwd=package.parent,env=env,capture_output=True,text=True);self.assertEqual(styled.returncode,0,styled.stdout+styled.stderr)
        self.assertEqual(trained_before,trained.stat().st_mtime_ns)
        self.assertNotEqual(before,output.stat().st_mtime_ns)
        fitted=workflow.stage_dir(self.cfg,'fit')/'child.txt';fitted_before=fitted.stat().st_mtime_ns
        settings=[{'plot_height_per_unit_interval':False},
                  {'plot_axis_scaling':{'x':'log','y':'linear'}},
                  {'observables':{'pt_jj':{'plot_axis_scaling':{'x':'log'},'plot_height_per_unit_interval':True}}},
                  {'plot_axis_limits':{'x_min':0.1}},
                  {'plot_axis_scaling':{'x':'log','y':'log'},'plot_axis_limits':{'x_min':0.1,'y_min':0.01}},
                  {'observables':{'pt_jj':{'plot_axis_limits':{'y_min':0.02}}}}]
        for setting in settings:
            previous=output.stat().st_mtime_ns;changed['plots'].update(setting);write_if_changed(config,changed)
            result=subprocess.run(cmd,cwd=package.parent,env=env,capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            self.assertNotEqual(previous,output.stat().st_mtime_ns)
            self.assertEqual(trained_before,trained.stat().st_mtime_ns)
            self.assertEqual(fitted_before,fitted.stat().st_mtime_ns)
        output.unlink();three=subprocess.run(cmd,cwd=package.parent,env=env,capture_output=True,text=True);self.assertEqual(three.returncode,0,three.stdout+three.stderr);self.assertTrue(output.is_file())

if __name__=='__main__':unittest.main()
