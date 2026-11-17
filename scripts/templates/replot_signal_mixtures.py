#!/usr/bin/env python3
"""Replot saved signal-mixture JSON as differential yields, without refitting."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.templates.mass_classifier_observables import replot_saved_signal_mixture


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input-dir',type=Path,required=True)
    parser.add_argument('--output-dir',type=Path,required=True)
    parser.add_argument('--pattern',default='**/signal_mixture.json',
                        help='Glob relative to input directory; select preferred plots explicitly for report bundles')
    args=parser.parse_args(argv)
    source=args.input_dir.resolve(); output=args.output_dir.resolve()
    if output==source or source in output.parents:
        parser.error('Output must be outside the input tree')
    paths=sorted(source.glob(args.pattern),key=lambda p:(p.parent!=source,p))
    if not paths:
        parser.error('No saved signal-mixture JSON matched')
    if output.exists():
        raise FileExistsError(output)
    plots=[]
    for path in paths:
        relative=path.parent.relative_to(source)
        replot_saved_signal_mixture(path,output/relative)
        plots.append(str(relative/'signal_mixture.png'))
        print('Replotted',relative,flush=True)
    manifest={'source':str(source),'pattern':args.pattern,'count':len(plots),
              'normalization':'differential_yield','refitted':False,'plots':plots}
    (output/'replot_manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    (output/'README.md').write_text(
        '# Differential signal yields\n\n'
        'Points, stacked components and uncertainty bands show yield divided by bin width. '
        'Areas retain the original integrated yields; ratios and fit results are unchanged. '
        'Endpoint bins retain the source overflow-folding policy.\n\n'
        + '\n'.join(f'- [{Path(p).parent}]({p})' for p in plots)+'\n')
    return 0


if __name__=='__main__':
    raise SystemExit(main())
