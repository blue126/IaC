#!/bin/bash
# Controller wrapper and Home Assistant helper contracts against a stub batch; no SSH, Docker or PBS access.
# Needs Linux (setsid, flock, /proc). From macOS run it in a container, for example:
#   docker run --rm --init -v "$PWD":/src:ro python:3.13-slim bash -c 'cp -r /src /w && cd /w && bash tests/gateway-backup/gateway-backup-ctl-test.sh'
# Set CTL_TEST_BUSYBOX=1 to use BusyBox applets as on the gateway (Alpine's BusyBox has them all):
#   docker run --rm --init -v "$PWD":/src:ro python:3.13-alpine sh -c 'apk add -q bash && cp -r /src /w && cd /w && CTL_TEST_BUSYBOX=1 bash tests/gateway-backup/gateway-backup-ctl-test.sh'
set -euo pipefail
for tool in setsid flock python3; do
    command -v "${tool}" >/dev/null || { printf 'ERROR: %s is required; run this test on Linux\n' "${tool}" >&2; exit 1; }
done
[[ -r /proc/self/cmdline ]] || { printf 'ERROR: /proc is required; run this test on Linux\n' >&2; exit 1; }
repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
export CTL_TEST_REPO="${repo}"
export CTL_TEST_ROOT
CTL_TEST_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/gateway-backup-ctl-test.XXXXXXXX")"
mkdir "${CTL_TEST_ROOT}/bin"
if [[ -n "${CTL_TEST_BUSYBOX:-}" ]]; then
    applets="$(busybox --list)"
    for applet in setsid flock sleep grep tail cat mv date mkdir sh; do
        grep -qx "${applet}" <<<"${applets}" || { printf 'ERROR: this BusyBox lacks the %s applet\n' "${applet}" >&2; exit 1; }
        ln -s "$(command -v busybox)" "${CTL_TEST_ROOT}/bin/${applet}"
    done
fi

python3 - <<'PY'
import fcntl, json, os, pathlib, shlex, signal, stat, subprocess, time
repo = pathlib.Path(os.environ['CTL_TEST_REPO'])
root = pathlib.Path(os.environ['CTL_TEST_ROOT'])
path = str(root / 'bin') + ':' + os.environ['PATH']
token = 'fictional-token-5ecret'
repository = 'fixture@pbs!ha@pbs.invalid:backup'
fingerprint = ':'.join(['aa'] * 32)
cases = 0

stub = r'''#!/bin/bash
# Stub batch: record what the runner passed, then hold until released or cancelled.
case_dir=CASE_DIR
printf '%s\n' "$@" >"${case_dir}/batch-args"
env | grep '^PBS_' | sort >"${case_dir}/batch-env"
trap 'echo "ERROR: Batch cancelled (exit 143); not run: later"; touch "${case_dir}/batch-cancelled"; exit 143' TERM
printf '%s\n' "$$" >"${case_dir}/batch-pid"
echo 'Batch order: stub'
while [[ ! -f "${case_dir}/release" ]]; do sleep 0.05; done
cat "${case_dir}/release-output" 2>/dev/null || true
exit "$(cat "${case_dir}/release")"
'''

def fixture(configured=True):
    global cases
    cases += 1
    c = root / f'{cases:02d}'
    backup = c / 'gateway-backup'
    backup.mkdir(parents=True)
    (c / 'lock').mkdir()
    (backup / 'gateway-backup.sh').write_text(stub.replace('CASE_DIR', shlex.quote(str(c))))
    source = (repo / 'scripts/gateway-backup/gateway-backup-ctl.sh').read_text()
    replacements = {'backup_dir=/mnt/data/gateway-backup\n': f'backup_dir={shlex.quote(str(backup))}\n',
                    'batch_lock=/var/lock/gateway-backup.lock\n': f'batch_lock={shlex.quote(str(c / "lock/gateway-backup.lock"))}\n'}
    if configured:
        replacements.update({"pbs_repository=''\n": f"pbs_repository='{repository}'\n",
                             "pbs_fingerprint=''\n": f"pbs_fingerprint='{fingerprint}'\n"})
    for old, new in replacements.items():
        assert source.count(old) == 1, old
        source = source.replace(old, new)
    (backup / 'gateway-backup-ctl.sh').write_text(source)
    return c

def ctl(c, *args, stdin='', ssh=None):
    env = {k: v for k, v in os.environ.items() if not k.startswith(('PBS_', 'SSH_'))}
    env['PATH'] = path
    if ssh is not None: env['SSH_ORIGINAL_COMMAND'] = ssh
    # capture_output waits for EOF: a run that kept SSH's stdio open would hit the timeout.
    return subprocess.run(['/bin/bash', str(c / 'gateway-backup/gateway-backup-ctl.sh'), *args],
                          input=stdin, capture_output=True, text=True, timeout=10, env=env)

