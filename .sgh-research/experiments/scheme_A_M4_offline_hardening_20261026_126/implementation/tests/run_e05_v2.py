#!/usr/bin/env python3
"""Complete E05's real wiring and authoritative credentials; finite native tests only."""
from pathlib import Path
import json
import re
import shlex
import shutil
import sys
from offline_support import Evidence, ROOT, pin, save

output = sys.argv[1]
e = Evidence('E05', output)
shadow = ROOT / 'implementation/author/observer/src/shadow'
header = shadow / 'scoped_epoch_v1.hpp'
test = ROOT / 'implementation/tests/test_scoped_epoch_v3.cpp'
frozen = shadow / 'task_time_profile_v1.hpp'
before = pin(frozen)
cases = ['EPV-E1', 'EPV-E2', 'EPV-E3', 'EPV-E4', 'EPV-E5', 'EPV-E6',
         'EPV-REPLAY-A', 'EPV-DUP-COMMIT', 'EPV-G5-RETRY', 'EPV-RETIRED-BINDING-V3',
         'EPV-LEGAL-NEW-SCHEDULE', 'EPV-RETIRED-LEDGER', 'EPV-FOREIGN', 'EPV-SERIAL', 'EPV-SNAPSHOT']
mutations = {
    'generation': ('    if (s.token.wrapper_generation != generation_) return "proposal_stale_generation";\n',
                   'EPV-REPLAY-A', 'e7_stale_generation_replay_rejected'),
    'foreign': ('    if (s.token.instance_id != instance_id_) return "proposal_foreign_instance";\n',
                'EPV-FOREIGN', 'foreign_instance_rejected'),
    'serial': ('    if (!s.token.serial || s.token.serial != serial_) return "proposal_unissued_or_superseded";\n',
               'EPV-SERIAL', 'unissued_serial_rejected'),
    'ledger': (None, 'EPV-RETIRED-LEDGER', 'e12_refusal_is_the_retired_ledger_reason'),
}
save(e.out / 'registration.json', {'cases': cases, 'mutations': mutations,
     'harness': pin(test), 'header': pin(header), 'case_timeout_seconds': 60, 'auto_retry': 0,
     'note': 'V3 binding case has a new ID because its assertions changed; original six preserve their 32 assertions.'})
inc = Path('/home/trevor/USV/usv_mpc_ws/install/usv_mpc_cpp/include')
lib = inc.parent / 'lib'


def compile_case(directory, name):
    binary = e.out / name
    r = e.command('build_' + name, ['g++', '-std=c++17', '-O2', '-I', directory, '-I', inc,
                  '-I', '/usr/include/eigen3', test, '-L', lib, '-lmpc_core_lib', '-pthread', '-o', binary])
    e.check('build.' + name, r.returncode == 0)
    return binary if r.returncode == 0 else None


def run_case(binary, case, directory):
    r = e.command(case, [binary, case, directory], timeout=60)
    record = directory / 'result.json'
    d = json.loads(record.read_text()) if record.is_file() else {}
    return r, d


binary = compile_case(shadow, 'epoch')
verdicts = []
if binary:
    for case in cases:
        r, d = run_case(binary, case, e.out / 'runs' / case)
        ok = r.returncode == 0 and d.get('passed') is True and bool(d.get('assertions')) and all(x['passed'] is True for x in d['assertions'])
        e.check(case, ok)
        verdicts.append({'case': case, 'result': d})
    total = sum(len(v['result']['assertions']) for v in verdicts[:6])
    e.check('original_six_32_assertions', total == 32, total)

for name, (old, case, assertion) in mutations.items():
    private = e.out / 'mutations' / name
    private.mkdir(parents=True)
    for source in shadow.iterdir():
        if source.is_file():
            shutil.copy2(source, private / source.name)
    text = header.read_text()
    if name == 'ledger':
        found = re.search(r'    for \(const auto &record : ledger_\)\n      if \(record.anchor && record.anchor->binding == binding\) \{\n        info.blocked_reason = "scoped_open_binding_retired"; return info;\n      \}\n', text)
        old = found.group() if found else None
    prepared = old is not None and text.count(old) == 1
    e.check('mutation.prepared.' + name, prepared)
    if not prepared:
        continue
    (private / header.name).write_text(text.replace(old, '    // targeted guard removed\n'))
    mutant = compile_case(private, 'mut_' + name)
    if mutant:
        r, d = run_case(mutant, case, private / 'run')
        failed = [x['name'] for x in d.get('assertions', []) if x['passed'] is False]
        e.check('mutation.caught.' + name, r.returncode == 2 and d.get('passed') is False and assertion in failed, failed)

# Reuse only the include/define recipe, redirect every author path to the new tree.
base = ROOT.parent / 'scheme_A_M4_rnw_s4_owned_20261025_119'
flags_path = base / 'build/cmake/CMakeFiles/p1_m4_regulator_owned.dir/flags.make'
flags = flags_path.read_text()
includes = shlex.split(re.search(r'^CXX_INCLUDES = (.*)$', flags, re.M).group(1))
includes = [str(ROOT / 'implementation/author') + x.split('/implementation/t2_author', 1)[1]
            if x.startswith(str(base / 'implementation/t2_author')) else
            x.replace(str(base / 'implementation/t2_author'), str(ROOT / 'implementation/author')) for x in includes]
defines = ['-DP1_DRIVER_TOOL_SHA256="offline-compile-only"', '-DP1_OWNED_SOURCE_BUNDLE_SHA256="offline-compile-only"']
r = e.command('regulator_actual_compile', ['g++', '-std=c++17', '-O0', *defines, *includes,
              '-c', shadow / 'regulator_owned_execute.cpp', '-o', e.out / 'regulator.o'], timeout=600)
e.check('actual_regulator_compiles_with_only_credential_commit', r.returncode == 0)
source = (shadow / 'regulator_owned_execute.cpp').read_text()
e.check('actual_call_uses_captured_identity_and_token',
        'reference_snapshot=reference_epoch_.snapshot_identity()' in source
        and 'mint(std::move(task_reference),reference_snapshot)' in source
        and 'commit(authenticated_reference,j.job_id,submit_commit_ns)' in source
        and 'commit(task_reference,j.job_id,submit_commit_ns)' not in source)
e.check('frozen_epoch_unchanged', pin(frozen) == before)
save(e.out / 'case_results.json', verdicts)
result = e.finish(header_pin=pin(header), test_pin=pin(test), flags_pin=pin(flags_path),
                  actual_call_site_compile_only=True, actual_owned_runtime=False)
sys.exit(0 if result['status'] == 'PASS' else 2)
