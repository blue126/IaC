#!/usr/bin/python3
"""PVE hook: refuse HAPI starts unless the external boundary verifies."""
import subprocess
import sys

if len(sys.argv) != 3 or not sys.argv[1].isdigit():
    sys.exit('Invalid PVE hook invocation')
if sys.argv[2] == 'pre-start':
    subprocess.run(['/usr/bin/python3', '/usr/local/lib/hapi-network.py', 'hook',
                    '--vmid', sys.argv[1]], check=True)
