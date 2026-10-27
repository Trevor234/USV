#!/usr/bin/env python3
"""Create a new retrospective, bounded-fixture readiness lock for frozen N10.

Expected identities are historical, derived from immutable run inputs and owned
preparation evidence. This is explicitly not preregistration or stage acceptance.
All source, executable, helper, raw record, effective configuration and bag bytes
are freshly read and locked. The old acceptance template supplies rule names only.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import stat

N10 = Path('/home/trevor/USV/.sgh-research/experiments/p1_execution_architecture_20261005_01/authored_D1_C3_4_20261013_v10')
TEMPLATE = Path('/home/trevor/MPC/scheme_A_prepare_close_20261010_02/independent_readiness/preregister/readiness_v3_contract.json')
MAX_BYTES = 128 * 1024 * 1024
HELPERS = ('lease_replay_v1.py', 'strict_types_v1.py', 'check_owned_fixture.py', 'owned_auth.py',
    'owned_release.py', 'runtime/check_p1_execution.py', 'runtime/check_p1_witness.py',
    'runtime/p1_contract_revision.py', 'validate_readiness_v3.py')
RECORDS = dict(run_inputs='inputs.json', run_result='result.json', preparation='preparation_evidence.json',
    checker_inputs='checker_inputs.json', topics_file='topics.json', expected_witness_header='expected_witness_header.json',
    startup_manifest='publisher/startup_manifest.json', publisher_session='publisher/session_summary.json',
    release='release.json', receipt='publisher/release_receipt.json', observer_source='observer/source.jsonl',
    worker_source='worker/source.jsonl', witness='observer/witness.json', ledger='owned_process_ledger.jsonl',
    native_reader='observer/owned_manifest.json.reader_ready.json',
    native_capability='worker/owned_manifest.json.capability_ready.json',
    recorder_terminal='recorder/terminal.json', synthetic_terminal='synthetic_source/terminal.json',
    transport_source='synthetic_source/transport_source.jsonl', close_tail_ack='close_tail_ack.json',
    gate_observation='publisher/release_observation.json', publication_observation='release_publication_observation.json')


def read(path):
    path = Path(path)
    if not path.is_absolute() or '..' in path.parts:
        raise ValueError('absolute regular path required')
    dfd = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    fd = None
    try:
        for part in path.parts[1:-1]:
            new = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=dfd)
            os.close(dfd); dfd = new
        fd = os.open(path.name, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=dfd)
        first = os.fstat(fd)
        if not stat.S_ISREG(first.st_mode) or first.st_size > MAX_BYTES:
            raise ValueError('nonregular or over byte budget')
        chunks, n = [], 0
        while True:
            part = os.read(fd, 1024 * 1024)
            if not part: break
            chunks.append(part); n += len(part)
            if n > MAX_BYTES: raise ValueError('input grew beyond byte budget')
        identity = lambda x: (x.st_dev, x.st_ino, x.st_mode, x.st_size, x.st_mtime_ns, x.st_ctime_ns)
        if identity(first) != identity(os.fstat(fd)) or identity(first) != identity(os.stat(path.name, dir_fd=dfd, follow_symlinks=False)) or n != first.st_size:
            raise ValueError('input changed during read')
        return b''.join(chunks)
    finally:
        if fd is not None: os.close(fd)
        os.close(dfd)


def pin(path):
    raw = read(path)
    return dict(path=str(path), bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())


def load(path):
    def pairs(items):
        out = {}
        for k, v in items:
            if k in out: raise ValueError('duplicate key')
            out[k] = v
        return out
    return json.loads(read(path), object_pairs_hook=pairs,
        parse_constant=lambda x: (_ for _ in ()).throw(ValueError('nonfinite JSON')))


def create(path, value):
    raw = (json.dumps(value, sort_keys=True, ensure_ascii=False, indent=2, allow_nan=False)+'\n').encode()
    with Path(path).open('xb') as f:
        f.write(raw); f.flush(); os.fsync(f.fileno())


def generate(run, validator):
    run = run.absolute()
    if run != N10 / 'runs/owned_C3_4_positive_01':
        raise ValueError('this retrospective contract identity is only N10 positive_01')
    template = load(TEMPLATE)
    inputs = load(run/'inputs.json'); prep = load(run/'preparation_evidence.json')
    result = load(run/'result.json')
    assert inputs['run_id'] == result['run_id'] == run.name and inputs['mode'] == result['mode'] == 'positive'
    assert result['passed'] is True and result['prepare_budget_ns'] == 25_000_000_000 and result['overall_budget_ns'] == 60_000_000_000
    records = {k: pin(run/v) for k, v in RECORDS.items()}
    records['contract'] = pin(Path(inputs['contract']))
    if records['contract']['sha256'] != inputs['contract_sha256']: raise ValueError('contract differs')
    for role in ('publisher','worker','observer','synthetic_source','recorder'):
        records['owned_'+role] = pin(run/role/'owned_manifest.json')
    helpers = {name: pin(N10/name) for name in HELPERS}
    closure = {}
    def add(path, category, expected_sha=None):
        path = Path(path); info = pin(path)
        if expected_sha and info['sha256'] != expected_sha:
            raise ValueError('historical pin differs: '+str(path))
        key = str(path)
        if key in closure:
            if closure[key]['sha256'] != info['sha256']: raise ValueError('inconsistent repeated pin')
            closure[key]['categories'] = sorted(set(closure[key]['categories']) | {category})
        else:
            closure[key] = dict(info, categories=[category])
    # Historical snapshots bind what ran; current tool versions are a separate
    # frozen identity. A later build-wrapper edit cannot impersonate its snapshot.
    historical_tool_audit = []
    for name, sha in inputs['tool_sha256'].items():
        add(run/(name.replace('/','__')+'.snapshot'), 'runtime_tool_snapshot', sha)
        current = pin(N10/name)
        add(N10/name, 'current_frozen_tool')
        historical_tool_audit.append(dict(tool=name, historical_sha256=sha,
            current_sha256=current['sha256'], current_matches_historical=current['sha256']==sha))
        if current['sha256'] != sha and name != 'build_c34_v10.py':
            raise ValueError('unsupported historical/current helper drift: '+name)
    for role, build in inputs['builds'].items():
        if build['passed'] is not True: raise ValueError('unsuccessful actual role build')
        add(build['binary'], 'actual_role_binary', build['binary_sha256'])
        for item in build.get('native_binaries', {}).values():
            add(item['path'], 'recorded_build_native_binary', item['sha256'])
    for role, item in inputs['source_bundles'].items():
        add(item['path'], 'role_source_bundle', item['sha256'])
        bundle = load(Path(item['path']))
        if bundle['role'] != role or len(bundle['files']) != item['files']: raise ValueError('source role/count differs')
        for source in bundle['files'].values():
            add(source['path'], 'actual_role_source', source['sha256'])
            if pin(Path(source['path']))['bytes'] != source['bytes']: raise ValueError('source byte count differs')
    for p in sorted(run.rglob('*')):
        if p.is_symlink(): raise ValueError('symlink in historical run')
        if p.is_file(): add(p, 'full_historical_run_file')
    for name in ('source_bundles_current.json','build_manifest_current.json'):
        add(N10/name, 'current_frozen_source_build_registry')
    driver = load(run/'release_publication_observation.json')['driver_identity']
    add(driver['exe'], 'historical_driver_interpreter', driver['exe_sha256'])
    add(TEMPLATE, 'rule_template_only')
    add(validator, 'validator_identity')
    add(Path(__file__).absolute(), 'generator_identity')
    add(Path(__file__).absolute().parent/'test_readiness_c35_coherent.py', 'coherent_negative_tool_identity')
    for record in records.values(): add(record['path'], 'used_record_input', record['sha256'])
    for helper in helpers.values(): add(helper['path'], 'sealed_helper', helper['sha256'])
    bag = run/'recorder/bag'
    return dict(schema='p1-C3.5-retrospective-readiness-component-contract/v1',
        created_utc=datetime.now(timezone.utc).isoformat(), fixture_only=True,
        input_origin='fresh read-only lock of frozen N10 owned_C3_4_positive_01; historical expected identities from inputs/preparation, never preregistration',
        template_rule_origin=pin(TEMPLATE), parent_root=str(N10), original_run=str(run),
        validator=pin(validator), sealed_helpers=helpers, record_files=records,
        historical_run_file_population=sorted(str(p.relative_to(run)) for p in run.rglob('*') if p.is_file()),
        bag_files={str(p.relative_to(bag)):pin(p) for p in sorted(bag.rglob('*')) if p.is_file()},
        pin_closure=closure, historical_tool_audit=historical_tool_audit,
        historical_tool_drift_policy='only build_c34_v10.py later wrapper identity is explicitly separate; all actual validation/driver/helper snapshots match current files',
        limits=template['limits'], component_scope=template['component_scope'],
        expected=dict(run_id=run.name, contract_sha256=inputs['contract_sha256'],
            expected_parameters=inputs['expected_parameters'], builds=inputs['builds'],
            source_bundles=inputs['source_bundles'], roles=prep['roles'],
            expected_witness_header=load(run/'expected_witness_header.json'),
            physical_topics=['/wamv/thrusters/left/thrust','/wamv/thrusters/right/thrust'],
            prepare_budget_ns=25_000_000_000, overall_budget_ns=60_000_000_000, close_budget_ns=15_000_000_000),
        required_false=template['required_false'], all_stage_qualifications=False,
        B4_qualified=False, M0b_qualified=False, M4_qualified=False, strict_full_chain_qualified=False,
        execute_qualified=False, research_conclusion=False,
        no_old_shared_v2_identity_claim=True, actual_ROS_nodes_created=False,
        negative_policy='fresh copies with coherent record rehash and selected semantic mutations; historical identity roots and source/binary/helper pins remain independently fixed')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',type=Path,default=N10/'runs/owned_C3_4_positive_01')
    parser.add_argument('--validator',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args(); c=generate(args.run,args.validator.absolute()); create(args.output,c)
    print(json.dumps(dict(contract=str(args.output), closure_files=len(c['pin_closure']), record_files=len(c['record_files']), stage_qualified=False)))
if __name__=='__main__': main()
