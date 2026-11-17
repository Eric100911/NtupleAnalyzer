import tempfile
import unittest
from pathlib import Path
import numpy as np
from scripts.templates.mass_classifier_observables import build_observable_templates,extract_observable_distribution,plot_signal_mixture,observable_inventory,observable_label
from scripts.templates.mass_classifier_normalization import build_mixed_efficiency_maps,compute_cross_sections,synthetic_normalization_config

class AdapterTests(unittest.TestCase):
    def test_physics_axis_labels(self):
        self.assertEqual(observable_label('pt_jjp'),r'$p_T(J/\psi_1+J/\psi_2+\phi)$ [GeV]')
        self.assertIn('eta',observable_label('dr_jj'))
        self.assertNotIn('GeV',observable_label('sumdr2'))
        self.assertNotEqual(observable_label('sumpt_jjp'),observable_label('pt_jjp'))
    def test_nested_thinning_fixture(self):
        cfg=synthetic_normalization_config(seed=7,trials_per_class=3000)
        n,d,e,g=map(np.asarray,(cfg['numerators'],cfg['denominators'],cfg['efficiencies'],cfg['generated_totals']))
        np.testing.assert_array_equal(n[:,:3],d[:,3:])
        np.testing.assert_allclose(n[:,3:].sum(axis=1)/g,e)
        self.assertTrue(np.all(np.abs(e-np.asarray(cfg['expected_efficiencies']))<.035))
        joint=np.zeros((84,84)); joint[:6,:6]=np.eye(6)*10
        joint[6:12,6:12]=cfg['efficiency_covariance']; joint[12:,12:]=cfg['count_covariance']
        joint[6:12,12:]=cfg['efficiency_count_cross_covariance']; joint[12:,6:12]=np.asarray(cfg['efficiency_count_cross_covariance']).T
        result=build_mixed_efficiency_maps(n,d,np.arange(100,700,100),e,generated_totals=g,selection_id=cfg['selection_id'],map_selection_id=cfg['map_selection_id'],joint_covariance=joint)
        self.assertEqual(len(result['efficiency']),6)
        self.assertGreater(np.trace(result['covariance']),0)
    def test_mixing_generated_exposure_and_covariance(self):
        # Physical generated amounts 200 and 100, unequal MC exposures 1000/500.
        n=np.array([[50.,20.],[50.,40.]])
        d=np.array([[100.,100.],[100.,100.]])
        result=build_mixed_efficiency_maps(n,d,[100,25],[.5,.25],generated_totals=[1000,500],selection_id='toy',map_selection_id='toy',class_covariance=[[100,10],[10,25]])
        np.testing.assert_allclose(result['physical_class_weights'],[.2,.2])
        np.testing.assert_allclose(result['efficiency'],[.5,.3])
        self.assertGreater(result['covariance'][1][1],0)
        with self.assertRaises(ValueError):
            build_mixed_efficiency_maps(n,d,[100,25],[.5,.25],generated_totals=[1000,500],selection_id='data',map_selection_id='other')
    def test_crosssection_shared_luminosity_covariance(self):
        r=compute_cross_sections([100,50],[.5,.25],10,[1,1],scope='synthetic inclusive',luminosity_variance=1)
        np.testing.assert_allclose(r['cross_sections'],[20,20])
        np.testing.assert_allclose(r['covariance'],np.full((2,2),4),rtol=1e-7)
        self.assertAlmostEqual(r['total_cross_section'],40.)
        self.assertAlmostEqual(r['total_variance'],16.,places=6)
        self.assertAlmostEqual(r['total_error'],4.,places=6)
        # Perfectly correlated N/epsilon cancels in their ratio: do not drop
        # the selected-yield/efficiency cross block.
        joint=np.zeros((4,4)); joint[:2,:2]=[[100,.5],[.5,.0025]]
        r=compute_cross_sections([100],[.5],10,[1],scope='synthetic inclusive',joint_covariance=joint)
        self.assertLess(abs(r['covariance'][0][0]),1e-12)
    def test_mass_extraction_and_template_normalization(self):
        values=np.array([0.,.2,.8,1.]); edges=[0,.5,1]
        seen={}
        def fitter(masses,categories,n_categories,**kwargs):
            seen.update(kwargs)
            np.testing.assert_array_equal(categories,[0,0,1,1])
            return {'signal_yields':[2,2],'signal_covariance':[[2,.5],[.5,2]]}
        extraction=extract_observable_distribution(values,edges,masses=np.ones((4,3)),fit_function=fitter)
        self.assertIsNone(seen['response_templates'])
        self.assertEqual(extraction['signal_covariance'][0][1],.5)
        t,c=build_observable_templates([values]*6,edges)
        np.testing.assert_allclose(t.sum(axis=0),1)
        np.testing.assert_allclose(c.sum(axis=1),0,atol=1e-12)
        self.assertEqual(len(observable_inventory()['features']),21)
        with self.assertRaises(ValueError): extract_observable_distribution([-.1],edges,pure_signal=True)
        with tempfile.TemporaryDirectory() as temp:
            out=plot_signal_mixture(Path(temp)/'plots',extraction,np.ones(6),np.eye(6),t,template_covariance=c)
            self.assertTrue(Path(out['artifacts'][0]).is_file())
            self.assertFalse(out['significance_available'])
            self.assertIsNone(out['residual_covariance'])
            extraction['fit']['diagnostics']={'reliable':False}
            with self.assertRaises(ValueError):
                plot_signal_mixture(Path(temp)/'invalid',extraction,np.ones(6),np.eye(6),t)
if __name__=='__main__': unittest.main()
