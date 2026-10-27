#!/usr/bin/env python3
"""Freeze admission compatibility entry: delegates to the single physical RNW rule source.
The original batch-117 implementation remains preserved in the takeover snapshot.
"""
import t2_rnw_admission_rules as _rules
FAMILY = _rules.FAMILY
TABLE_KEYS = _rules.TABLE_KEYS
CLAUSE_SPEC = _rules.CLAUSE_SPEC
ACTION_SPEC = _rules.ACTION_SPEC
REQUIRED_ORDER = _rules.REQUIRED_ORDER
validate_table = _rules.validate_table
module_identity = _rules.module_identity
