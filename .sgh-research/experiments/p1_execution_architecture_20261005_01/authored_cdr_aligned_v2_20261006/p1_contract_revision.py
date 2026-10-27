"""Recognize preserved diagnostic revisions without accepting an undeclared policy."""
POLICY="terminal_on_failed_or_invalid_native_result"
CAPABILITY_POLICY="valid_identity_capability_callback_receipt_lease_terminal_until_new_run"
CAPABILITY_FIELDS={"worker_capability_lease_policy","worker_capability_receipt_timeout_ns","worker_capability_source_freshness_available"}

def diagnostic_revision_supported(contract):
    revision=contract.get("diagnostic_contract_revision")
    if type(revision) is not int:
        return False
    if revision==2:
        return "worker_failure_policy" not in contract and not CAPABILITY_FIELDS.intersection(contract)
    if revision==3:
        return contract.get("worker_failure_policy")==POLICY and not CAPABILITY_FIELDS.intersection(contract)
    age=contract.get("worker_capability_receipt_timeout_ns")
    return (revision==4 and contract.get("worker_failure_policy")==POLICY
            and contract.get("worker_capability_lease_policy")==CAPABILITY_POLICY
            and type(age) is int and 200_000_000<=age<=5_000_000_000
            and contract.get("worker_capability_source_freshness_available") is False
            and contract.get("parameters_are_diagnostic_only") is True)
