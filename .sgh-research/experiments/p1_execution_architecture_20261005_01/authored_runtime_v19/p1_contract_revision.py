"""Recognize preserved diagnostic revisions without accepting an undeclared policy."""
POLICY="terminal_on_failed_or_invalid_native_result"

def diagnostic_revision_supported(contract):
    revision=contract.get("diagnostic_contract_revision")
    if type(revision) is not int:
        return False
    if revision==2:
        return "worker_failure_policy" not in contract
    return revision==3 and contract.get("worker_failure_policy")==POLICY
