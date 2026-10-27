#!/usr/bin/env python3
"""Rebuild the actual entry suite alongside a reverted Worker in a private copy."""
from pathlib import Path
import hashlib
import json
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'evidence/reviewed_input_snapshot/implementation/w2_author/worker'
OUT = ROOT / 'evidence/entry_coverage_probe'
OUT.mkdir(exist_ok=False)
worker = (SOURCE / 'solver_worker_m4.cpp').read_text()
before = worker
names = ['w2_release_fd', 'w2_release_job_id', 'w2_release_ordinal',
         'w2_release_nonce', 'w2_release_wait_ns']
match = re.search(r'formal_owned::overrides\(\*this,\{[^\n]+\}\);', worker)
assert match
whitelist = match.group(0)
for name in names:
    assert ',"' + name + '"' in whitelist
    whitelist = whitelist.replace(',"' + name + '"', '')
worker = worker[:match.start()] + whitelist + worker[match.end():]
assert 'if(flags<0||(flags&O_ACCMODE)!=O_RDONLY)' in worker
worker = worker.replace('if(flags<0||(flags&O_ACCMODE)!=O_RDONLY)',
                        'if((st.st_mode&O_ACCMODE)!=O_RDONLY)')
(OUT / 'solver_worker_m4.cpp').write_text(worker)
test = OUT / 'test_w2_entry_contract.cpp'
test.write_bytes((SOURCE / test.name).read_bytes())
binary = OUT / 'test_w2_entry_contract'
argv = ['/usr/bin/c++', '-std=c++17', '-O2', str(test), '-lgtest', '-pthread', '-o', str(binary)]
built = subprocess.run(argv, capture_output=True, text=True, timeout=60)
(OUT / 'compile.stdout.txt').write_text(built.stdout)
(OUT / 'compile.stderr.txt').write_text(built.stderr)
assert built.returncode == 0, built.stderr
run = subprocess.run([str(binary)], capture_output=True, text=True, timeout=30)
(OUT / 'run.stdout.txt').write_text(run.stdout)
(OUT / 'run.stderr.txt').write_text(run.stderr)
assert run.returncode == 0 and '[  PASSED  ] 4 tests.' in run.stdout
dependency_argv = ['/usr/bin/c++', '-std=c++17', '-MM', str(test)]
dependencies = subprocess.check_output(dependency_argv, text=True)
(OUT / 'test_dependencies.txt').write_text(dependencies)
result = {
    'schema': 'W2-entry-test-source-dependency-blind-spot-v1',
    'private_worker_mutations': ['remove all five W2 override names', 'restore wrong st_mode access-direction predicate'],
    'test_source_unchanged': True,
    'worker_before_sha256': hashlib.sha256(before.encode()).hexdigest(),
    'worker_mutant_sha256': hashlib.sha256(worker.encode()).hexdigest(),
    'compile_argv': argv, 'compile_returncode': built.returncode,
    'run_argv': [str(binary)], 'run_returncode': run.returncode,
    'passed_tests': 4, 'mutant_rejected': False,
    'dependencies_argv': dependency_argv,
    'test_depends_on_worker_source': 'solver_worker_m4.cpp' in dependencies,
    'scope': 'The entry suite is freshly compiled; it does not compile/include/launch the adjacent Worker, which is the demonstrated coverage gap',
}
(OUT / 'verification_v1.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
print(json.dumps(result, ensure_ascii=False))
