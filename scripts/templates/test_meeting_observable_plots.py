"""Meeting projections preserve frozen common normalization and declared grids."""
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path
import numpy as np
from scripts.templates.mass_classifier_observables import COMPONENT_COLORS, plot_signal_mixture, replot_saved_signal_mixture
from scripts.templates.prepare_meeting_observable_plots import choose_binning


class MeetingPlotsTest(unittest.TestCase):
    def test_independent_axis_and_height_settings_preserve_integrated_inputs(self):
        import matplotlib.pyplot as plt
        from scripts.templates.mass_classifier_observables import resolve_plot_settings
        cfg={'plot_height_per_unit_interval':True,'plot_axis_scaling':{'x':'linear','y':'log'},
             'observables':{'pt_jj':{'plot_axis_scaling':{'x':'log'},'plot_height_per_unit_interval':False}}}
        settings=resolve_plot_settings(cfg,'pt_jj')
        self.assertEqual(settings,{'plot_height_per_unit_interval':False,'plot_axis_scaling':{'x':'log','y':'log'},'plot_axis_limits':{}})
        n=np.ones(6)*20; t=np.array([[.25]*6,[.75]*6]); v=np.eye(6)
        extraction={'edges':[1,2,6],'signal_yields':[30,90],'signal_covariance':[[4,1],[1,9]]}
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'source'
            original=plot_signal_mixture(source,extraction,n,v,t,observable='pt_jj')
            for density in (True,False):
                with patch('matplotlib.pyplot.close'):
                    r=replot_saved_signal_mixture(source/'signal_mixture.json',Path(tmp)/str(density),
                        plot_height_per_unit_interval=density,plot_axis_scaling={'x':'log','y':'log'},plot_axis_limits={'y_min':.1})
                    fig=plt.gcf(); ax,ratio=fig.axes; scale=np.array([1,4]) if density else np.ones(2)
                    self.assertEqual(ax.get_xscale(),'log'); self.assertEqual(ratio.get_xscale(),'log');self.assertEqual(ax.get_yscale(),'log')
                    np.testing.assert_allclose([p.get_height() for p in ax.patches[:2]],t[:,0]*n[0]/scale)
                    np.testing.assert_allclose(ax.containers[-1].lines[0].get_ydata(),np.array([30,90])/scale)
                    np.testing.assert_allclose(r['displayed_height']['signal_covariance'],np.array(extraction['signal_covariance'])/(scale[:,None]*scale[None,:]))
                    np.testing.assert_allclose(r['displayed_height']['signal_errors'],np.array([[2,3],[2,3]])/scale)
                    for key in ('signal_yields','signal_covariance','prediction','prediction_covariance','components','signal_errors'):
                        self.assertEqual(r[key],original[key])
                plt.close(fig)

    def test_display_limits_zero_edge_log_errors_and_explicit_upper_limits(self):
        import matplotlib.pyplot as plt
        n=np.ones(6)*20;t=np.full((3,6),1/3)
        extraction={'edges':[0,1,3,6],'signal_yields':[2,0,-2],
                    'signal_covariance':np.diag([16,4,9]),
                    'signal_upper_limits':[None,None,{'value':9,'confidence_level':.95,'method':'external profile'}]}
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'source'; original=plot_signal_mixture(source,extraction,n,np.eye(6),t,observable='pt_jj')
            with patch('matplotlib.pyplot.close'):
                r=replot_saved_signal_mixture(source/'signal_mixture.json',Path(tmp)/'log',plot_axis_scaling={'x':'log','y':'log'},plot_axis_limits={'x_min':.1,'x_max':5,'y_min':1})
                fig=plt.gcf();ax,ratio=fig.axes
                self.assertEqual(ax.get_xlim(),(.1,5));self.assertEqual(ratio.get_xlim(),(.1,5));self.assertEqual(ratio.get_yscale(),'linear')
                np.testing.assert_allclose(ax.containers[-1].lines[0].get_ydata(),[2])
                self.assertEqual(sum(getattr(text,'arrow_patch',None) is not None for text in ax.texts),1)  # only explicitly supplied upper limit arrow
                segments=ax.collections[0].get_segments()
                np.testing.assert_allclose(segments[0],[[.5,1],[.5,6]])
                self.assertEqual(len(ax.containers[-1].lines[1]),0) # no fabricated lower cap
                self.assertEqual(r['signal_upper_limits'],extraction['signal_upper_limits'])
                self.assertEqual(r['edges'],[0,1,3,6]);self.assertEqual(r['bin_widths'],[1,2,3])
                np.testing.assert_allclose(r['displayed_height']['signal_covariance'],np.diag([16,1,1]))
                for key in ('signal_yields','signal_covariance','components','prediction'):
                    self.assertEqual(r[key],original[key])
            plt.close(fig)

    def test_limit_inheritance_and_invalid_log_limits(self):
        from scripts.templates.mass_classifier_observables import resolve_plot_settings,validate_plot_axes
        settings=resolve_plot_settings({'plot_axis_limits':{'x_min':.1,'x_max':100,'y_min':1},'observables':{'x':{'plot_axis_limits':{'x_max':20}}}},'x')
        self.assertEqual(settings['plot_axis_limits'],{'x_min':.1,'x_max':20,'y_min':1})
        for limits in ({'x_min':3,'x_max':2},{'xmin':1},{'y_min':float('inf')}):
            with self.assertRaises(ValueError): resolve_plot_settings({'plot_axis_limits':limits},'x')
        result={'edges':[0,1],'signal_yields':[1],'prediction':[2],'components':[[1]*6],'signal_covariance':[[1]],'prediction_covariance':[[1]]}
        for upper in ([{'value':2,'confidence_level':1}], [{'value':-1,'confidence_level':.95}]):
            with self.assertRaises(ValueError): validate_plot_axes(dict(result,signal_upper_limits=upper),resolve_plot_settings({},'x'))
        with self.assertRaisesRegex(ValueError,'positive y_min'):
            validate_plot_axes(result,resolve_plot_settings({'plot_axis_scaling':{'y':'log'}},'x'))

    def test_log_edges_refused_before_output_creation(self):
        n=np.ones(6)*20;t=np.array([[.5]*6,[.5]*6])
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'source'; output=Path(tmp)/'bad'
            plot_signal_mixture(source,{'edges':[0,1,3],'signal_yields':[20,30],'signal_covariance':np.eye(2)},n,np.eye(6),t)
            with self.assertRaisesRegex(ValueError,'zero first edge'):
                replot_saved_signal_mixture(source/'signal_mixture.json',output,plot_axis_scaling={'x':'log'})
            self.assertFalse(output.exists())

    def test_palette_has_six_distinct_non_gray_components(self):
        self.assertEqual(len(set(COMPONENT_COLORS)),6)
        for color in COMPONENT_COLORS:
            rgb=[int(color[i:i+2],16) for i in (1,3,5)]
            self.assertGreater(max(rgb)-min(rgb),20)

    def test_bin_selection_uses_only_counts_and_template_ess(self):
        x=np.tile(np.linspace(0,1,1000),6)
        labels=np.repeat(np.arange(6),1000); weights=np.ones(len(x))
        edges,status=choose_binning(x,x,labels,weights,[0,.25,.5,.75,1])
        self.assertEqual(len(edges)-1,10)
        self.assertFalse(status['uses_mass_fit_or_residuals'])
        self.assertEqual((edges[0],edges[-1]),(0,1))
        edges,status=choose_binning(x,[.5],labels,weights,[0,.25,.5,.75,1])
        self.assertEqual(len(edges)-1,4)
        self.assertTrue(all(not c['pass'] for c in status['candidates']))

    def test_same_six_yields_are_reused_without_projection_normalization(self):
        n=np.arange(1,7.)*10; v=np.diag(n)
        t=np.array([[.25]*6,[.75]*6])
        extraction={'edges':[0,1,2],'signal_yields':[12,22],
                    'signal_covariance':[[12,1],[1,22]]}
        with tempfile.TemporaryDirectory() as tmp:
            r=plot_signal_mixture(Path(tmp)/'plot',extraction,n,v,t)
        np.testing.assert_allclose(np.array(r['components']).sum(axis=0),n)
        self.assertEqual(sum(r['prediction']),sum(n))
        self.assertNotEqual(sum(r['prediction']),sum(r['signal_yields']))
        np.testing.assert_allclose(r['prediction_covariance'],t@v@t.T)

    def test_variable_width_differential_yields_preserve_areas_and_covariance(self):
        import matplotlib.pyplot as plt
        n=np.arange(1,7.)*10; v=np.diag(n)
        t=np.array([[.25]*6,[.75]*6])
        widths=np.array([.5,2.])
        vy=np.array([[12.,3.],[3.,22.]])
        extraction={'edges':[0,.5,2.5],'signal_yields':[12,22],
                    'signal_covariance':vy,'fit':{'diagnostics':{'empty_categories':[1]}}}
        with tempfile.TemporaryDirectory() as tmp:
            # Inspect actual artists as well as the portable density covariance.
            with patch('matplotlib.pyplot.close'):
                r=plot_signal_mixture(Path(tmp)/'plot',extraction,n,v,t,observable='pt_jj',
                    cross_covariance=np.eye(2),profile_intervals=[[9,17],[18,28]])
                fig=plt.gcf(); ax,ratio=fig.axes
                np.testing.assert_allclose([p.get_height() for p in ax.patches[:2]],t[:,0]*n[0]/widths)
                np.testing.assert_allclose(ax.containers[-1].lines[0].get_ydata(),[24.])
                np.testing.assert_allclose(ratio.containers[0].lines[0].get_ydata(),[12/r['prediction'][0]])
            plt.close(fig)
            density=r['differential_yield']
            np.testing.assert_allclose(np.array(density['components']).T@widths,n)
            np.testing.assert_allclose(np.array(density['signal'])*widths,[12,22])
            scale=widths[:,None]*widths[None,:]
            np.testing.assert_allclose(density['signal_covariance'],vy/scale)
            np.testing.assert_allclose(density['prediction_covariance'],(t@v@t.T)/scale)
            np.testing.assert_allclose(density['residual_covariance'],(vy+t@v@t.T-2*np.eye(2))/scale)
            np.testing.assert_allclose(density['signal_errors'],np.array([[3,4],[5,6]])/widths)
            self.assertEqual(r['y_axis_label'],'Signal yield / GeV')
            replay=replot_saved_signal_mixture(Path(tmp)/'plot/signal_mixture.json',Path(tmp)/'replay')
            for key in ('signal_yields','prediction','signal_covariance','prediction_covariance',
                        'components','signal_errors','masked_signal_bins','differential_yield'):
                self.assertEqual(replay[key],r[key])


if __name__=='__main__': unittest.main()
