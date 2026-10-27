"""Actual file/role entry for the NEW bounded no_output preparation session.

This authenticates input bytes, not peer/endpoint readiness. No solver, actuator,
ROS node, or business thread is started here. The owned runtime adapter remains
a separate integration obligation.
"""
from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import re
import stat

from p1_full_contract import (ContractError, SPEC_SHA256, MAX_CONTRACT_BYTES,
                              parse_contract_bytes, require_runtime_mode)


@dataclass(frozen=True)
class PreparationContract:
    path: str
    raw: bytes
    sha256: str
    spec_sha256: str
    device: int
    inode: int
    mode: int

    @property
    def configuration(self):
        """A new parsed value; callers cannot mutate the authenticated bytes."""
        return parse_contract_bytes(self.raw)


def load_preparation_contract(path, expected_sha256, *, mode):
    if (type(expected_sha256) is not str
            or re.fullmatch(r'[0-9a-f]{64}', expected_sha256) is None):
        raise ContractError('explicit expected SHA-256 required for preparation entry')
    if type(mode) is not str or mode != 'no_output':
        raise ContractError('formal preparation entry requires no_output')
    name = os.fspath(path)
    if type(name) is not str or len(name.encode('utf-8')) > 4096 or '\0' in name:
        raise ContractError('bounded explicit file path required')
    p = Path(name)
    if not p.is_absolute() or str(p) != name or '..' in p.parts or not p.name:
        raise ContractError('absolute normalized path required')
    directory = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    fd = None
    try:
        for part in p.parent.parts[1:]:
            next_directory = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                                     dir_fd=directory)
            os.close(directory)
            directory = next_directory
        fd = os.open(p.name, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK,
                     dir_fd=directory)
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or not 0 < before.st_size <= MAX_CONTRACT_BYTES:
            raise ContractError('bounded regular contract file required')
        data = bytearray()
        while len(data) <= MAX_CONTRACT_BYTES:
            chunk = os.read(fd, MAX_CONTRACT_BYTES + 1 - len(data))
            if not chunk:
                break
            data.extend(chunk)
        after = os.fstat(fd)
        metadata = lambda s: (s.st_dev, s.st_ino, s.st_mode, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
        if metadata(before) != metadata(after) or len(data) != after.st_size:
            raise ContractError('contract file changed during read')
        raw = bytes(data)
        actual = hashlib.sha256(raw).hexdigest()
        if actual != expected_sha256:
            raise ContractError('preparation contract SHA-256 mismatch')
        contract = parse_contract_bytes(raw)
        require_runtime_mode(contract, mode)
        if (contract['schema'] != 'p1-execution-contract-v3'
                or contract['qualification'] != 'execution_pre_freeze'):
            raise ContractError('preparation entry accepts only formal pre-freeze')
        return PreparationContract(name, raw, actual, SPEC_SHA256,
                                   after.st_dev, after.st_ino, after.st_mode)
    finally:
        if fd is not None:
            os.close(fd)
        os.close(directory)
