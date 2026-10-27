"""Independent declared configuration-domain check, never a full-chain gate.

This does not change production defaults. It validates owned typed canonical
parameters for five-role captured fixtures. Typed IEEE hex hashing does not
qualify the unrelated decimal formatter used by reference fingerprints.
"""
from __future__ import annotations
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import owned_auth
import strict_types_v1 as domains
from check_release_observation_v1 import Inputs, ROLES, strict_json

SCHEMA = 'p1-C3.4-config-supported-domain/v1'


def ascii_string(value, path):
    if type(value) is not str or not value.isascii():
        raise ValueError('unsupported_config_domain:' + path + ':ASCII_string')


def check_parameters(parameters):
    canonical = owned_auth.canonical_parameters(parameters)
    if len(parameters) > 512:
        raise ValueError('unsupported_config_domain:parameter_population_exceeds_512')
    counts = Counter()
    ieee_bits = set()
    for name, row in parameters.items():
        ascii_string(name, 'parameter_name')
        kind, value = row['type'], row['value']
        counts[str(kind)] += 1
        if kind == 4:
            ascii_string(value, name)
        elif kind == 9:
            for i, item in enumerate(value):
                ascii_string(item, name + '[' + str(i) + ']')
        elif kind == 3:
            ieee_bits.add(row['canonical_value'])
        elif kind == 8:
            ieee_bits.update(row['canonical_value'])
    return {'passed': True, 'parameters': len(parameters), 'type_population': dict(counts),
        'canonical_ieee_bits': sorted(ieee_bits),
        'canonical_sha256': owned_auth.parameter_digest(parameters),
        'declared_domain': {'names_strings': 'ASCII including JSON-escaped controls',
            'bool': 'exact bool', 'integer': 'signed int64', 'double': 'finite IEEE754 binary64, canonical hex',
            'arrays': 'typed homogeneous arrays; empty permitted with explicit ROS type',
            'byte_array': 'exact uint8 array; supported component domain, not used by recorded five-role sample',
            'not_set': 'null for explicit ROS type 0; supported component domain, not used by recorded sample'},
        'general_reference_decimal_formatter_qualified': False,
        'general_JSON_YAML_Unicode_qualified': False}


def check_expected(expected):
    if type(expected) is not dict or len(expected) > 512:
        raise ValueError('unsupported_config_domain:expected_parameter_object')
    for name, value in expected.items():
        ascii_string(name, 'expected_parameter_name')
        values = value if type(value) is list else [value]
        if type(value) is list and values and len({type(x) for x in values}) != 1:
            raise ValueError('unsupported_config_domain:' + name + ':homogeneous_array')
        for item in values:
            if type(item) is str:
                ascii_string(item, name)
            elif type(item) is bool or item is None:
                pass
            elif type(item) is int:
                domains.int64(item, 'expected.' + name)
            elif type(item) is float:
                domains.finite_number(item, 'expected.' + name)
            else:
                raise ValueError('unsupported_config_domain:' + name + ':ROS_parameter_value')
    return True


def analyze(run):
    run = Path(run)
    reader = Inputs()
    inputs = reader.json(run / 'inputs.json')
    results = {}
    for role in ROLES:
        manifest = reader.json(run / role / 'owned_manifest.json')
        parameters = manifest['effective_parameters']
        value = check_parameters(parameters)
        if value['canonical_sha256'] != manifest['effective_parameters_sha256']:
            raise ValueError('actual_cpp_canonical_parameter_digest_differs:' + role)
        expected = inputs['expected_parameters'][role]
        check_expected(expected)
        actual = {name: row['value'] for name, row in parameters.items()}
        if not owned_auth.exact_value(actual, expected):
            raise ValueError('full_effective_expected_typed_configuration_differs:' + role)
        value['actual_manifest_path'] = str(run / role / 'owned_manifest.json')
        value['expected_full_value_set_equal'] = True
        value['byte_arrays_observed'] = value['type_population'].get('5', 0)
        results[role] = value
    after = reader.unchanged()
    if reader.before != after:
        raise ValueError('config_scope_input_changed')
    return {'schema': SCHEMA, 'passed': True, 'run': str(run), 'roles': results,
        'input_sha256_before': reader.before, 'input_sha256_after': after,
        'inputs_unchanged': True, 'checker_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'general_reference_decimal_formatter_qualified': False,
        'general_JSON_YAML_Unicode_qualified': False,
        'shared_v2_original_identity_restored': False, 'strict_full_chain': False,
        'D1': False, 'P1': False, 'execute': False, 'research_conclusion': False,
        'limits': ['supported typed configuration scope only; arbitrary Unicode/mappings/mixed arrays unqualified',
            'native Reference fingerprint decimal spelling still requires its recorded IEEE corpus',
            'no dynamic recipe, actual plant, Master Clock, strict or research qualification']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    try:
        result = analyze(args.run)
    except Exception as error:
        result = {'schema': SCHEMA, 'passed': False, 'error': type(error).__name__ + ': ' + str(error),
            'strict_full_chain': False, 'execute': False}
    from owned_release import create_only_json
    create_only_json(args.output, result)
    print(json.dumps({'passed': result['passed'], 'output': str(args.output), 'error': result.get('error')}))
    return 0 if result['passed'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
