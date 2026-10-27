"""C3.4-B representation boundaries; never a runtime/phase qualification.

Historical complete-analyze overlays live in a separate reproducible script so
this unit suite does not depend on one research machine's pinned N9 captures.
"""
import copy
import json
import math
import struct
import unittest
from pathlib import Path
from unittest.mock import patch
import strict_types_v1 as d
import check_release_observation_v1 as c
import owned_auth as a
import owned_release as r
import test_release_observation_v1 as old_tests


class IntegerDomains(unittest.TestCase):
    def test_uint64_exact_boundaries(self):
        for value in (0, 1, d.U64_MAX):
            with self.subTest(value=value):
                self.assertEqual(d.uint64(value, 'count'), value)

    def test_uint64_rejects_all_confusion_and_range_cases(self):
        for value in (False, True, 0.0, 1.0, '0', '1', None, -1, d.U64_MAX + 1,
                      float('nan'), float('inf'), -float('inf')):
            with self.subTest(value=repr(value)):
                with self.assertRaisesRegex(ValueError, 'exact_uint64'):
                    d.uint64(value, 'count')

    def test_int64_exact_boundaries(self):
        for value in (d.I64_MIN, -1, 0, d.I64_MAX):
            with self.subTest(value=value):
                self.assertEqual(d.int64(value, 'time'), value)

    def test_int64_rejects_bool_float_str_null_and_overflow(self):
        for value in (False, True, 0.0, '0', None, d.I64_MIN - 1, d.I64_MAX + 1):
            with self.subTest(value=repr(value)):
                with self.assertRaisesRegex(ValueError, 'exact_int64'):
                    d.int64(value, 'time')

    def test_exact_bool_rejects_equal_integer_representations(self):
        for value in (0, 1, 0.0, 1.0, 'true', None):
            with self.subTest(value=repr(value)):
                with self.assertRaisesRegex(ValueError, 'exact_bool'):
                    d.boolean(value, 'flag')
        self.assertFalse(d.boolean(False, 'flag'))
        self.assertTrue(d.boolean(True, 'flag'))


class FiniteJSON(unittest.TestCase):
    def test_release_checker_nan_infinity_and_exponent_overflow(self):
        for token in ('NaN', 'Infinity', '-Infinity', '1e309', '-1e309'):
            for prefix, suffix in (('', ''), ('{"x": [', ']}')):
                with self.subTest(token=token, prefix=prefix):
                    with self.assertRaises(ValueError):
                        c.strict_json((prefix + token + suffix).encode())

    def test_owned_release_parser_rejects_overflow(self):
        for token in ('NaN', 'Infinity', '-Infinity', '1e309', '-1e309'):
            with self.subTest(token=token):
                with self.assertRaises(ValueError):
                    r.strict_json(('{"x":[' + token + ']}').encode())

    def test_finite_extremes_and_negative_zero_preserved(self):
        row = c.strict_json(b'{"x":[1e308,-1e308,-0.0,5e-324]}')
        self.assertTrue(all(math.isfinite(v) for v in row['x']))
        self.assertEqual(struct.pack('>d', row['x'][2]).hex(), '8000000000000000')

    def test_64bit_json_integer_domain(self):
        for value in (d.I64_MIN, d.U64_MAX):
            self.assertEqual(c.strict_json(str(value)), value)
        for value in (d.I64_MIN - 1, d.U64_MAX + 1):
            with self.assertRaisesRegex(ValueError, 'json_integer_native_64bit_range'):
                c.strict_json(str(value))


