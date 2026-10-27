#!/usr/bin/python3
"""Current bounded component report; all stage/research qualifications stay false."""
import argparse
import importlib
import json
from pathlib import Path
import sys
sys.dont_write_bytecode = True
import check_activation_provenance_v1 as C3


def main():
    p = argparse.ArgumentParser(); p.add_argument('--output',type=Path,required=True); a = p.parse_args()
    try:
        c,identity = C3.imports()
        parent = importlib.import_module('consolidate_current_v5')
        if Path(parent.__file__).resolve() != C3.N5/'consolidate_current_v5.py': raise ValueError('wrong pinned parent consolidator')
        prior = parent.analyze(); s = C3.load(); current = C3.analyze(s)
        components = dict(prior['components'])
        components.update({'C3/'+k:v for k,v in current['components'].items()})
        unchanged = all(C3.sha(s['safe'].read_regular(path)) == s['hashes'][key] for key,path in s['paths'].items()) and all(C3.sha(s['safe'].read_regular(Path(s['typed']['root'])/path)) == s['typed']['hashes'][path] for path in s['typed']['paths'])
        for pin in c['record_pins'].values():
            unchanged &= C3.sha(Path(pin['path']).read_bytes()) == pin['sha256']
        report = {'schema':'p1-current-consolidated-components-v6','run_id':current['run_id'],
            'component_suite_passed':prior['component_suite_passed'] and current['passed'] and unchanged,
            'components':components,'component_count':len(components),'parent_components':prior['component_count'],
            'C3_components':len(current['components']),'C3_issues':current['issues'],'original_inputs_unchanged':unchanged,
            'original_authenticity_qualified':True,'storage':prior['storage'],'C3_proofs':current['proofs'],
            'missing_strict_gates':prior['missing_strict_gates'],'C3_remaining_observation_gaps':current['qualification_limits'],
            'strict_readiness_passed':False,'all_original_execution_rules_qualified':False,'shared_v2_identity_recovered':False,
            'general_float_formatter_qualified':False,'DDS_graph_empty_proven':False,
            'reference_numeric_order':'raw frozen -> publisher held-history nominal target -> frozen Job reference126',
            'historical_helper_limit':'v4 helper constructs ref from frozen state; only current original equal-result corpus passed; unchanged historical artifact',
            'scope':'full original fixed-valid offline components, including all 31 Decisions and 22 actual activations; no stage/research conclusion',**C3.FLAGS}
    except Exception as e:
        report = {'schema':'p1-current-consolidated-components-v6','component_suite_passed':False,'load_error':type(e).__name__+': '+str(e),**C3.FLAGS}
    with a.output.open('x') as f: json.dump(report,f,ensure_ascii=False,indent=2,allow_nan=False); f.write('\n')
    print(json.dumps({'component_suite_passed':report['component_suite_passed'],'component_count':report.get('component_count'),'load_error':report.get('load_error'),'C3_issues':report.get('C3_issues')}))
    return 0 if report['component_suite_passed'] else 1


if __name__ == '__main__': raise SystemExit(main())
