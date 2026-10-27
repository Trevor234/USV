#!/usr/bin/env python3
"""Read-only source, generated-spec, corpus and compiler-input audit."""
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

sys.dont_write_bytecode=True
D=Path(__file__).resolve().parent.parent
I=D/'implementation'
W=D.parent


def pin(p):
    p=Path(p);data=p.read_bytes();return {'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}


def main():
    inputs={}
    def capture(p,expected=None):
        p=Path(p);value=pin(p)
        if expected is not None:
            assert all(value[k]==expected[k] for k in ['bytes','sha256'] if k in expected),str(p)
        if str(p) in inputs:assert inputs[str(p)]==value
        inputs[str(p)]=value;return p.read_bytes()
    def read(p):return json.loads(capture(p))
    source=read(D/'preflight/current_source_capture_v1.json')
    for path,expected in source['input_sha256'].items():capture(path,expected)
    spec=read(I/'current_contract_spec_v1.json')
    assert pin(I/'current_contract_spec_v1.json')['sha256']=='317ec56f9c1211b9d8adc5dc727e2a20c1f281afd2047efafecbac797c46d798'
    assert len(spec['legacy_baseline'])==81 and len(spec['legacy_baseline']['hydro'])==19
    assert len(spec['integer_keys'])==39 and not spec['physical_execute_release_enabled']
    assert json.loads(capture(I/'current_diag_contract_v1.json'))==spec['legacy_baseline']
    pre=json.loads(capture(I/'current_pre_freeze_contract_v1.json'));assert len(pre)==84
    generated=read(D/'evidence/generated_contract_artifacts_v1.json')
    for path,expected in generated['generated'].items():capture(path,expected)
    # The only textual C++ differences are sorted initializer presentation for
    # two std::set values; all validation logic and current values stay exact.
    def normalized_cpp(raw):
        text=raw.decode()
        def sort_set(match):
            names=re.findall(r'"([^"]+)"',match.group(1))
            return 'static const std::set<std::string> fields = {'+','.join(json.dumps(k) for k in sorted(names))+'}'
        return re.sub(r'static const std::set<std::string> fields = \{([^}]*)\}',sort_set,text)
    original=W/'scheme_A_owned_business_start_20261020_39/author/observer/src/shadow/p1_full_contract.hpp'
    assert normalized_cpp(capture(original))==normalized_cpp(capture(I/'native/p1_full_contract.hpp'))
    worker=W/'scheme_A_V2_watchdog_lease_20261019_35/worker_author/worker/p1_full_contract.hpp'
    assert capture(worker)==capture(original)
    reports=[]
    for rel,count in [('verification/contract_parity_v2.json',385),
                      ('verification/formal_prepare_cases_v1.json',102),
                      ('verification/formal_contract_entry_v1.json',25)]:
        report=read(D/rel);assert report['passed'] and report['case_count']==count
        assert report['input_sha256_before']==report['input_sha256_after']
        for path,expected in report['input_sha256_before'].items():capture(path,expected)
        reports.append(report)
    parity,replay,entry=reports
    assert parity['expected_accept_count']==38 and parity['expected_reject_count']==347
    assert replay['seeded_component_only'] and not replay['live_owned_endpoint_authentication_proven']
    assert not entry['owned_ROS_runtime']
    raw_manifest=read(D/'verification/corpus_manifest_v2.json')
    assert len(raw_manifest['cases'])==385
    native=[json.loads(line) for line in capture(D/'verification/native_parity_stdout_v2.jsonl').splitlines()]
    assert len(native)==385
    assert [r['accepted'] for r in native]==[r['expected'] for r in raw_manifest['cases']]
    assert capture(D/'verification/native_parity_stderr_v2.log')==b''
    assert capture(D/'verification/formal_prepare_stderr_v1.log')==b''
    first=read(D/'evidence/parity_attempt01_failure_v1.json')
    assert not first['passed'] and first['returned_results']==378 and first['next_case']=='raw_invalid_utf8'
    for path,expected in first['files'].items():capture(path,expected)
    builds=[]
    for name in ['contract_probe_attempt01','contract_probe_attempt02','formal_prepare_attempt01']:
        build=read(D/'build'/name/'build_manifest_v1.json');assert build['returncode']==0 and not build['ROS']
        for field in ['compiler','source','binary']:capture(build[field]['path'],build[field])
        for field in ['dependencies','runtime_libraries']:
            for path,row in build[field].items():capture(path,row)
        builds.append(build)
    # Reproduce all five outputs in a new ephemeral directory; compare bytes,
    # not just the generator's own claims. No frozen file is overwritten.
    templates={p.name:capture(p) for p in sorted((I/'templates').iterdir())}
    generator=capture(I/'generate_contract_v1.py')
    with tempfile.TemporaryDirectory(prefix='usv_B544_reproduction_') as temp:
        root=Path(temp);impl=root/'implementation'
        for rel in ['templates','native','python']:(impl/rel).mkdir(parents=True,exist_ok=True)
        (root/'evidence').mkdir()
        for name,raw in templates.items():(impl/'templates'/name).write_bytes(raw)
        (impl/'current_contract_spec_v1.json').write_bytes(capture(I/'current_contract_spec_v1.json'))
        (impl/'generate_contract_v1.py').write_bytes(generator)
        result=subprocess.run([sys.executable,'-B',str(impl/'generate_contract_v1.py')],capture_output=True,timeout=10)
        assert result.returncode==0,(result.stdout,result.stderr)
        repro=[]
        for path in generated['generated']:
            rel=Path(path).relative_to(I);assert (impl/rel).read_bytes()==capture(I/rel);repro.append(str(rel))
    static={
      'legacy_task_time_entry':W/'scheme_A_owned_business_start_20261020_39/author/observer/src/shadow/task_time_entry_contract_v1.hpp',
      'legacy_business_gate':W/'scheme_A_owned_business_start_20261020_39/author/common/business_start_gate_v1.hpp',
      'current_worker':W/'scheme_A_V2_watchdog_lease_20261019_35/worker_author/worker/solver_worker.cpp',
      'worker_disabled_fault_policy':W/'scheme_A_V2_watchdog_lease_20261019_35/worker_author/worker/v2_diagnostic_block.hpp',
      'current_fixture':W/'scheme_A_longitudinal_20261016_19/author_snapshot/fixture/synthetic_source.cpp',
      'current_recorder':W/'p1_execution_architecture_20261005_01/authored_D1_C3_4_20261013_v10/recorder/src/owned_recorder.cpp'}
    role_sources={k:{'path':str(p),**pin(p)} for k,p in static.items()}
    for p in static.values():capture(p)
    assert 'only explicitly declared shadow' not in capture(static['legacy_task_time_entry']).decode() # delegated guard
    assert 'require_shadow_mode(mode)' in capture(static['legacy_task_time_entry']).decode()
    assert '"shadow"&&witnessed&&fault_enabled' in capture(static['legacy_business_gate']).decode()
    assert '"/research/control/applied"' in capture(static['current_fixture']).decode()
    for p in [I/'python/formal_prepare_contract.py',I/'native/formal_prepare_gate_v1.hpp',
              D/'implementation/owned_no_output_integration_plan_v1.json',
              D/'preflight/theory_review_decision_v1.json',Path(__file__).resolve()]:capture(p)
    after={p:pin(p) for p in inputs}
    assert inputs==after
    report={'schema':'B5-contract-component-evidence-audit/v1','passed':True,
      'spec_recovered_exact_existing_Native_SHA256':True,'Native_rules_semantically_unchanged':True,
      'generator_reproduced_outputs':repro,'contract_parity_cases':385,'prepare_core_cases':102,
      'actual_file_entry_cases':25,'failed_probe_attempt01_preserved':True,
      'source_static_role_review':role_sources,'source_evidence_inputs':len(inputs),
      'input_sha256_before':inputs,'input_sha256_after':after,
      'new_ROS_processes':0,'existing_five_role_ELFs_changed':False,
      'live_owned_formal_no_output_entry_proven':False,'B5_formal_freeze_qualified':False,
      'stage_qualified':False,'execute_qualified':False,'research_conclusion':False}
    with (D/'postrun/component_evidence_audit_v1.json').open('x') as f:json.dump(report,f,ensure_ascii=False,indent=2,sort_keys=True);f.write('\n')
    print(json.dumps({'passed':True,'input_pins':len(inputs),'same_spec_SHA256':True,'outputs_reproduced':len(repro)}))


if __name__=='__main__':main()