class GateFields(unittest.TestCase):
    def setUp(self):
        self.fixture = old_tests.GateObservation()
        self.fixture.setUp()

    def test_all_native_count_fields_reject_bool(self):
        original = copy.deepcopy(self.fixture.gate)
        for key in ('release_bytes_count', 'poll_count', 'missing_release_count',
                    'released_integrity_verify_count', 'original_freshness_read_count'):
            self.fixture.gate = copy.deepcopy(original)
            self.fixture.gate[key] = bool(original[key])
            with self.subTest(field=key), self.assertRaisesRegex(ValueError, 'exact_uint64'):
                self.fixture.positive()

    def test_original_expired_freshness_true_is_rejected(self):
        self.fixture.expired()
        self.fixture.gate['original_freshness_read_count'] = True
        with self.assertRaisesRegex(ValueError, 'gate.original_freshness_read_count:exact_uint64'):
            c.check_gate(self.fixture.gate, self.fixture.release, self.fixture.raw,
                self.fixture.event, 300, 'expired_release')

    def test_nullable_times_reject_non_integer_when_read(self):
        for value in (False, 150.0, '150', -1, d.I64_MAX + 1):
            self.fixture.setUp()
            self.fixture.gate['final_freshness_now_ns'] = value
            with self.subTest(value=repr(value)), self.assertRaisesRegex(ValueError, 'exact_int64'):
                self.fixture.positive()

    def test_unread_nulls_still_pass_actual_expired_case(self):
        self.assertTrue(self.fixture.expired()['passed'])

    def test_positive_required_read_null_still_fails_semantically(self):
        self.fixture.gate['final_freshness_now_ns'] = None
        with self.assertRaisesRegex(ValueError, 'positive_actual_freshness_values_invalid'):
            self.fixture.positive()

    def test_gate_flag_integer_is_rejected(self):
        self.fixture.gate['receipt_io_completed'] = 1
        with self.assertRaisesRegex(ValueError, 'exact_bool'):
            self.fixture.positive()

    def test_event_deadline_bool_is_rejected(self):
        self.fixture.event['valid_until_steady_ns'] = True
        with self.assertRaisesRegex(ValueError, 'exact_int64'):
            c.check_event(self.fixture.event, Path('/tmp/release.json'), self.fixture.release,
                self.fixture.raw, '2' * 64, 80)

    def test_completed_event_end_null_still_rejected_by_causality(self):
        self.fixture.event['call_end_steady_ns'] = None
        with self.assertRaisesRegex(ValueError, 'publication_call_timeline_invalid'):
            c.check_event(self.fixture.event, Path('/tmp/release.json'), self.fixture.release,
                self.fixture.raw, '2' * 64, 80)


class SessionAndTransportFields(unittest.TestCase):
    def setUp(self):
        self.fixture = old_tests.OriginalUnarmedSession()
        self.fixture.setUp()
        self.fixture.session['streams'] = {'applied': dict.fromkeys(
            ('generated', 'emitted', 'dropped', 'first_sequence', 'last_sequence'), 0)}

    def test_original_zero_session_fields_cannot_be_false(self):
        original = copy.deepcopy(self.fixture.session)
        for key in ('start_steady_ns', 'queue_dropped_total', 'publish_errors',
                    'cycle_invocations_started', 'interrupted_cycle_sequence'):
            self.fixture.session = copy.deepcopy(original)
            self.fixture.session[key] = False
            with self.subTest(field=key), self.assertRaisesRegex(ValueError, 'field_domain:'):
                c.check_source_session(self.fixture.session, self.fixture.startup, 300, 'expired_release')

    def test_all_stream_count_fields_exact_uint64(self):
        for key in self.fixture.session['streams']['applied']:
            for bad in (False, 0.0, '0', None, -1, d.U64_MAX + 1):
                row = copy.deepcopy(self.fixture.session)
                row['streams']['applied'][key] = bad
                with self.subTest(field=key, value=repr(bad)), self.assertRaisesRegex(ValueError, 'exact_uint64'):
                    d.session(row)

    def test_stream_count_uint64_boundary_is_representation_valid_only(self):
        self.fixture.session['streams']['applied']['generated'] = d.U64_MAX
        d.session(self.fixture.session)

    def test_terminal_count_bool_rejected(self):
        with self.assertRaisesRegex(ValueError, 'exact_uint64'):
            d.terminal({'transport_counts': {'/clock': False}})

    def test_transport_ordinal_float_rejected(self):
        with self.assertRaisesRegex(ValueError, 'exact_uint64'):
            d.transport({'ordinal': 1.0, 'serialized_bytes': 20})

    def test_sqlite_metadata_total_false_rejected(self):
        with self.assertRaisesRegex(ValueError, 'exact_uint64'):
            d.metadata({'message_count': False, 'topics_with_message_count': []})

    def test_ledger_returncode_false_and_identity_pid_float_rejected(self):
        for row in ({'returncode': False}, {'identity': {'pid': 1.0}}, {'monotonic_ns': d.I64_MAX + 1}):
            with self.subTest(row=row), self.assertRaisesRegex(ValueError, 'exact_int64'):
                d.ledger(row)

    def test_process_identity_uint64_ticks_boundary(self):
        d.identity({'pid': 1, 'start_ticks': d.U64_MAX})


