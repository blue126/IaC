#!/bin/bash
# Focused command contracts with fictional files; no live Docker/PBS access.
set -euo pipefail
repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
export BACKUP_TEST_REPO="${repo}"
export BACKUP_TEST_ROOT
BACKUP_TEST_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/gateway-backup-test.XXXXXXXX")"
mkdir "${BACKUP_TEST_ROOT}/bin"

cat >"${BACKUP_TEST_ROOT}/bin/fixture-command" <<'PY'
#!/usr/bin/env python3
import fcntl, hashlib, json, os, pathlib, shutil, signal, stat, sys, time
root = pathlib.Path(os.environ['BACKUP_CASE'])
args = sys.argv[1:]
tool = pathlib.Path(sys.argv[0]).name
with (root / 'calls.jsonl').open('a') as log:
    log.write(json.dumps([tool, *args]) + '\n')
state = json.loads((root / 'state.json').read_text())
scopes = json.loads((root / 'scopes.json').read_text())
owners = {n: b for b, names in scopes.items() for n in names}
def image_id(name): return 'sha256:' + hashlib.sha256(name.encode()).hexdigest()
if tool == 'flock':
    assert args == ['-n', '9']
    try: fcntl.flock(9, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError: sys.exit(1)
    sys.exit(0)
# Every Docker/client/cleanup call must retain the same global lock.
lockfile = root / 'locks/gateway-backup.lock'
assert os.fstat(9).st_ino == lockfile.stat().st_ino
with lockfile.open() as contender:
    try: fcntl.flock(contender, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError: pass
    else: raise AssertionError('Global lock was released before cleanup completed')
active = root / 'active-business'
if tool == 'docker' and args[:2] != ['image', 'inspect']:
    business = owners[args[-1]]
    assert business in json.loads((root / 'allowed.json').read_text()), business
    if not active.exists() or active.read_text() != business:
        assert (root / 'state.json').read_text() == (root / 'original.json').read_text(), 'Next business began before original states were restored'
        assert not list((root / 'tmp').iterdir()), 'Next business began before metadata cleanup'
        active.write_text(business)
else:
    business = active.read_text()
selected = scopes[business]
def enabled(flag):
    return os.environ.get(flag) and os.environ.get('AT_BUSINESS', business) == business
def signal_cleanup_group():
    group = os.getpgrp()
    # Only the adapter's private session may be signalled, never the test runner.
    assert group != int(os.environ['BACKUP_TEST_RUNNER_PGID'])
    assert os.getsid(0) == group == os.getppid()
    os.killpg(group, getattr(signal, 'SIG' + os.environ['GROUP_SIGNAL']))
    time.sleep(0.1)
    (root / 'group-cleanup-survived').write_text(tool)
if tool == 'rm':
    assert args[:2] == ['-rf', '--'] and len(args) == 3
    assert pathlib.Path(args[2]).parent == root / 'tmp'
    if enabled('SIGNAL_CLEANUP_GROUP') and os.environ['SIGNAL_CLEANUP_GROUP'] == 'rm': signal_cleanup_group()
    if enabled('FAIL_CLEANUP'): sys.exit(20)
    shutil.rmtree(args[2])
    sys.exit(0)
if tool == 'docker':
    assert os.environ['DOCKER_HOST'] == 'unix:///var/run/docker.sock'
    assert 'DOCKER_CONTEXT' not in os.environ
    if args[0] == 'inspect':
        if '--format' not in args:
            assert args[1:] == selected
            if enabled('FAIL_METADATA'): sys.exit(18)
            print(json.dumps([{'Name': n, 'Image': image_id(n), 'State': {'Running': state[n]},
                               'Config': {'Env': ['FICTIONAL=private']}} for n in args[1:]]))
        else:
            if args[2] == '{{.Image}}':
                assert args[3:] == selected
                if enabled('FAIL_IMAGE_IDS'): sys.exit(22)
                print('\n'.join(image_id(n) for n in selected))
                sys.exit(0)
            template, name = args[2:]
            assert name in state, name
            if '.Mounts' in template:
                destination = {'hermes': '/opt/hermes', 'xiaozhi-esp32-server-redis': '/data'}[name]
                assert 'eq .Type "volume"' in template and 'eq .Destination "' + destination + '"' in template
                volume = 'hermes-volume-data' if name == 'hermes' else 'redis-volume-data'
                if not enabled('MISSING_VOLUME'): print(root / volume)
            elif '.State.Paused' in template:
                print(str(state[name]).lower(), 'false', 'false')
            elif '.State.ExitCode' in template:
                print(os.environ.get('DB_EXIT_STATE', '1 false') if os.environ.get('UNCLEAN_DB') == name else '0 false')
            else:
                assert template == '{{.State.Running}}'
                print(str(state[name]).lower())
    elif args[:2] == ['image', 'inspect']:
        if enabled('FAIL_IMAGE_METADATA'): sys.exit(24)
        if not args[2:]: sys.exit(2)
        assert args[2:] == [image_id(n) for n in selected]
        print(json.dumps([{'Id': image_id(n), 'RepoDigests': ['fixture/' + n + '@' + image_id(n)],
                           'Os': 'linux', 'Architecture': 'arm64'} for n in selected]))
    else:
        assert args[0] in ('stop', 'start'), args
        name = args[-1]
        assert name in selected
        if args[0] == 'stop':
            assert args[1:3] == ['--time', '60']
            state[name] = False
            (root / 'state.json').write_text(json.dumps(state))
            if os.environ.get('FAIL_STOP') == name: sys.exit(17)
        else:
            if (root / 'client-pid').exists():
                try: os.kill(int((root / 'client-pid').read_text()), 0)
                except ProcessLookupError: pass
                else: raise AssertionError('Restart began before the native backup client exited')
            if enabled('SIGNAL_CLEANUP') and name == selected[0]:
                signum = getattr(signal, 'SIG' + os.environ['SIGNAL_CLEANUP']) if os.environ['SIGNAL_CLEANUP'] != '1' else signal.SIGTERM
                os.kill(os.getppid(), signum)
                time.sleep(0.1)
            if enabled('SIGNAL_CLEANUP_GROUP') and os.environ['SIGNAL_CLEANUP_GROUP'] == 'start' and name == selected[0]:
                signal_cleanup_group()
            if os.environ.get('FAIL_START') == name: sys.exit(19)
            state[name] = True
            (root / 'state.json').write_text(json.dumps(state))
else:
    assert tool == 'proxmox-backup-client'
    assert os.environ['PBS_REPOSITORY'] == 'fixture@pbs!backup@pbs.invalid:backup'
    assert os.environ['PBS_PASSWORD'] == 'fictional-token'
    assert os.environ['PBS_FINGERPRINT'] == ':'.join(['aa'] * 32)
    if args[:2] == ['snapshot', 'list']:
        assert args[2:] == ['--output-format', 'json']
        if enabled('FAIL_PBS'): sys.exit(11)
        print('[]')
    else:
        assert args[0] == 'backup', args
        assert all(not state[n] for n in selected), 'Backup must run while every selected container is stopped'
        metadata = pathlib.Path(next(a.split(':', 1)[1] for a in args if a.startswith('metadata.pxar:')))
        assert stat.S_IMODE(metadata.stat().st_mode) == 0o700
        assert {p.name for p in metadata.iterdir()} == {'docker-inspect.json', 'docker-images.json', 'running-containers.txt'}
        assert all(stat.S_IMODE(p.stat().st_mode) == 0o600 for p in metadata.iterdir())
        records = json.loads((metadata / 'docker-inspect.json').read_text())
        original = json.loads((root / 'original.json').read_text())
        assert [v['Name'] for v in records] == selected
        assert all(v['State']['Running'] == original[v['Name']] for v in records)
        images = json.loads((metadata / 'docker-images.json').read_text())
        assert [i['Id'] for i in images] == [v['Image'] for v in records]
        assert all(i['RepoDigests'] and i['Os'] == 'linux' and i['Architecture'] == 'arm64' for i in images)
        assert (metadata / 'running-containers.txt').read_text().split() == [n for n in selected if original[n]]
        (root / 'backup-args.json').write_text(json.dumps(args))
        with (root / 'backups.jsonl').open('a') as log: log.write(json.dumps(args) + '\n')
        (root / 'metadata-path').write_text(str(metadata))
        (root / 'client-pid').write_text(str(os.getpid()))
        if enabled('HOLD_BACKUP'):
            (root / 'client-ready').touch()
            deadline = time.monotonic() + 5
            while not (root / 'release-client').exists() and time.monotonic() < deadline: time.sleep(0.01)
            assert (root / 'release-client').exists(), 'Concurrent fixture did not release the client'
        if enabled('SIGNAL_BACKUP'):
            signum = getattr(signal, 'SIG' + os.environ['SIGNAL_BACKUP'])
            received = []
            signal.signal(signum, lambda number, frame: received.append(number))
            (root / 'client-ready').touch()
            if not os.environ.get('SIGNAL_PID_WINDOW'): os.kill(os.getppid(), signum)
            deadline = time.monotonic() + 3
            while not received and time.monotonic() < deadline: time.sleep(0.01)
            assert received == [signum], 'Cancellation was not forwarded to the native client'
            # Keep reading after cancellation, then exit successfully: the parent must wait.
            time.sleep(0.2)
            assert all(not json.loads((root / 'state.json').read_text())[n] for n in selected)
            (root / 'client-cancelled').write_text(str(signum))
            sys.exit(0)
        if enabled('FAIL_BACKUP'): sys.exit(23)
PY
chmod +x "${BACKUP_TEST_ROOT}/bin/fixture-command"
ln -s fixture-command "${BACKUP_TEST_ROOT}/bin/docker"
ln -s fixture-command "${BACKUP_TEST_ROOT}/bin/flock"
ln -s fixture-command "${BACKUP_TEST_ROOT}/bin/proxmox-backup-client"
ln -s fixture-command "${BACKUP_TEST_ROOT}/bin/rm"

python3 - <<'PY'
import fcntl, json, os, pathlib, shlex, subprocess, time
repo = pathlib.Path(os.environ['BACKUP_TEST_REPO'])
root = pathlib.Path(os.environ['BACKUP_TEST_ROOT'])
businesses = {
    'xiaozhi': (['xiaozhi-esp32-server-db', 'xiaozhi-esp32-server-redis', 'xiaozhi-esp32-server', 'xiaozhi-esp32-server-web', 'xz-mqtt-gw'],
                [('xiaozhi', '/mnt/data/xiaozhi'), ('mqtt', '/mnt/data/xiaozhi-mqtt-gateway')]),
    'hermes': (['hermes', 'hermes-webui'], [('hermes', '/mnt/data/hermes')]),
    'open-webui': (['open-webui'], [('open-webui', '/mnt/data/open-webui')]),
    'codex-proxy': (['codex-proxy'], [('codex-proxy', '/mnt/data/codex-openai-proxy')]),
    'cn-proxy': (['cn-proxy'], [('cn-proxy', '/etc/sing-box')]),
    'qnetd-witness': (['qnetd-witness'], [('qnetd', '/mnt/data/qnetd')]),
    'youtube-mcp': (['youtube-mcp-youtube-mcp-1'], [('youtube-mcp', '/mnt/data/xiaozhi/youtube-mcp')]),
}
batch = ['xiaozhi', 'hermes', 'open-webui', 'codex-proxy', 'cn-proxy', 'youtube-mcp']
cases = 0

def rebase(r, path):
    return str(path).replace('/mnt/data', str(r / 'data')).replace('/etc/sing-box', str(r / 'sing-box'))

def fixture(business, stopped=()):
    global cases
    cases += 1
    r = root / f'{cases:02d}-{business}'
    (r / 'cli').mkdir(parents=True)
    (r / 'tmp').mkdir()
    (r / 'locks').mkdir()
    (r / 'business').write_text(business)
    for volume in ('redis-volume-data', 'hermes-volume-data'): (r / volume).mkdir()
    script = (repo / 'scripts/gateway-backup/gateway-backup.sh').read_text()
    assert script.count('lock_dir=/var/lock\n') == 1
    script = script.replace('lock_dir=/var/lock\n', f'lock_dir={shlex.quote(str(r / "locks"))}\n')
    (r / 'cli/gateway-backup.sh').write_text(rebase(r, script))
    assert {p.name for p in (r / 'cli').iterdir()} == {'gateway-backup.sh'}
    for _, paths in businesses.values():
        for _, path in paths: pathlib.Path(rebase(r, path)).mkdir(parents=True, exist_ok=True)
    (r / 'sing-box/ts-state').mkdir()
    (r / 'sing-box/ts-state/identity').write_text('fictional identity')
    (r / 'data/xiaozhi/youtube-mcp/independent-data').write_text('fictional youtube data')
    allowed = batch if business == 'all' else [business]
    state = {n: n not in stopped for names, _ in businesses.values() for n in names}
    state['unrelated-container'] = True
    for name, value in [('state', state), ('original', state), ('allowed', allowed),
                        ('scopes', {b: names for b, (names, _) in businesses.items()})]:
        (r / f'{name}.json').write_text(json.dumps(value))
    (r / 'calls.jsonl').touch()
    return r

def environment(r, **flags):
    env = {k: v for k, v in os.environ.items() if not k.startswith('PBS_')}
    env.update(PATH=str(root / 'bin') + ':' + os.environ['PATH'], BACKUP_CASE=str(r),
               TMPDIR=str(r / 'tmp'), DOCKER_HOST='tcp://remote.invalid:2376', DOCKER_CONTEXT='remote-production',
               BACKUP_TEST_RUNNER_PGID=str(os.getpgrp()),
               PBS_REPOSITORY='fixture@pbs!backup@pbs.invalid:backup',
               PBS_PASSWORD='fictional-token', PBS_FINGERPRINT=':'.join(['aa'] * 32))
    env.update({k: str(v) for k, v in flags.items()})
    return env

def run(r, business, expected=0, args=None, check_cleanup=True, **flags):
    env = environment(r, **flags)
    if flags.get('SIGNAL_PID_WINDOW'):
        # Pause the copied adapter at the exact fork/PID registration boundary.
        script = r / 'cli/gateway-backup.sh'
        source = script.read_text()
        assert source.count('backup_pid=$!\n') == 1
        injection = 'if [[ "${business}" == "${AT_BUSINESS:-${business}}" ]]; then\nwhile [[ ! -f "${BACKUP_CASE}/client-ready" ]]; do sleep 0.01; done\nkill -' + flags['SIGNAL_BACKUP'] + ' "$$"\nfi\n'
        script.write_text(source.replace('backup_pid=$!\n', injection + 'backup_pid=$!\n'))
    if flags.get('SIGNAL_CLEANUP_WINDOW'):
        # Cancel after cleanup arguments are captured but before its traps take over.
        script = r / 'cli/gateway-backup.sh'
        source = script.read_text()
        boundary = '    local rc="$1" container\n'
        assert source.count(boundary) == 1
        injection = '    if [[ "${business}" == "${AT_BUSINESS}" ]]; then kill -' + flags['SIGNAL_CLEANUP_WINDOW'] + ' "$$"; fi\n'
        script.write_text(source.replace(boundary, boundary + injection))
    if flags.get('SIGNAL_CLEANUP_RETURN'):
        # Deliver a late signal after cleanup reports its result but before return.
        script = r / 'cli/gateway-backup.sh'
        source = script.read_text()
        boundary = '    return "${rc}"\n'
        assert source.count(boundary) == 1
        injection = '    if [[ "${business}" == "${AT_BUSINESS}" ]]; then kill -TERM "$$"; fi\n'
        script.write_text(source.replace(boundary, injection + boundary))
    command = ['/bin/bash', str(r / 'cli/gateway-backup.sh')]
    command += args if args is not None else ['backup', business]
    result = subprocess.run(command, env=env, capture_output=True, text=True, timeout=10,
                            start_new_session=bool(flags.get('SIGNAL_CLEANUP_GROUP')))
    (r / 'result.log').write_text(result.stdout + result.stderr)
    assert (result.returncode != 0 if expected is None else result.returncode == expected), (r, result.returncode, result.stdout, result.stderr)
    if check_cleanup and not flags.get('FAIL_CLEANUP'):
        assert not list((r / 'tmp').iterdir()), 'Private metadata must be cleaned on success and failure'
    return result

def calls(r): return [json.loads(line) for line in (r / 'calls.jsonl').read_text().splitlines()]
def mutations(r): return [c for c in calls(r) if c[:2] in [['docker', 'stop'], ['docker', 'start'], ['proxmox-backup-client', 'backup']]]
def unchanged(r): assert (r / 'state.json').read_text() == (r / 'original.json').read_text()
def no_backup(r): assert not (r / 'backup-args.json').exists()
def passed(label): print('PASS: ' + label, flush=True)

for business, (names, paths) in businesses.items():
    stopped = ('xiaozhi-esp32-server-web',) if business == 'xiaozhi' else tuple(names) if business == 'qnetd-witness' else ()
    r = fixture(business, stopped)
    run(r, business)
    unchanged(r)
    args = json.loads((r / 'backup-args.json').read_text())
    expected_sources = [f'{archive}.pxar:{rebase(r, path)}' for archive, path in paths]
    if business in ('xiaozhi', 'hermes'):
        archive, volume = ('redis', 'redis-volume-data') if business == 'xiaozhi' else ('hermes-source', 'hermes-volume-data')
        expected_sources.append(archive + '.pxar:' + str(r / volume))
    expected_sources.append('metadata.pxar:' + (r / 'metadata-path').read_text())
    expected = ['backup', *expected_sources, '--backup-type', 'host', '--backup-id', 'gateway-' + business,
                '--crypt-mode', 'none']
    if business == 'xiaozhi': expected += ['--exclude', '/youtube-mcp']
    assert args == expected, (business, args)
    running = [n for n in names if n not in stopped]
    assert [c[-1] for c in calls(r) if c[:2] == ['docker', 'stop']] == list(reversed(running))
    assert [c[-1] for c in calls(r) if c[:2] == ['docker', 'start']] == running
    stages = [c[:2] for c in mutations(r)]
    assert stages == [['docker', 'stop']] * len(running) + [['proxmox-backup-client', 'backup']] + [['docker', 'start']] * len(running)
passed('seven independent groups and sources; local Docker override, Redis/Hermes volumes, CN identity, youtube exclusion, stop/start order and private container/image metadata')

r = fixture('xiaozhi')
run(r, 'xiaozhi', pbs_keyfile=str(r / 'missing-key'),
    PBS_ENCRYPTION_PASSWORD_FILE=str(r / 'missing-passphrase'),
    PBS_PASSWORD_FILE=str(r / 'missing-token-file'))
args = json.loads((r / 'backup-args.json').read_text())
assert args[args.index('--crypt-mode') + 1] == 'none' and '--keyfile' not in args
assert not any(c[:2] == ['proxmox-backup-client', 'key'] for c in calls(r))
unchanged(r)
passed('adapter command contract: no key inspection/keyfile option, explicit crypt-mode none despite obsolete key references')

for args in (['backup', 'unknown'], ['backup', '../xiaozhi'], ['restore', 'xiaozhi'],
             ['backup', 'xiaozhi', 'hermes'], ['backup', 'xiaozhi', '--config', 'unused.conf']):
    r = fixture('xiaozhi')
    run(r, 'xiaozhi', expected=2 if args[0] != 'backup' or len(args) != 2 else 1, args=args)
    assert not calls(r)
    unchanged(r)
passed('unknown/path-traversal business names, obsolete restore and multiple positional businesses rejected')

for variable in ('PBS_REPOSITORY', 'PBS_PASSWORD'):
    r = fixture('xiaozhi')
    result = run(r, 'xiaozhi', expected=1, **{variable: ''})
    assert variable in result.stderr
    assert not calls(r)
    unchanged(r)
passed('standalone script rejects missing PBS repository or token before Docker/PBS access')

r = fixture('xiaozhi')
with (r / 'locks/gateway-backup.lock').open('w') as lock:
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    result = run(r, 'xiaozhi', expected=1)
assert 'Another business backup is active' in result.stderr
assert calls(r) == [['flock', '-n', '9']]
unchanged(r)
passed('global lock contention rejects before state capture or downtime; lock held through all restarts and metadata cleanup')

for flags, code in [({'FAIL_PBS': 1}, 11), ({'MISSING_VOLUME': 1}, 1), ({'FAIL_METADATA': 1}, 18),
                    ({'FAIL_IMAGE_IDS': 1}, None), ({'FAIL_IMAGE_METADATA': 1}, None)]:
    r = fixture('xiaozhi')
    run(r, 'xiaozhi', expected=code, **flags)
    assert not mutations(r)
    unchanged(r)
for path in ('data/xiaozhi', 'redis-volume-data'):
    r = fixture('xiaozhi')
    (r / path).rename(r / ('unavailable-' + pathlib.Path(path).name))
    run(r, 'xiaozhi', expected=1)
    assert not mutations(r)
    unchanged(r)
passed('PBS/auth, missing directory/volume and container/image inspect failure reject before downtime')

for flags, code in [({'FAIL_BACKUP': 1}, 23), ({'FAIL_STOP': 'xiaozhi-esp32-server-redis'}, 17)]:
    r = fixture('xiaozhi', ('xiaozhi-esp32-server-web',))
    run(r, 'xiaozhi', expected=code, **flags)
    unchanged(r)
    if 'FAIL_STOP' in flags: no_backup(r)
passed('client/stop failures preserve errors and attempt original restarts')

for database in businesses['xiaozhi'][0][:2]:
    for exit_state in ('1 false', '0 true'):
        r = fixture('xiaozhi', ('xiaozhi-esp32-server-web',))
        run(r, 'xiaozhi', expected=1, UNCLEAN_DB=database, DB_EXIT_STATE=exit_state)
        no_backup(r)
        unchanged(r)
passed('MySQL and Redis independently reject non-OOM abnormal exit and OOM flags, then restore original states')

for sig, code in (('INT', 130), ('TERM', 143)):
    for window in (False, True):
        r = fixture('xiaozhi', ('xiaozhi-esp32-server-web',))
        run(r, 'xiaozhi', expected=code, SIGNAL_BACKUP=sig, SIGNAL_CLEANUP=1,
            **({'SIGNAL_PID_WINDOW': 1} if window else {}))
        assert (r / 'client-cancelled').exists()
        unchanged(r)
passed('INT/TERM and fork/PID-window cancellation wait for client exit 0, preserve 130/143 and ignore repeated cleanup TERM')

for failed_backup, expected in ((False, 1), (True, 23)):
    r = fixture('xiaozhi', ('xiaozhi-esp32-server-web',))
    result = run(r, 'xiaozhi', expected=expected, FAIL_START='xiaozhi-esp32-server-db', **({'FAIL_BACKUP': 1} if failed_backup else {}))
    assert 'Failed to restart xiaozhi-esp32-server-db' in result.stderr
    assert 'Backup completed:' not in result.stdout
    assert [c[-1] for c in calls(r) if c[:2] == ['docker', 'start']] == [n for n in businesses['xiaozhi'][0] if n != 'xiaozhi-esp32-server-web']
passed('restart failure is reported, other original restarts attempted, and original backup error preserved')

r = fixture('qnetd-witness')
result = run(r, 'qnetd-witness', expected=1)
assert 'separately arranged quorum maintenance window' in result.stderr
assert not mutations(r)
unchanged(r)
passed('running qnetd refuses automatic stop; stopped qnetd remains stopped after native backup')

r = fixture('all', ('xiaozhi-esp32-server-web', 'hermes-webui', 'cn-proxy'))
result = run(r, 'all')
unchanged(r)
backups = [json.loads(line) for line in (r / 'backups.jsonl').read_text().splitlines()]
assert len(backups) == len(batch)
original = json.loads((r / 'original.json').read_text())
expected_calls = []
for index, (business, args) in enumerate(zip(batch, backups), 1):
    names, paths = businesses[business]
    expected_sources = [f'{archive}.pxar:{rebase(r, path)}' for archive, path in paths]
    if business in ('xiaozhi', 'hermes'):
        archive, volume = ('redis', 'redis-volume-data') if business == 'xiaozhi' else ('hermes-source', 'hermes-volume-data')
        expected_sources.append(archive + '.pxar:' + str(r / volume))
    metadata_arg = next(a for a in args if a.startswith('metadata.pxar:'))
    assert not pathlib.Path(metadata_arg.split(':', 1)[1]).exists()
    expected = ['backup', *expected_sources, metadata_arg, '--backup-type', 'host', '--backup-id', 'gateway-' + business,
                '--crypt-mode', 'none']
    if business == 'xiaozhi': expected += ['--exclude', '/youtube-mcp']
    assert args == expected, (business, args)
    running = [n for n in names if original[n]]
    expected_calls += [['docker', 'stop', '--time', '60', n] for n in reversed(running)]
    expected_calls += [['proxmox-backup-client', *args]]
    expected_calls += [['docker', 'start', n] for n in running]
    assert f'Backup progress {index}/6: {business}' in result.stdout
    assert f'Backup completed: host/gateway-{business}.' in result.stdout
assert mutations(r) == expected_calls
assert 'qnetd-witness is excluded from all' in result.stdout
assert not any(n in call for call in calls(r) for n in ('qnetd-witness', 'unrelated-container'))
assert [c for c in calls(r) if c[0] == 'flock'] == [['flock', '-n', '9']]
passed('all executes the exact six-business stop/backup/start sequence under one lock, resets business options, retains stopped containers and excludes qnetd')

def stopped_at_hermes(r, result):
    assert 'host/gateway-hermes (exit ' in result.stderr
    assert 'Backup completed: host/gateway-hermes.' not in result.stdout
    assert 'Backup progress 3/' not in result.stdout
    untouched = [n for b in batch[2:] + ['qnetd-witness'] for n in businesses[b][0]] + ['unrelated-container']
    assert not any(n in call for call in calls(r) for n in untouched), calls(r)

for flags, code in [({'FAIL_PBS': 1}, 11), ({'FAIL_METADATA': 1}, 18), ({'FAIL_STOP': 'hermes-webui'}, 17),
                    ({'FAIL_BACKUP': 1}, 23), ({'FAIL_START': 'hermes'}, 1), ({'FAIL_CLEANUP': 1}, 1),
                    ({'FAIL_BACKUP': 1, 'FAIL_START': 'hermes', 'FAIL_CLEANUP': 1}, 23)]:
    r = fixture('all')
    result = run(r, 'all', expected=code, AT_BUSINESS='hermes', **flags)
    stopped_at_hermes(r, result)
    if not (flags.get('FAIL_PBS') or flags.get('FAIL_METADATA')):
        assert [c[-1] for c in calls(r) if c[:2] == ['docker', 'start'] and c[-1] in businesses['hermes'][0]] == businesses['hermes'][0]
    expected_state = json.loads((r / 'original.json').read_text())
    if flags.get('FAIL_START'): expected_state['hermes'] = False
    assert json.loads((r / 'state.json').read_text()) == expected_state
    if flags.get('FAIL_CLEANUP'):
        assert 'Could not remove private metadata:' in result.stderr
        assert len(list((r / 'tmp').iterdir())) == 1
passed('middle-business preflight, metadata, stop, backup, restart and cleanup failures stop the queue and preserve the original error')

for sig, code in (('INT', 130), ('TERM', 143)):
    for window in (False, True):
        r = fixture('all', ('xiaozhi-esp32-server-web',))
        result = run(r, 'all', expected=code, AT_BUSINESS='hermes', SIGNAL_BACKUP=sig, SIGNAL_CLEANUP=1,
                     **({'SIGNAL_PID_WINDOW': 1} if window else {}))
        assert (r / 'client-cancelled').exists()
        stopped_at_hermes(r, result)
        unchanged(r)
    r = fixture('all')
    result = run(r, 'all', expected=code, AT_BUSINESS='hermes', SIGNAL_CLEANUP=sig)
    stopped_at_hermes(r, result)
    unchanged(r)
    r = fixture('all')
    result = run(r, 'all', expected=code, AT_BUSINESS='hermes', SIGNAL_CLEANUP_WINDOW=sig)
    stopped_at_hermes(r, result)
    unchanged(r)
passed('middle-business INT/TERM, fork/PID-window, upload-to-cleanup handover and first cancellation during normal cleanup restore current states and prevent the next business')

for stage in ('start', 'rm'):
    for sig, code in (('INT', 130), ('TERM', 143)):
        stopped = tuple(businesses['hermes'][0]) if stage == 'rm' else ()
        r = fixture('all', stopped)
        result = run(r, 'all', expected=code, AT_BUSINESS='hermes', SIGNAL_CLEANUP_GROUP=stage, GROUP_SIGNAL=sig)
        assert (r / 'group-cleanup-survived').read_text() == ('docker' if stage == 'start' else 'rm')
        assert not any(message in result.stderr for message in ('Failed to restart', 'Could not remove private metadata'))
        stopped_at_hermes(r, result)
        unchanged(r)
passed('isolated-process-group INT/TERM during restart and metadata deletion completes cleanup, preserves original states and stops the batch')

r = fixture('all')
result = run(r, 'all', expected=23, AT_BUSINESS='hermes', FAIL_BACKUP=1, SIGNAL_CLEANUP_RETURN=1)
assert 'host/gateway-hermes (exit 23)' in result.stderr
stopped_at_hermes(r, result)
unchanged(r)
passed('late TERM between cleanup reporting and return preserves the existing backup error 23')

for first, target in (('all', 'hermes'), ('xiaozhi', 'xiaozhi')):
    r = fixture('all')
    command = ['/bin/bash', str(r / 'cli/gateway-backup.sh'), 'backup', first]
    process = subprocess.Popen(command, env=environment(r, HOLD_BACKUP=1, AT_BUSINESS=target),
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    deadline = time.monotonic() + 5
    while not (r / 'client-ready').exists() and process.poll() is None and time.monotonic() < deadline: time.sleep(0.01)
    try:
        assert (r / 'client-ready').exists(), 'First invocation did not reach the held native client'
        for contender in ('all', 'cn-proxy'):
            before = len(calls(r))
            rejected = run(r, contender, expected=1, check_cleanup=False)
            assert 'Another business backup is active' in rejected.stderr
            assert calls(r)[before:] == [['flock', '-n', '9']], 'Concurrent invocation touched Docker/PBS'
    finally:
        (r / 'release-client').touch()
        stdout, stderr = process.communicate(timeout=10)
        (r / 'concurrent-result.log').write_text(stdout + stderr)
    assert process.returncode == 0, (process.returncode, stdout, stderr)
    assert not list((r / 'tmp').iterdir())
    unchanged(r)
passed('live overlapping all/all, all/single, single/all and distinct-single invocations reject before Docker/PBS access')
print(f'Offline matrix passed: {cases} fixtures retained at {root}', flush=True)
PY
