"""Strict GoogleTest/attempt gates shared by the reviewed runner and tests."""
from collections import Counter


def parse_gtest(doc, expected):
    assert isinstance(doc, dict), 'missing GoogleTest document'
    for key in ('tests', 'failures', 'errors', 'disabled'):
        assert type(doc.get(key)) is int and doc[key] >= 0, 'invalid GoogleTest total: ' + key
    assert isinstance(doc.get('testsuites'), list), 'missing suites'
    rows = {}
    for suite in doc['testsuites']:
        assert isinstance(suite, dict) and isinstance(suite.get('name'), str)
        assert isinstance(suite.get('testsuite'), list)
        for case in suite['testsuite']:
            assert isinstance(case, dict) and isinstance(case.get('name'), str)
            name = suite['name'] + '.' + case['name']
            assert name not in rows, 'duplicate test: ' + name
            failures = case.get('failures', [])
            assert isinstance(failures, list)
            assert all(isinstance(item, dict) and isinstance(item.get('failure'), str)
                       and item['failure'] for item in failures), 'malformed assertion evidence'
            rows[name] = {'status': case.get('status'), 'result': case.get('result'),
                          'failures': [item['failure'] for item in failures],
                          'skipped': bool(case.get('skipped'))}
    assert set(rows) == set(expected), 'test population mismatch'
    assert doc['tests'] == len(rows), 'test count mismatch'
    assert doc['failures'] == sum(bool(row['failures']) for row in rows.values()), 'failure count mismatch'
    assert doc['errors'] == doc['disabled'] == 0, 'errors or disabled tests'
    assert all(row['status'] == 'RUN' and row['result'] == 'COMPLETED' and not row['skipped']
               for row in rows.values()), 'test did not execute completely'
    return rows


def baseline_verdict(doc, returncode, expected):
    rows = parse_gtest(doc, expected)
    assert returncode == 0 and not any(row['failures'] for row in rows.values()), 'baseline failed'
    return rows


def mutation_verdict(doc, returncode, expected, named_failures, prepared, compile_returncode):
    assert prepared is True and compile_returncode == 0, 'unprepared or unbuilt mutation'
    rows = parse_gtest(doc, expected)
    assertions = {name for name, row in rows.items() if row['failures']}
    assert returncode == 1 and assertions, 'mutation was not rejected by assertions'
    assert named_failures and set(named_failures) <= assertions, 'named mutation assertion missing'
    return sorted(assertions)


def complete_verdict(baseline_passed, mutations, expected_names, identities_unchanged):
    names = [row['name'] for row in mutations]
    assert names and Counter(names) == Counter(expected_names), 'mutation population mismatch'
    assert baseline_passed is True and identities_unchanged is True, 'baseline or identity failed'
    assert all(row.get('prepared') is True and row.get('assertion_caught') is True
               for row in mutations), 'mutation not caught'
    return True