class ParameterCanonicalFields(unittest.TestCase):
    def test_bool_cannot_be_parameter_type(self):
        with self.assertRaisesRegex(ValueError, 'invalid parameter type'):
            a.canonical_parameters({'x': {'type': True, 'value': True, 'canonical_value': True}})

    def test_typed_bool_canonical_cannot_be_equal_int(self):
        for kind, value, canonical in ((1, True, 1), (1, False, 0), (6, [True, False], [1, 0]),
                                        (2, 0, False), (7, [0], [False])):
            with self.subTest(kind=kind), self.assertRaisesRegex(ValueError, 'canonical parameter differs'):
                a.canonical_parameters({'x': {'type': kind, 'value': value, 'canonical_value': canonical}})

    def test_double_and_double_array_reject_bool_and_nonfinite(self):
        for value in (True, False, float('nan'), float('inf'), -float('inf'), 10 ** 400):
            for kind in (3, 8):
                row = {'type': kind, 'value': value if kind == 3 else [value],
                       'canonical_value': '0000000000000000' if kind == 3 else ['0000000000000000']}
                with self.subTest(kind=kind, value=repr(value)), self.assertRaises(ValueError):
                    a.canonical_parameters({'x': row})

    def test_double_exponent_overflow_from_json_cannot_reach_canonical(self):
        with self.assertRaises(ValueError):
            parameters = c.strict_json(b'{"x":{"type":8,"value":[1e309],"canonical_value":["7ff0000000000000"]}}')
            a.canonical_parameters(parameters)

    def test_parameter_integer_array_signed_boundaries(self):
        values = [d.I64_MIN, d.I64_MAX]
        self.assertEqual(a.canonical_parameters({'x': {'type': 7, 'value': values,
            'canonical_value': values}})['x']['canonical_value'], values)
        for bad in (True, d.I64_MIN - 1, d.I64_MAX + 1):
            with self.subTest(value=bad), self.assertRaises(ValueError):
                a.canonical_parameters({'x': {'type': 7, 'value': [bad], 'canonical_value': [bad]}})

    def test_parameter_byte_array_bounds(self):
        a.canonical_parameters({'x': {'type': 5, 'value': [0, 255], 'canonical_value': [0, 255]}})
        for bad in (True, -1, 256, 0.0):
            with self.subTest(value=bad), self.assertRaises(ValueError):
                a.canonical_parameters({'x': {'type': 5, 'value': [bad], 'canonical_value': [bad]}})

    def test_signed_zero_bits_still_distinct(self):
        plus = a.parameter_digest({'x': {'type': 3, 'value': 0.0, 'canonical_value': '0000000000000000'}})
        minus = a.parameter_digest({'x': {'type': 3, 'value': -0.0, 'canonical_value': '8000000000000000'}})
        self.assertNotEqual(plus, minus)


if __name__ == '__main__':
    unittest.main()
