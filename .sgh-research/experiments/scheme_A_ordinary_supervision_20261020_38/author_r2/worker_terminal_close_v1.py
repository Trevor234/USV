"""Authenticated reception closure after Worker terminal invalidates business anchors.

This is a distinct diagnostic profile. It never claims the old normal anchor-tail
chain, and still requires a live Observer ACK before Publisher shutdown.
"""
import hashlib
import json
from pathlib import Path
import time

PROFILE = 'worker-terminal-reception-v1'


def need(value, why):
    if not value:
        raise ValueError(why)


def capture(root, roles, *, rows, spin, bound, close_start_ns, deadline_ns, create_only_json):
    root = Path(root)
    session_path = root / 'publisher/session_summary.json'
    session = json.loads(session_path.read_bytes())
    last = session['streams']['applied']['last_sequence']
    need(session['normal_end'] and session['flushed'] and session['publish_errors'] == 0 and last > 0,
         'terminal_reception_requires_normal_Publisher_close')
    owner = roles['publisher']['manifest']
    endpoints = owner['endpoints']
    def gid(topic):
        found = [e['gid'] for e in endpoints if e['kind'] == 'publisher' and e['topic'] == topic]
        need(len(found) == 1, 'one_exact_owner_GID:' + topic)
        return found[0]
    applied_gid = gid('/research/control/applied')
    physical = ['/wamv/thrusters/left/thrust', '/wamv/thrusters/right/thrust']
    until = min(deadline_ns, close_start_ns + 15_000_000_000, time.monotonic_ns() + 2_000_000_000)
    while time.monotonic_ns() < until:
        bound()  # Live real driver excludes already reaped Publisher, checks other owned roles.
        source = rows(root / 'observer/source.jsonl')
        callbacks = [r for r in source if r.get('type') == 'adapter_applied_callback']
        found = {r['sequence']: r for r in callbacks if r['authentication_reason'] == ''}
        need(len(found) == len([r for r in callbacks if r['authentication_reason'] == '']), 'duplicate_authenticated_Applied_sequence')
        need(all(r['raw_input']['publisher_gid'] == applied_gid for r in found.values()), 'terminal_callback_foreign_GID')
        complete = set(found) == set(range(1, last + 1))
        if complete:
            for r in found.values():
                raw = r['raw_input'];wire = bytes.fromhex(raw['cdr_hex'])
                need(len(wire) == raw['cdr_bytes'] and hashlib.sha256(wire).hexdigest() == raw['cdr_sha256'], 'terminal_callback_CDR_integrity')
            tx = rows(root / 'synthetic_source/transport_source.jsonl')
            counts = {}
            for topic in physical + ['/research/control/applied']:
                records = [r for r in tx if r['topic'] == topic]
                need(all(r['publisher_gid'] == gid(topic) for r in records), 'foreign_terminal_transport_GID')
                counts[topic] = len(records)
            if all(n == session['streams']['applied']['emitted'] for n in counts.values()):
                proof = {'schema': 'V2-worker-terminal-authenticated-reception-close/v1', 'profile': PROFILE,
                    'run_id': roles['observer']['manifest']['run_id'], 'checked_ns': time.monotonic_ns(),
                    'Publisher_session_sha256': hashlib.sha256(session_path.read_bytes()).hexdigest(),
                    'publisher_last_sequence': last, 'authenticated_receiver_last_sequence': max(found),
                    'authenticated_receiver_count': len(found), 'transport_counts': counts,
                    'receiver_roles_alive': True, 'business_anchor_count':len([r for r in source if r.get('type')=='legacy_anchor']),
                    'business_anchor_chain_complete': [r['sequence'] for r in source if r.get('type')=='legacy_anchor']==list(range(1,last+1)),
                    'normal_close_qualified': False, 'stage_qualified': False, 'execute_qualified': False,
                    'research_conclusion': False}
                create_only_json(root / 'V2_terminal_reception_close_ack.json', proof)
                return proof
        spin(.01)
    raise RuntimeError('V2 authenticated terminal reception capture expired')
