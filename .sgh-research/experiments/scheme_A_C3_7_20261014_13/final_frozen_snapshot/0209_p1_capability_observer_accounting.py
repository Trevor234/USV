"""Content-aligned capability receipt suffix; explicitly bounded bootstrap prefix.

v1 has no sequence/send timestamp. Matching receipt contents cannot establish
per-packet provenance, source freshness or replay resistance.
"""
def account_capability_receipts(observed, actual, first_wall_ns):
    issues=[]
    prefix_count=len(actual)-len(observed)
    if not observed or type(first_wall_ns) is not int or first_wall_ns<=0:
        issues.append('capability first observer wall receipt absent')
    if prefix_count<0:
        issues.append('capability observer has more receipts than actual bag')
        prefix_count=0
    prefix=actual[:prefix_count];suffix=actual[prefix_count:]
    if [e['payload_sha256'] for e in observed]!=[e['payload_sha256'] for e in suffix]:
        issues.append('capability observer/actual receipt suffix differs')
    if prefix and (type(first_wall_ns) is not int or any(
        type(e.get('bag_receive_wall_ns')) is not int
        or e['bag_receive_wall_ns']>=first_wall_ns
        or e['message']['active_job']!=0
        or e['message']['pending_count']!=0
        or e['message']['completed_jobs']!=0
        or e['message']['fatal']
        for e in prefix)):
        issues.append('capability unobserved prefix not pre-observer initial idle receipts')
    return {'issues':issues,'unobserved_bootstrap_capability_prefix_count':len(prefix),
            'capability_observer_receipt_suffix_count':len(suffix),
            'first_capability_observer_wall_ns':first_wall_ns,
            'capability_receipt_accounting_semantics':'ordered payload suffix with initial idle raw prefix before first observer receipt; no per-packet source provenance'}
