"""Preserved strict typed-resource domain; no diagnostic revision recognizer."""
RESOURCE_POLICY="typed_domain_bounds_before_copy_v1"
RESOURCE_BUDGET_SCOPE="application_typed_domain_cdr1_with_4_byte_encapsulation"
RESOURCE_FIELDS={"resource_policy","max_profile_dims","max_profile_label_bytes",
                 "max_path_frame_bytes","job_cdr_max_bytes","candidate_cdr_max_bytes",
                 "resource_budget_scope"}

def resource_contract_supported(contract):
    """Validate the declared typed application domain, not raw DDS allocation."""
    if (contract.get("resource_policy") != RESOURCE_POLICY
            or contract.get("resource_budget_scope") != RESOURCE_BUDGET_SCOPE):
        return False
    fixed={"max_profile_dims":4,"max_profile_label_bytes":64,
           "max_path_frame_bytes":128,"job_cdr_max_bytes":6460,
           "candidate_cdr_max_bytes":8204,"dds_depth":1}
    for key, expected in fixed.items():
        value=contract.get(key)
        if type(value) is not int or value != expected:
            return False
    bounded={"max_path_points":2048,"max_profile_rows":2048,
             "log_capacity":512,"history_capacity":256}
    for key, upper in bounded.items():
        value=contract.get(key)
        if type(value) is not int or not 1 <= value <= upper:
            return False
    for key, lower, upper in (("max_job_bytes",6460,8192),
                              ("max_candidate_bytes",8204,16384)):
        value=contract.get(key)
        if type(value) is not int or not lower <= value <= upper:
            return False
    return True
