#!/usr/bin/env python3
"""Render non-secret fixtures to a caller-selected temporary directory."""
import importlib.util
from pathlib import Path
import sys
spec = importlib.util.spec_from_file_location('offline', Path(__file__).with_name('test-offline.py'))
offline = importlib.util.module_from_spec(spec)
spec.loader.exec_module(offline)
out = Path(sys.argv[1])
out.mkdir(parents=True, exist_ok=True)
for template in ['nftables.conf.j2', 'pve-nftables.conf.j2', 'sshd-config.j2', 'netplan.yml.j2']:
    (out / template.removesuffix('.j2')).write_text(offline.render(template))
