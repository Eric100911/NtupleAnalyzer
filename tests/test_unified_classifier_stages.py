"""Bounded adapter contracts; no ROOT scans or fit/training jobs."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ntuple_analyzer.adapters.classifier import RESPONSE, stage_spec, execute, _accepted


class ClassifierStages(unittest.TestCase):
    def test_plot_settings_validation_and_partial_override(self):
        from scripts.templates.mass_classifier_observables import resolve_plot_settings
        settings=resolve_plot_settings({'plot_axis_scaling':{'x':'linear','y':'log'},'observables':{'m_jj':{'plot_axis_scaling':{'x':'log'}}}},'m_jj')
        self.assertEqual(settings['plot_axis_scaling'],{'x':'log','y':'log'})
        for cfg in ({'plot_height_per_unit_interval':'true'},{'plot_axis_scaling':{'x':'symlog'}},{'plot_axis_scaling':[]},{'observables':{'m_jj':{'plot_axis_scaling':None}}}):
            with self.assertRaises(ValueError): resolve_plot_settings(cfg,'m_jj')

    def test_external_plot_has_only_saved_json_inputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); (root/'signal_mixture.json').write_text('{}')
            spec=stage_spec('plot',{'plots':{'input_dir':str(root)}},root/'run')
            self.assertEqual(spec['dependencies'],[])
            self.assertEqual(spec['inputs'],[str(root/'signal_mixture.json')])

    def test_response_endpoints_match_implementation(self):
        import numpy as np
        from scripts.templates.bootstrap_classifier_closure import response_bins
        scores=np.eye(6)
        bins=response_bins(scores,RESPONSE['class_order'],'coarse')
        self.assertEqual(bins.tolist(),[2,11,20,27,36,51])
        self.assertEqual(RESPONSE['score_edges'][-1],1.000001)

    def test_partial_process_is_not_accepted(self):
        self.assertFalse(_accepted({'diagnostics':{'reliable':False,'status':0}}))
        self.assertFalse(_accepted({'diagnostics':{'status':0}}))
        self.assertTrue(_accepted({'diagnostics':{'reliable':True}}))

    def test_templates_save_exact_native_matrix(self):
        import numpy as np
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); out=root/'output'; expected=np.full((54,6),1/54)
            model=root/'model.json'; model.write_text('{}')
            bundle={'manifest':{'feature_names':['dr_jj'],'model':str(model)},'pools':{'heldout_template':{}}}
            with patch('scripts.templates.mass_classifier_inputs.load_study',return_value=bundle), patch('scripts.templates.mass_classifier_inputs.response_templates',return_value=(expected,{'covariance':np.zeros((6,54,54))})):
                metadata=execute('templates',{'channel':'JJP','inputs':{'classifier_study':str(root/'frozen')}},root,out)
            with np.load(out/'response_templates.npz') as saved: np.testing.assert_array_equal(saved['templates'],expected)
            self.assertEqual(metadata['status'],'accepted')
            self.assertIn('response_templates.npz',metadata['artifacts'])

    def test_raw_manifest_shared_selector_preserves_identity_and_orders_slots(self):
        import ROOT
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            rdf=ROOT.RDataFrame(2)
            float_vectors={
            'Jpsi_1_mass':[3.05,3.06],'Jpsi_2_mass':[3.15,3.16], 'Phi_mass':[1.02,1.02],
            'Jpsi_1_pt':[7,8], 'Jpsi_2_pt':[10,12], 'Phi_pt':[5,6],
            'Jpsi_1_eta':[0,0],'Jpsi_2_eta':[0,0], 'Phi_eta':[0,0],
            'Jpsi_1_mu_1_Idx':[0,0],'Jpsi_1_mu_2_Idx':[1,1], 'Jpsi_2_mu_1_Idx':[2,2],'Jpsi_2_mu_2_Idx':[3,3],
            'Phi_K_1_pt':[2.5,3],'Phi_K_2_pt':[2.5,3],'Phi_K_1_eta':[0,0],'Phi_K_2_eta':[0,0],
            'muPx':[4,4,4,4],'muPy':[0,0,0,0],'muPz':[0,0,0,0]}
            for obj in ('Jpsi_1','Jpsi_2','Phi'):
             float_vectors[obj+'_px']=float_vectors[obj+'_pt'];float_vectors[obj+'_py']=[0,0];float_vectors[obj+'_pz']=[0,0]
            for name,values in float_vectors.items(): rdf=rdf.Define(name,'ROOT::VecOps::RVec<float>{'+','.join(f'{v}f' if '.' in str(v) else f'{v}.f' for v in values)+'}')
            rdf=rdf.Define('muIsPatSoftMuon','ROOT::VecOps::RVec<int>{1,1,1,1}').Define('run','static_cast<UInt_t>(1)').Define('lumi','static_cast<UInt_t>(2)').Define('event','static_cast<ULong64_t>(100+rdfentry_)')
            rdf.Snapshot('X_data',str(root/'raw.root'))
            import json
            selection={'selection_id':'synthetic-shared-selector','deduplication':'unique run lumi event','candidate_ordering':'descending pT','candidate_index_branch':'bestCandIdx','mass_windows':[[2.9,3.3],[2.9,3.3],[.99,1.07]],'event_identity':['run','lumi','event']}
            (root/'selection.json').write_text(json.dumps(selection));(root/'files.json').write_text(json.dumps({'files':['raw.root']}))
            from ntuple_analyzer.adapters.classifier import execute
            result=execute('select',{'channel':'JJP','inputs':{'raw_data':str(root/'files.json'),'data_selection_manifest':str(root/'selection.json')}},root/'run',root/'out')
            rdf=ROOT.RDataFrame('selected',str(root/'out/selected.root'))
            a=rdf.AsNumpy(['event','bestCandIdx','sel_Jpsi_1_px','sel_Jpsi_2_px','sel_Jpsi_1_mass'])
            self.assertEqual(result['status'],'accepted')
            self.assertEqual(a['event'].tolist(),[100,101])
            self.assertEqual(a['bestCandIdx'].tolist(),[1,1])
            self.assertEqual(a['sel_Jpsi_1_px'].tolist(),[12,12])
            self.assertEqual(a['sel_Jpsi_2_px'].tolist(),[8,8])
            self.assertAlmostEqual(float(a['sel_Jpsi_1_mass'][0]),3.16,places=5)

    def test_raw_input_is_not_selected_table(self):
        from ntuple_analyzer.adapters.classifier import _select
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); manifest=root/'selection.json'
            manifest.write_text(json.dumps({'selection_id':'x','deduplication':'event','candidate_ordering':'pt','candidate_index_branch':'idx','mass_windows':[], 'event_identity':['event']}))
            with self.assertRaisesRegex(ValueError,'schema: legacy_selected'):
                _select({'inputs':{'data_selection_manifest':str(manifest),'selected_data':{'path':str(root/'x.root'),'schema':'X_data'}}},root/'out')

    def test_renderer_dependency_does_not_invalidate_training(self):
        spec=stage_spec('train',{},Path('/tmp/run'))
        self.assertFalse(any(p.endswith('/mass_classifier_observables.py') for p in spec['code']))

    def test_external_study_tracks_source_children(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); study=root/'study'; source=root/'source'; study.mkdir(); (source/'inputs').mkdir(parents=True)
            (source/'inputs/full_features.parquet').touch(); (study/'frozen_input_reference.json').write_text(json.dumps({'study':str(source)}))
            spec=stage_spec('templates',{'inputs':{'classifier_study':str(study)}},root/'run')
            self.assertEqual(spec['dependencies'],['score'])
            self.assertIn(str(source/'inputs/full_features.parquet'),spec['inputs'])


if __name__=='__main__': unittest.main()
