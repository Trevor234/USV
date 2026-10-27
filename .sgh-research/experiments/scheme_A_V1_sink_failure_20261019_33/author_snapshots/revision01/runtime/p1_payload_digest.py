"""Canonical ROS field content, independent of CDR alignment padding.
Finite doubles and signed zeros retain their IEEE754 bits. Every NaN stimulus is
classified as the same invalid numeric value; NaN payload bits are not a contract.
"""
import hashlib
import json
import math
import struct

def canonical(value):
    if isinstance(value, dict):
        return {str(k):canonical(v) for k,v in value.items()}
    if isinstance(value, (list, tuple)):
        return [canonical(v) for v in value]
    if isinstance(value, float):
        return {"float64": "NaN" if math.isnan(value) else struct.pack("!d",value).hex()}
    if value is None or isinstance(value,(str,int,bool)):
        return value
    raise TypeError("unsupported normalized ROS field "+type(value).__name__)

def canonical_payload_digest(value):
    blob=json.dumps(canonical(value),sort_keys=True,separators=(",",":"),allow_nan=False).encode()
    return hashlib.sha256(blob).hexdigest()

def payload_digest(message):
    from rosidl_runtime_py.convert import message_to_ordereddict
    from check_p1_execution import plain
    return canonical_payload_digest(plain(dict(message_to_ordereddict(message))))