def runs(c): return c / 'gateway-backup/runs'
def wait_for(predicate, label, timeout=5):
    deadline = time.monotonic() + timeout
    while not predicate():
        assert time.monotonic() < deadline, label
        time.sleep(0.02)
def started(c, run_id, **kw):
    for marker in ('batch-pid', 'release'):
        (c / marker).unlink(missing_ok=True)
    t0 = time.monotonic()
    result = ctl(c, 'start', run_id, **kw)
    assert result.returncode == 0 and result.stdout == f'started run_id={run_id}\n', result
    assert time.monotonic() - t0 < 4, 'start must return without waiting for the batch'
    wait_for((c / 'batch-pid').exists, 'stub batch did not start')
    return result
def finished(c, run_id):
    wait_for(lambda: ctl(c, 'status', run_id).stdout.startswith('exit='), 'run did not record its exit')
    return ctl(c, 'status', run_id).stdout
def pid(c, run_id, name): return int((runs(c) / run_id / name).read_text())
def passed(label): print('PASS: ' + label, flush=True)

c = fixture()
started(c, 'r1', stdin=token + '\n')
assert ctl(c, 'status', 'r1').stdout == 'running\n'
assert (c / 'batch-args').read_text().split() == ['backup', 'all']
env = dict(line.split('=', 1) for line in (c / 'batch-env').read_text().splitlines())
assert env == {'PBS_FINGERPRINT': fingerprint, 'PBS_PASSWORD': token, 'PBS_REPOSITORY': repository}, env
for name in ('runner.pid', 'pid'):
    process = pid(c, 'r1', name)
    assert token not in pathlib.Path(f'/proc/{process}/cmdline').read_bytes().decode()
    assert os.getsid(process) != os.getsid(0), 'run must leave the caller session'
assert all(stat.S_IMODE(p.stat().st_mode) == 0o700 for p in (runs(c), runs(c) / 'r1'))
assert not any(token in p.read_text() for p in runs(c).rglob('*') if p.is_file())
passed('start returns at once, detaches the batch into its own session, passes the token only through the environment and never writes it')

for run_id in ('r2', 'r1'):
    result = ctl(c, 'start', run_id, stdin=token + '\n')
    assert result.returncode == 3 and 'busy: an earlier controller run is still active' in result.stderr, result
assert not (runs(c) / 'r2').exists()
(c / 'release-output').write_text('ERROR: Batch finished with failures: 4/5 completed; failed: hermes(exit 23)\n')
(c / 'release').write_text('23')
assert finished(c, 'r1') == 'exit=23\nsummary=ERROR: Batch finished with failures: 4/5 completed; failed: hermes(exit 23)\n'
assert all((runs(c) / 'r1' / name).exists() for name in ('started', 'finished'))
result = ctl(c, 'start', 'r1', stdin=token + '\n')
assert result.returncode == 3 and 'run_id already used: r1' in result.stderr
passed('a second start is refused while a run is active, the exit code and batch summary are reported, and a run_id is never reused')

started(c, 'r3', stdin=token)
cancel = ctl(c, 'cancel', 'r3')
assert cancel.returncode == 0 and cancel.stdout == 'cancelling\n', cancel
assert finished(c, 'r3') == 'exit=143\nsummary=ERROR: Batch cancelled (exit 143); not run: later\n'
assert (c / 'batch-cancelled').exists()
assert ctl(c, 'cancel', 'r3').stdout.startswith('exit=143\n')
passed('a token without a trailing newline starts a new run; cancel sends TERM to the batch and later reports its recorded exit')

c = fixture()
started(c, 's1', stdin=token + '\n', ssh='start s1')
assert ctl(c, ssh='status s1').stdout == 'running\n'
for bad in ('', 'status', 'status s1 extra', 'status s1; id', 'status $(id)', 'status s1\nid', '_run s1',
            'restart s1', 'status ../s1', 'start  s1', 'STATUS s1', 'status -s1'):
    result = ctl(c, ssh=bad)
    assert result.returncode == 2 and 'Usage' in result.stderr and not result.stdout, (bad, result)
(c / 'release').write_text('0')
assert finished(c, 's1') == 'exit=0\n'
passed('forced-command mode accepts only "<start|status|cancel> <run_id>" and rejects shell syntax, extra words and internal verbs')

c = fixture()
for args in (('start', ''), ('start', '../x'), ('start', '.hidden'), ('start', '-x'), ('start', 'a/b'),
             ('start', 'a b'), ('start', 'x' * 65), ('start',), ('start', 'a', 'b'), ('restart', 'a'), ()):
    result = ctl(c, *args, stdin=token + '\n')
    assert result.returncode == 2 and 'Usage' in result.stderr, (args, result)
result = ctl(c, 'start', 'e1', stdin='')
assert result.returncode == 2 and 'Supply the PBS token' in result.stderr
assert not runs(c).exists()
c = fixture(configured=False)
result = ctl(c, 'start', 'e2', stdin=token + '\n')
assert result.returncode == 1 and 'pbs_repository is not configured' in result.stderr and not runs(c).exists()
passed('invalid run_ids, verbs and argument counts, an empty token and a missing repository are rejected before any run exists')

