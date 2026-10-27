"""Declared-domain admission boundaries; no production default modification."""
import struct
import unittest
import config_scope_v1 as c


class ConfigScope(unittest.TestCase):
    def test_ascii_escape_population_and_supported_scalar_rows(self):
        text = ''.join(chr(i) for i in range(128))
        report = c.check_parameters({'text': {'type': 4, 'value': text, 'canonical_value': text},
            'flag': {'type': 1, 'value': False, 'canonical_value': False},
            'low': {'type': 2, 'value': -(1 << 63), 'canonical_value': -(1 << 63)},
            'high': {'type': 2, 'value': (1 << 63) - 1, 'canonical_value': (1 << 63) - 1}})
        self.assertTrue(report['passed'])
        self.assertFalse(report['general_JSON_YAML_Unicode_qualified'])

    def test_unicode_name_or_value_explicitly_out_of_scope(self):
        for name, value in (('中文', 'ASCII'), ('ascii', '中文')):
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, 'unsupported_config_domain'):
                c.check_parameters({name: {'type': 4, 'value': value, 'canonical_value': value}})

    def test_double_scope_finite_extremes_bits_and_signed_zero(self):
        values = [1e308, -1e308, 5e-324, -0.0, 0.0]
        report = c.check_parameters({'x': {'type': 8, 'value': values,
            'canonical_value': [struct.pack('>d', v).hex() for v in values]}})
        self.assertEqual(len(report['canonical_ieee_bits']), 5)
        self.assertFalse(report['general_reference_decimal_formatter_qualified'])

    def test_homogeneous_array_and_byte_domain(self):
        rows = {}
        for name, kind, values in (('bytes', 5, [0, 255]), ('bools', 6, [False, True]),
            ('ints', 7, [-1, 1]), ('strings', 9, ['a', '\\"\n']), ('empty', 9, [])):
            rows[name] = {'type': kind, 'value': values, 'canonical_value': values}
        self.assertTrue(c.check_parameters(rows)['passed'])
        with self.assertRaises(ValueError):
            c.check_expected({'mixed': [1, False]})

    def test_arbitrary_mapping_and_nonfinite_unsupported(self):
        for value in ({'nested': 1}, float('inf'), float('nan'), 1 << 63):
            with self.subTest(value=repr(value)), self.assertRaises(ValueError):
                c.check_expected({'x': value})

    def test_string_array_unicode_unsupported(self):
        with self.assertRaisesRegex(ValueError, 'unsupported_config_domain'):
            c.check_parameters({'x': {'type': 9, 'value': ['ASCII', '中文'],
                'canonical_value': ['ASCII', '中文']}})


if __name__ == '__main__':
    unittest.main()
