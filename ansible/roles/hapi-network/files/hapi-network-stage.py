#!/usr/bin/python3
"""Serialize the real HAPI network deployment; publish only verified policies."""
import fcntl
import importlib.util
import os
from pathlib import Path
import re
import sys

spec = importlib.util.spec_from_file_location('sdn', Path(__file__).with_name('hapi-sdn.py'))
sdn = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sdn)
boundary = sdn.boundary


def deploy(candidate, expected, root=boundary.ROOT, state=boundary.STATE):
    boundary.require(os.geteuid() == 0, 'PVE network deployment requires root')
    boundary.require(expected == 'absent' or isinstance(expected, str) and re.fullmatch(r'[a-f0-9]{64}', expected),
                     'An explicit reviewed current digest or absent is required')
    state.mkdir(mode=0o700, parents=True, exist_ok=True)
    boundary.STATE = state
    with (state / 'lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        c = boundary.load(candidate)
        current = root / 'manifest.json'
        checkpoint = state / 'network-operation.json'
        phase = 'validate'
        def record(status):
            boundary.atomic(checkpoint, {'manifest': boundary.digest(c), 'stage': phase,
                                        'status': status, 'public_entry_ready': False})
        try:
            record('running')
            live_digest = boundary.digest(boundary.load(current)) if current.exists() else 'absent'
            boundary.require(expected == live_digest or live_digest == boundary.digest(c),
                             'Stale manifest baseline; review a fresh plan before retrying')
            if current.exists():
                boundary.compatible(c, boundary.load(current))
            phase = 'kernel-preflight'
            record('running')
            boundary.preflight(c)
            phase = 'sdn'
            record('running')
            changed = sdn.SDN(state / 'sdn.json').reconcile(c)
            phase = 'external-boundaries'
            record('running')
            changed = boundary.apply(c) or changed
            boundary.verify(c)
            phase = 'publish-manifest'
            record('running')
            if not current.exists() or boundary.load(current) != c:
                boundary.atomic(current, c)
                changed = True
            phase = 'external-boundaries-verified'
            record('complete')
            return changed
        except Exception:
            record('failed')
            raise


if __name__ == '__main__':
    try:
        boundary.require(len(sys.argv) == 3, 'Supply the candidate manifest and reviewed current digest (or absent)')
        print('changed' if deploy(Path(sys.argv[1]), sys.argv[2]) else 'unchanged')
    except Exception as error:
        sys.exit('HAPI network stage refused: ' + str(error))
