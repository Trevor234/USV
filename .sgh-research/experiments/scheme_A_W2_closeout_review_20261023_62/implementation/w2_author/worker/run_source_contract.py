#!/usr/bin/env python3
"""Source-level wiring assertions the compiled suites cannot make.

Two 62-review findings are about *composition*, not behaviour a unit test sees:
the Worker's strict whitelist must actually merge the helper's name set, and the
RawBackend must actually call the final guard. A compiled test exercises the
helper directly, so deleting the merge (or the guard call) leaves it green —
which is exactly the 62/E5 blind spot.

These checks read the production source and assert the call is present, so a
later refactor that drops it fails here.
"""
from __future__ import annotations

import json
from pathlib import Path
import re
import sys

sys.dont_write_bytecode = True

HERE = Path(__file__).resolve().parent
TREE = HERE.parent
PKG = TREE.parents[1]
OUT = PKG / 'evidence' / 'w2_source_contract'

WORKER = TREE / 'worker' / 'solver_worker_m4.cpp'
RAW = TREE / 'worker' / 'raw_backend_v1.hpp'
BACKEND = TREE / 'worker' / 'owned_cold_backend.hpp'


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    checks = {}

    worker = WORKER.read_text()
    checks['worker_merges_helper_parameter_set'] = bool(re.search(
        r'const auto &w2_names\s*=\s*w2_entry::parameters\(\);\s*'
        r'allowed\.insert\(w2_names\.begin\(\),\s*w2_names\.end\(\)\);', worker))
    checks['worker_whitelist_goes_through_helper'] = 'formal_owned::overrides(*this,allowed)' in worker
    # A regression that lists the five names literally again would leave the
    # helper unused; the merge check above would still pass, so assert that the
    # literal list is not present as the sole source of the names.
    literal_five = re.search(
        r'"w2_release_fd"\s*,\s*"w2_release_job_id"\s*,\s*"w2_release_ordinal"'
        r'\s*,\s*"w2_release_nonce"\s*,\s*"w2_release_wait_ns"', worker)
    checks['worker_does_not_duplicate_the_five_names'] = not literal_five

    raw = RAW.read_text()
    checks['raw_backend_calls_final_guard'] = bool(re.search(
        r'if\(final_guard_&&!final_guard_\(ordinal_\)\)', raw))
    checks['final_guard_precedes_native_call'] = (
        raw.index('final_guard_(ordinal_)') < raw.index('note_native_call(ordinal_)'))

    backend = BACKEND.read_text()
    # E3: the guard must check stop and the Job deadline for every internal
    # call, before the matches() shortcut.
    guard = backend[backend.index('set_final_guard'):backend.index('Json w2_boundary_event()')]
    checks['guard_checks_stop_for_every_call'] = 'if(stop_&&stop_())return false;' in guard
    checks['guard_checks_deadline_for_every_call'] = \
        'if(clock_()>current_deadline_ns_)return false;' in guard
    checks['guard_deadline_check_precedes_matches'] = (
        guard.index('current_deadline_ns_') < guard.index('matches(ordinal,current_job_)'))
    # E4: the catch must republish the boundary fact after a refusal.
    catch = backend[backend.index('}catch(...){'):]
    checks['catch_republishes_boundary'] = 'last_["w2_boundary"]=w2_boundary_json(rec);' in catch

    # E6: the terminal catch must clear the active slot. Anchor on the catch's
    # own body rather than a fixed-length window: `active_=0;` also appears in
    # the timeout paths, which would make this check pass after the fix is
    # removed from the catch itself.
    # The file has several `catch(const std::exception & e)` blocks; take the
    # one that actually contains the terminal record, not the first in the file.
    term_at = worker.index('"type","terminal_exception"')
    catch_start = worker.rindex('}catch(const std::exception & e){', 0, term_at)
    # End at the catch's own `break;}` rather than the next `}}`, which belongs
    # to the enclosing loop and would pull in the normal-completion path where
    # `active_=0;` legitimately appears.
    catch_end = worker.index('break;}', catch_start)
    catch_body = worker[catch_start:catch_end]
    checks['terminal_catch_clears_active'] = 'active_=0;' in catch_body

    ok = all(checks.values())
    report = {'schema': 'W2-source-contract-v1', 'checks': checks,
              'all_passed': ok,
              'note': ('Composition checks over production source. These cover '
                       'what a compiled unit test cannot observe: that the '
                       'Worker consumes the helper set and that RawBackend '
                       'really calls the final guard.')}
    path = OUT / 'source_contract_v1.json'
    path.write_text(json.dumps(report, indent=2) + '\n')
    for k, v in checks.items():
        print('%-46s %s' % (k, 'PASS' if v else 'FAIL'))
    print('all passed:', ok)
    print('written:', path)
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