c = fixture()
with (c / 'lock/gateway-backup.lock').open('w') as lock:
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    result = ctl(c, 'start', 'm1', stdin=token + '\n')
assert result.returncode == 3 and 'busy: a gateway backup is already running' in result.stderr
assert not (runs(c) / 'm1').exists()
started(c, 'm2', stdin=token + '\n')
(c / 'release').write_text('0')
assert finished(c, 'm2') == 'exit=0\n'
passed('a manual batch holding the backup lock blocks start; once released a run proceeds')

c = fixture()
assert ctl(c, 'status', 'nope').stdout == 'unknown\nreason=no such run\n'
assert ctl(c, 'cancel', 'nope').stdout == 'unknown\nreason=no such run\n'
started(c, 'o1', stdin=token + '\n')
os.kill(pid(c, 'o1', 'runner.pid'), signal.SIGKILL)
time.sleep(0.2)
assert ctl(c, 'status', 'o1').stdout == 'running\n', 'an orphaned batch is still running'
result = ctl(c, 'start', 'o2', stdin=token + '\n')
assert result.returncode == 3 and 'busy' in result.stderr, 'the orphaned batch still holds the run lock'
assert ctl(c, 'cancel', 'o1').stdout == 'cancelling\n'
wait_for((c / 'batch-cancelled').exists, 'orphaned batch was not cancelled')
wait_for(lambda: ctl(c, 'status', 'o1').stdout.startswith('unknown'), 'lost run must become unknown')
assert ctl(c, 'status', 'o1').stdout == 'unknown\nreason=no live process and no recorded exit\n'
started(c, 'o3', stdin=token + '\n')
os.kill(pid(c, 'o3', 'pid'), signal.SIGKILL)
wait_for(lambda: ctl(c, 'status', 'o3').stdout.startswith('exit='), 'killed batch must still record an exit')
assert ctl(c, 'status', 'o3').stdout == 'exit=137\n'
passed('unknown runs, an orphaned batch (still running, still blocking, still cancellable) and a lost run are reported truthfully')

h = root / 'ha'
(h / 'bin').mkdir(parents=True)
(h / 'bin/ssh').write_text(f'''#!/usr/bin/env python3
import json, sys
json.dump(sys.argv[1:], open({str(h / "ssh-args.json")!r}, 'w'))
open({str(h / "ssh-stdin")!r}, 'w').write(sys.stdin.read())
print('fake-ok')
''')
(h / 'bin/ssh').chmod(0o755)
(h / 'token').write_text(token + '\n')
helper = (repo / 'scripts/gateway-backup/ha-gateway-backup.sh').read_text()
settings = {'key': h / 'key', 'known_hosts': h / 'known_hosts', 'token_file': h / 'token'}
for name, value in settings.items():
    old = next(line for line in helper.splitlines() if line.startswith(name + '=/config/'))
    helper = helper.replace(old + '\n', f'{name}={value}\n')
(h / 'ha-gateway-backup.sh').write_text(helper)
def ha(*args):
    for name in ('ssh-args.json', 'ssh-stdin'): (h / name).unlink(missing_ok=True)
    env = dict(os.environ, PATH=str(h / 'bin') + ':' + path)
    return subprocess.run(['sh', str(h / 'ha-gateway-backup.sh'), *args], capture_output=True, text=True, timeout=10, env=env)
options = ['-i', str(h / 'key'), '-o', 'IdentitiesOnly=yes', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10',
           '-o', 'StrictHostKeyChecking=yes', '-o', f'UserKnownHostsFile={h / "known_hosts"}', 'root@192.168.1.1']
for action in ('start', 'status', 'cancel'):
    result = ha(action, '20261008T234500')
    assert result.returncode == 0 and result.stdout == 'fake-ok\n', result
    args = json.loads((h / 'ssh-args.json').read_text())
    assert args == options + [action, '20261008T234500'], args
    assert (h / 'ssh-stdin').read_text() == (token + '\n' if action == 'start' else '')
for args in (('restart', 'a'), ('start', ''), ('start', '../x'), ('start', '-oProxyCommand=x'), ('start', 'a b'),
             ('start', 'x' * 65), ('start',), ('start', 'a', 'b')):
    result = ha(*args)
    assert result.returncode == 2 and 'Usage' in result.stderr and not (h / 'ssh-args.json').exists(), (args, result)
(h / 'token').unlink()
result = ha('start', 'a1')
assert result.returncode == 1 and 'Missing PBS token file' in result.stderr and not (h / 'ssh-args.json').exists()
passed('HA helper sends only "<action> <run_id>" with strict host checking, feeds the token on stdin for start only, and rejects bad input before SSH')
print(f'Controller matrix passed: {cases} fixtures retained at {root}', flush=True)
PY
