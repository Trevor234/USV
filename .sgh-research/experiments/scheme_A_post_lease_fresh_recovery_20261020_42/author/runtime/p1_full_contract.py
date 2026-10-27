"""Pinned B0 full-contract rules; no ROS or physical execution authorization.

Legacy revision recognition remains in p1_contract_revision. This module validates
complete current diag5 and fixed-profile formal v3 contracts only.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import re

from p1_contract_revision import resource_contract_supported

SPEC_SHA256 = "33fb4a5eef93aa6abce5a61e7549dd7217f90c9572e5097791731fbb89661ffd"
MAX_CONTRACT_BYTES = 65536
MIN_INT64, MAX_INT64 = -(1 << 63), (1 << 63) - 1


class ContractError(ValueError):
    """A declared contract or role is unsupported; no coercion is permitted."""


def _reject_constant(token):
    raise ContractError("nonfinite JSON constant: " + token)


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ContractError("duplicate JSON key: " + key)
        result[key] = value
    return result


def _domain(value, field="contract"):
    kind = type(value)
    if kind is dict:
        for key, item in value.items():
            if type(key) is not str:
                raise ContractError("string object key required: " + field)
            _domain(item, field + "." + key)
    elif kind is list:
        for index, item in enumerate(value):
            _domain(item, f"{field}[{index}]")
    elif kind is int:
        if not MIN_INT64 <= value <= MAX_INT64:
            raise ContractError("integer outside int64: " + field)
    elif kind is float:
        if not math.isfinite(value):
            raise ContractError("finite number required: " + field)
    elif kind not in (str, bool, type(None)):
        raise ContractError("JSON value required: " + field)


def parse_contract_bytes(data: bytes):
    """Strict raw bytes, including duplicate keys, constants and size limits."""
    if type(data) is not bytes or len(data) > MAX_CONTRACT_BYTES:
        raise ContractError("contract exceeds 64 KiB or is not bytes")
    try:
        value = json.loads(data.decode("utf-8"), object_pairs_hook=_unique_object,
                           parse_constant=_reject_constant)
        _domain(value)
        return value
    except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise ContractError("invalid contract JSON: " + str(exc)) from exc


_spec_bytes = Path(__file__).with_name("p1_contract_spec_v1.json").read_bytes()
if hashlib.sha256(_spec_bytes).hexdigest() != SPEC_SHA256:
    raise ContractError("contract validation spec hash changed")
SPEC = parse_contract_bytes(_spec_bytes)
if (SPEC.get("schema") != "p1-contract-validation-spec-v1"
        or SPEC.get("max_contract_bytes") != MAX_CONTRACT_BYTES
        or SPEC.get("physical_execute_release_enabled") is not False):
    raise ContractError("unsupported pinned contract spec")
FORMAL_SCHEMA = SPEC["formal_schema"]
_BASELINE = SPEC["legacy_baseline"]
_INTEGER_KEYS = frozenset(SPEC["integer_keys"])
_RESOURCE_KEYS = frozenset(SPEC["resource_keys"])
_SPECIAL_KEYS = frozenset(SPEC["special_keys"])
_FORMAL_KEYS = (frozenset(_BASELINE) - {"diagnostic_contract_revision"}
                | frozenset(SPEC["formal_added_keys"]))


def _match(value, expected, field):
    """JSON semantic numeric equality, while bool and integer keys stay strict."""
    kind = type(expected)
    if kind is dict:
        if type(value) is not dict or set(value) != set(expected):
            raise ContractError("object shape mismatch: " + field)
        for key, item in expected.items():
            _match(value[key], item, field + "." + key)
    elif kind is list:
        if type(value) is not list or len(value) != len(expected):
            raise ContractError("array shape mismatch: " + field)
        for index, item in enumerate(expected):
            _match(value[index], item, f"{field}[{index}]")
    elif kind in (int, float):
        if type(value) not in (int, float) or value != expected:
            raise ContractError("unsupported numeric profile: " + field)
    elif type(value) is not kind or value != expected:
        raise ContractError("unsupported profile value/type: " + field)


def validate_fields(contract: dict) -> dict:
    """Validate a complete profile only; worker roles use this fields-only gate."""
    if type(contract) is not dict:
        raise ContractError("contract object required")
    _domain(contract)
    schema = contract.get("schema")
    formal = schema == FORMAL_SCHEMA
    if schema != _BASELINE["schema"] and not formal:
        raise ContractError("unsupported contract schema")
    expected_keys = _FORMAL_KEYS if formal else frozenset(_BASELINE)
    if set(contract) != expected_keys:
        missing = sorted(expected_keys - set(contract))
        extra = sorted(set(contract) - expected_keys)
        raise ContractError(f"contract field set mismatch: missing={missing}, extra={extra}")
    for key in _INTEGER_KEYS.intersection(contract):
        if type(contract[key]) is not int:
            raise ContractError("true integer required: " + key)
    if not resource_contract_supported(contract):
        raise ContractError("unsupported typed resource domain")
    for key, value in _BASELINE.items():
        if key in _RESOURCE_KEYS or (formal and key in _SPECIAL_KEYS):
            continue
        _match(contract[key], value, key)
    if not formal:
        return contract
    for key, value in (("execution_contract_revision", SPEC["execution_revision"]),
                       ("resource_contract_revision", SPEC["resource_revision"])):
        if type(contract[key]) is not int or contract[key] != value:
            raise ContractError("unsupported integer revision: " + key)
    _match(contract["supported_parameter_profile"], SPEC["profile_id"],
           "supported_parameter_profile")
    if contract["qualification"] == SPEC["formal_pre_freeze_qualification"]:
        expected = {"execute_qualified": False, "parameters_are_diagnostic_only": True,
                    "fault_injection_enabled": False, "freeze_evidence_sha256": "",
                    "pending_final_calibration": _BASELINE["pending_final_calibration"]}
    elif contract["qualification"] == SPEC["formal_frozen_qualification"]:
        expected = {"execute_qualified": True, "parameters_are_diagnostic_only": False,
                    "fault_injection_enabled": False, "pending_final_calibration": []}
        marker = contract["freeze_evidence_sha256"]
        if type(marker) is not str or re.fullmatch(r"[0-9a-f]{64}", marker) is None:
            raise ContractError("frozen evidence SHA-256 required")
    else:
        raise ContractError("unsupported formal qualification")
    for key, value in expected.items():
        _match(contract[key], value, key)
    return contract


def validate_mode(contract: dict, mode: str) -> dict:
    """Pure role/mode matrix; a frozen profile does not authorize startup."""
    validate_fields(contract)
    if type(mode) is not str:
        raise ContractError("mode string required")
    allowed = ({"no_output", "execute"}
               if contract["schema"] == FORMAL_SCHEMA and
               contract["qualification"] == SPEC["formal_frozen_qualification"]
               else {"no_output"} if contract["schema"] == FORMAL_SCHEMA
               else {"no_output", "shadow"})
    if mode not in allowed:
        raise ContractError("contract mode not permitted: " + mode)
    return contract


def require_runtime_mode(contract: dict, mode: str) -> dict:
    """Actual startup gate: release is closed even for structurally frozen v3."""
    validate_mode(contract, mode)
    if mode == "execute":
        raise ContractError("B5/M4 release not enabled")
    return contract


def load_contract(path: Path, expected: str | None = None, *,
                  mode: str | None = None, runtime: bool = False) -> tuple[dict, str]:
    with Path(path).open("rb") as stream:
        data = stream.read(MAX_CONTRACT_BYTES + 1)
    if len(data) > MAX_CONTRACT_BYTES:
        raise ContractError("contract exceeds 64 KiB")
    actual = hashlib.sha256(data).hexdigest()
    if expected is not None and (type(expected) is not str or
            re.fullmatch(r"[0-9a-f]{64}", expected) is None or actual != expected):
        raise ContractError("contract hash changed or invalid expected SHA-256")
    contract = parse_contract_bytes(data)
    validate_fields(contract)
    if runtime and mode is None:
        raise ContractError("runtime mode required")
    if mode is not None:
        (require_runtime_mode if runtime else validate_mode)(contract, mode)
    return contract, actual
