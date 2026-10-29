#!/usr/bin/env python3
"""Offline contract tests; these do not prove real network/SSH enforcement."""
import copy
import base64
import struct
import importlib.util
import json
import os
import tempfile
from types import SimpleNamespace
from pathlib import Path
import unittest
from unittest.mock import patch
import jinja2
import yaml

ROOT = Path(__file__).resolve().parents[2]
ROLE = ROOT / 'ansible/roles/employee-access'
FIXTURE = json.loads((Path(__file__).parent / 'fixture.json').read_text())


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def render(name, config=None):
    c = config or FIXTURE
    env = jinja2.Environment(loader=jinja2.FileSystemLoader(ROLE / 'templates'), undefined=jinja2.StrictUndefined, trim_blocks=True)
    env.filters['bool'] = bool
    values = {'employee_access_' + k: v for k, v in c.items()}
    values.update(employee_access_vmid=c['gateway_vmid'], employee_access_admin_user='ubuntu', employee_access_wireguard_private_key='OFFLINE_PLACEHOLDER')
    return env.get_template(name).render(**values)


DISPATCH = module('dispatch', ROLE / 'files/employee-dispatch.py')
FIREWALL = module('firewall', ROLE / 'files/employee-firewall.py')
VALIDATOR = module('validator', ROLE / 'files/validate-inputs.py')


INVALID_GUARD = {'rule': {'family': 'inet', 'table': 'employee_access', 'chain': 'input', 'expr': [
    {'match': {'op': '==', 'left': {'ct': {'key': 'state'}}, 'right': 'invalid'}}, {'drop': None}]}}


class FirewallExtensionTests(unittest.TestCase):
    def test_only_the_exact_oci_rule_is_excluded_from_base_verification(self):
        base = {'nftables': [{'table': {'family': 'inet', 'name': 'employee_access'}}, copy.deepcopy(INVALID_GUARD)]}
        actual = [copy.deepcopy(base), {'nftables': []}]
        actual[0]['nftables'].append(copy.deepcopy(FIREWALL.OCI_EXTENSION_RULE))
        self.assertEqual(FIREWALL.without_known_extension(actual, True, True)[0], base)
        for damaged in ([], [dict(FIREWALL.OCI_EXTENSION_RULE, rule=dict(FIREWALL.OCI_EXTENSION_RULE['rule'], comment='other'))],
                        [dict(FIREWALL.OCI_EXTENSION_RULE, rule=dict(FIREWALL.OCI_EXTENSION_RULE['rule'], expr=[]))],
                        [FIREWALL.OCI_EXTENSION_RULE, FIREWALL.OCI_EXTENSION_RULE]):
            with self.subTest(damaged=damaged), self.assertRaises(RuntimeError):
                FIREWALL.without_known_extension([{'nftables': copy.deepcopy(damaged)}, {'nftables': []}], True, True)
        self.assertEqual(FIREWALL.without_known_extension([{'nftables': [FIREWALL.OCI_EXTENSION_RULE]}], False, True)[0]['nftables'], [FIREWALL.OCI_EXTENSION_RULE])


    def test_browser_extension_must_match_the_exact_expected_rule(self):
        base = {'nftables': [{'table': {'family': 'inet', 'name': 'employee_access'}}, copy.deepcopy(INVALID_GUARD)]}
        rules = [copy.deepcopy(FIREWALL.OCI_EXTENSION_RULE), copy.deepcopy(FIREWALL.BROWSER_EXTENSION_RULE)]
        actual = [{'nftables': base['nftables'] + rules}, {'nftables': []}]
        self.assertEqual(FIREWALL.without_known_extension(actual, True, True, True)[0], base)
        rules[1]['rule']['expr'][3]['match']['right'] = 22
        with self.assertRaises(RuntimeError):
            FIREWALL.without_known_extension([{'nftables': rules}, {'nftables': []}], True, True, True)


    def test_extension_cannot_bypass_the_invalid_state_guard(self):
        for rules in ([FIREWALL.OCI_EXTENSION_RULE, INVALID_GUARD], [FIREWALL.OCI_EXTENSION_RULE]):
            with self.subTest(rules=rules), self.assertRaises(RuntimeError):
                FIREWALL.without_known_extension([{'nftables':copy.deepcopy(rules)}, {'nftables':[]}], True, True)

    def test_known_extensions_do_not_hide_nat_drift(self):
        with tempfile.TemporaryDirectory() as directory:
            base=Path(directory);policy=base/'policy.nft';policy.write_text('synthetic-policy')
            expected=[{'nftables':[copy.deepcopy(INVALID_GUARD)]},{'nftables':[{'table':{'family':'ip','name':'employee_nat'}}]}]
            actual=copy.deepcopy(expected);actual[0]['nftables'].append(copy.deepcopy(FIREWALL.OCI_EXTENSION_RULE))
            applied=base/'applied.json';applied.write_text(json.dumps({'sha256':FIREWALL.hashlib.sha256(policy.read_bytes()).hexdigest(),'tables':expected}))
            marker=base/'oci.conf';marker.touch();missing=base/'browser.conf'
            original=Path.read_text
            def read_text(path,*args,**kwargs):
                return '1' if str(path)=='/proc/sys/net/ipv4/ip_forward' else original(path,*args,**kwargs)
            with patch.object(FIREWALL,'POLICY',policy), patch.object(FIREWALL,'APPLIED',applied), patch.object(FIREWALL,'OCI_EXTENSION_UNIT',marker), patch.object(FIREWALL,'BROWSER_EXTENSION_UNIT',missing), patch.object(FIREWALL,'snapshot',side_effect=lambda gateway:copy.deepcopy(actual)), patch.object(Path,'read_text',read_text):
                FIREWALL.verify(True)
                actual[1]['nftables']=[]
                with self.assertRaisesRegex(RuntimeError,'differs'):FIREWALL.verify(True)


class DispatchTests(unittest.TestCase):
    def setUp(self):
        self.mapping = {'employee': 'alice', 'host': '10.231.1.2', 'user': 'employee', 'enabled': True}

    def test_shell_is_only_fixed_destination(self):
        args = DISPATCH.command(self.mapping, '', True)
        self.assertEqual(args[-2:], ['-tt', 'employee@10.231.1.2'])
        for option in ['EscapeChar=none', 'EnableEscapeCommandline=no', 'StrictHostKeyChecking=yes', 'ProxyCommand=none', 'ProxyJump=none', 'ControlPath=none', 'IdentityAgent=none', 'KnownHostsCommand=none', 'ClearAllForwardings=yes']:
            self.assertIn(option, args)
        self.assertEqual(args[:3], ['/usr/bin/ssh', '-F', '/dev/null'])

    def test_sftp_is_fixed_subsystem_on_same_vm(self):
        args = DISPATCH.command(self.mapping, 'employee-sftp')
        self.assertEqual(args[-4:], ['-T', '-s', 'employee@10.231.1.2', 'sftp'])

    def test_mosh_starts_only_the_fixed_vm_shell(self):
        policy = {'address': '10.230.0.1', 'port_start': 60000, 'port_end': 60009}
        request = "employee-mosh 'new' '-c' '256' '-s' '-p' '60000:60009' '-l' 'LANG=en_US.UTF-8'"
        args = DISPATCH.mosh_command(self.mapping, request, policy)
        self.assertEqual(args[:9], ['/usr/bin/mosh-server', 'new', '-i', '10.230.0.1', '-p', '60000:60009', '-c', '256', '--'])
        self.assertEqual(args[-2:], ['-tt', 'employee@10.231.1.2'])
        alternate = 'exec employee-mosh -H abc123 -t -u ed-alice-laptop -- 60000 60009'
        self.assertEqual(DISPATCH.mosh_command(self.mapping, alternate, policy, 'ed-alice-laptop'), args)
        self.assertEqual(DISPATCH.mosh_command(self.mapping, 'employee-mosh --version', policy), ['/usr/bin/mosh-server', '--version'])
        for unsafe in ["employee-mosh 'new' '--' 'sh'", "employee-mosh 'new' '-p' '60010:60019'", "employee-mosh 'new'; id", "employee-mosh 'new' '-l' 'LANG=$(id)'"]:
            with self.subTest(request=unsafe), self.assertRaises(ValueError):
                DISPATCH.mosh_command(self.mapping, unsafe, policy)
        for unsafe in ['exec employee-mosh -H abc123 -t -u bob -- 60000 60009',
                       'exec employee-mosh -H abc123 -t -u ed-alice-laptop -- 60000 60099',
                       'exec employee-mosh -H abc123 -t -u ed-alice-laptop -- 60000 60009; id']:
            with self.subTest(request=unsafe), self.assertRaises(ValueError):
                DISPATCH.mosh_command(self.mapping, unsafe, policy, 'ed-alice-laptop')
        with self.assertRaises(ValueError):
            DISPATCH.mosh_command(self.mapping, request, dict(policy, address='0.0.0.0', port_end=61001))

    def test_mosh_timeout_is_bounded_and_passed_only_to_mosh(self):
        with tempfile.TemporaryDirectory() as directory:
            base=Path(directory);(base/'devices').mkdir();(base/'mosh-devices').mkdir()
            account='ed-alice-laptop';(base/'devices'/f'{account}.json').write_text(json.dumps(self.mapping))
            policy={'address':'10.230.0.1','port_start':60000,'port_end':60009,'network_timeout':86400}
            (base/'mosh-devices'/f'{account}.json').write_text(json.dumps(policy))
            with patch.object(DISPATCH,'ROOT',base), patch.object(DISPATCH.pwd,'getpwuid',return_value=SimpleNamespace(pw_name=account)), patch.object(DISPATCH.os,'execve') as execute:
                with patch.dict(os.environ,SSH_ORIGINAL_COMMAND='employee-mosh new -p 60000:60009'):
                    self.assertEqual(DISPATCH.main(),0)
                    self.assertEqual(execute.call_args.args[2]['MOSH_SERVER_NETWORK_TMOUT'],'86400')
                with patch.dict(os.environ,SSH_ORIGINAL_COMMAND=''):
                    self.assertEqual(DISPATCH.main(),0)
                    self.assertNotIn('MOSH_SERVER_NETWORK_TMOUT',execute.call_args.args[2])
            for value in (0,True,'86400',2592001):
                with self.subTest(value=value), self.assertRaises(ValueError):
                    DISPATCH.mosh_command(self.mapping,'employee-mosh new -p 60000:60009',dict(policy,network_timeout=value))

    def test_injections_and_unsupported_commands_are_rejected(self):
        for original in ['sftp', 'internal-sftp', '/usr/lib/openssh/sftp-server', 'employee-sftp;id', 'employee-sftp\n', 'ssh bob', 'sh', 'id', 'scp -t /tmp', '-L 8080:host:22', '$(id)', '`id`', 'env TERM=x bash']:
            with self.subTest(original=original), self.assertRaises(ValueError):
                DISPATCH.command(self.mapping, original)

    def test_mapping_corruption_and_revocation_fail_closed(self):
        for key, value in [('host', '-oProxyCommand=id'), ('user', 'employee;id'), ('employee', '../../bob'), ('enabled', False), ('enabled', 'true')]:
            value_map = dict(self.mapping, **{key: value})
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                DISPATCH.command(value_map, '')

    def test_missing_mapping_denies_without_exec(self):
        # getpwuid is a POSIX account lookup, not a password or credential.
        with patch.object(DISPATCH.pwd, 'getpwuid') as pw, patch.object(DISPATCH.os, 'execve') as execute:
            pw.return_value.pw_name = 'ed-missing'
            with patch.object(DISPATCH, 'ROOT', Path('/nonexistent-employee-test')):
                self.assertEqual(DISPATCH.main(), 1)
            execute.assert_not_called()


class InventoryTests(unittest.TestCase):
    def test_removing_prefix_does_not_allow_killing_system_accounts(self):
        tasks=yaml.safe_load((ROLE/'tasks/revoke.yml').read_text())
        policy=next(t['ansible.builtin.assert']['that'][0] for t in tasks if t['name']=='Refuse revocation of unmanaged operating-system accounts')
        expression=jinja2.Environment().compile_expression(policy)
        cases=[(None,True),(['*','995','995','','/var/empty/employee-access','/bin/sh'],True),(['x','0','0','','/root','/bin/bash'],False),(['x','1000','1000','','/home/ubuntu','/bin/bash'],False)]
        for account,expected in cases:
            self.assertEqual(bool(expression(ansible_facts={'getent_passwd':{'zhang171903992':account}},employee_revoke_account='zhang171903992')),expected)

    def test_mosh_cleanup_never_signals_unmanaged_accounts(self):
        tasks=yaml.safe_load((ROLE/'tasks/stop-mosh-sessions.yml').read_text())
        policy=next(t['ansible.builtin.assert']['that'] for t in tasks if t['name']=='Refuse to signal an unmanaged operating-system account')
        expression=jinja2.Environment().compile_expression(policy)
        for account,expected in ((None,True),(['*','995','995','','/var/empty/employee-access','/bin/sh'],True),(['x','0','0','','/root','/bin/bash'],False),(['x','1000','1000','','/home/ubuntu','/bin/bash'],False)):
            self.assertEqual(bool(expression(ansible_facts={'getent_passwd':{'device':account}},employee_mosh_account='device')),expected)

    def test_unprefixed_device_account_is_valid(self):
        data=copy.deepcopy(FIXTURE)
        device=data['devices'].pop('ed-alice-laptop')
        data['devices']['zhang171903992']=device
        data['mosh_devices']['zhang171903992']=data['mosh_devices'].pop('ed-alice-laptop')
        VALIDATOR.validate(data)

    def test_valid_fixture(self):
        VALIDATOR.validate(FIXTURE)

    def test_mosh_preflight_rejects_unknown_invalid_and_overlapping_ranges(self):
        for mutate in (
                lambda c:c['mosh_devices'].update(unknown={'port_start':60020,'port_end':60029}),
                lambda c:c['mosh_devices']['ed-alice-laptop'].update(port_start=1,port_end=65535),
                lambda c:c['mosh_devices']['ed-bob-laptop'].update(port_start=60009)):
            c=copy.deepcopy(FIXTURE);mutate(c)
            with self.subTest(config=c['mosh_devices']), self.assertRaises(ValueError):VALIDATOR.validate(c)
        c=copy.deepcopy(FIXTURE);c['devices']['ed-alice-laptop']['enabled']=False
        VALIDATOR.validate(c)
        self.assertNotIn('udp dport 60000-60009 accept',render('nftables.conf.j2',c))

    def test_emergency_policy_ignores_malformed_mosh_entries(self):
        c=copy.deepcopy(FIXTURE);c['networks']['alice']['disabled']=True
        c['mosh_devices'].update(unknown={'port_start':60020,'port_end':60029})
        c['mosh_devices']['ed-alice-laptop']={'port_start':1,'port_end':65535}
        c['validate_mosh']=False;VALIDATOR.validate(c)
        rules=render('nftables.conf.j2',c)
        self.assertIn('iifname "emp0" drop',rules)
        self.assertNotIn('udp dport 1-65535',rules)
        self.assertIn('udp dport 60010-60019 accept',rules)

    def test_unsafe_network_inputs_fail(self):
        mutations = [
            lambda c: c['networks']['alice'].update(interface='emp0" accept'),
            lambda c: c['networks']['bob'].update(bridge='vmbr501'),
            lambda c: c['networks']['bob'].update(vmid=501),
            lambda c: c['networks']['bob'].update(mac_address=c['networks']['alice']['mac_address']),
            lambda c: c.update(uplink_mac=c['networks']['alice']['mac_address']),
            lambda c: c['networks']['bob'].update(nic_slot=1),
            lambda c: c['networks']['alice'].update(ip='10.231.1.3'),
            lambda c: c['devices']['ed-bob-laptop'].update(address='10.230.0.2'),
            lambda c: c['devices']['ed-bob-laptop'].update(employee='missing'),
            lambda c: c['devices']['ed-bob-laptop'].update(ssh_public_key='ssh-ed25519 AAAA\ncommand="sh"'),
            lambda c: c.update(home_public_ipv4=[]),
            lambda c: c.update(maintenance_sources=['0.0.0.0/0']),
            lambda c: c.update(maintenance_sources=['10.230.0.2/32']),
            lambda c: c.update(dns_server='192.168.50.1'),
        ]
        for mutate in mutations:
            value = copy.deepcopy(FIXTURE)
            mutate(value)
            with self.subTest(value=value), self.assertRaises(ValueError):
                VALIDATOR.validate(value)

    def test_public_key_wire_structure(self):
        valid = FIXTURE['devices']['ed-alice-laptop']['ssh_public_key']
        wire = base64.b64decode(valid.split()[1])
        mutations = [b'', wire[:-1], wire + b'x', wire.replace(b'ssh-ed25519', b'ssh-ecdsa00'), struct.pack('!I', 500) + wire[4:]]
        for damaged in mutations:
            with self.subTest(wire=damaged), self.assertRaises(ValueError):
                VALIDATOR.public_key('ssh-ed25519 ' + base64.b64encode(damaged).decode())
        VALIDATOR.public_key(valid)

    def test_boundary_structure_does_not_require_first_boot_host_keys(self):
        config = copy.deepcopy(FIXTURE)
        config.update(host_keys={}, require_host_keys=False)
        VALIDATOR.validate(config)
        config['networks']['alice']['interface'] = 'emp9'
        with self.assertRaises(ValueError):
            VALIDATOR.validate(config)

    def test_uplink_gateway_outside_subnet_rejected(self):
        config = copy.deepcopy(FIXTURE)
        config['uplink_gateway'] = '192.168.70.1'
        with self.assertRaises(ValueError):
            VALIDATOR.validate(config)


class PolicyRenderTests(unittest.TestCase):
    def test_standard_nftables_loads_before_employee_policy(self):
        import configparser
        unit = configparser.ConfigParser()
        unit.read_string(render('firewall.service.j2'))
        self.assertIn('nftables.service', unit['Unit']['After'].split())
        self.assertNotIn('nftables.service', unit['Unit'].get('Before', '').split())
        self.assertNotIn('ExecStartPre', unit['Service'])

    def test_templates_render_strictly(self):
        for path in (ROLE / 'templates').glob('*.j2'):
            with self.subTest(template=path.name):
                self.assertTrue(render(path.name).strip())

    def test_network_policy_covers_protected_paths(self):
        rules = render('nftables.conf.j2')
        for expected in ['meta nfproto ipv6 drop', 'iifname "wg-employee" drop', 'oifname "wg-employee" drop', '198.51.100.20/32', '203.0.113.0/28', '100.64.0.0/10', '192.168.0.0/16', 'iifname "emp0" ip saddr != 10.231.1.2 drop', 'iifname "emp0" ip daddr @protected4 drop', 'iifname "emp0" oifname "employee-uplink" accept', 'tcp sport 22 ct state established accept']:
            self.assertIn(expected, rules)
        self.assertLess(rules.index('iifname "emp0" ip daddr @protected4 drop'), rules.index('iifname "emp0" oifname "employee-uplink" accept'))
        self.assertNotIn('flush ruleset', rules)

    def test_mosh_udp_is_limited_to_one_device_inside_wireguard(self):
        rules = render('nftables.conf.j2')
        self.assertIn('iifname "wg-employee" ip saddr 10.230.0.2 ip daddr 10.230.0.1 udp dport 60000-60009 accept', rules)
        self.assertNotIn('ip saddr 10.230.0.3 ip daddr 10.230.0.1 udp dport', rules)
        self.assertIn('iifname "wg-employee" ip saddr 10.230.0.4 ip daddr 10.230.0.1 udp dport 60010-60019 accept', rules)
        disabled = copy.deepcopy(FIXTURE)
        disabled['devices']['ed-alice-laptop']['enabled'] = False
        self.assertNotIn('udp dport 60000-60009 accept', render('nftables.conf.j2', disabled))
        self.assertIn('udp dport 60010-60019 accept', render('nftables.conf.j2', disabled))

    def test_l2_boundary_binds_vm_port_address_and_gateway(self):
        rules = render('pve-nftables.conf.j2')
        self.assertIn('iifname "tap501i0" drop', rules)
        self.assertIn('iifname "tap501i0" oifname "tap500i1" ether saddr 02:00:00:00:01:02 ether type ip ip saddr 10.231.1.2 accept', rules)
        self.assertIn('arp saddr ip 10.231.1.2 arp daddr ip 10.231.1.1 accept', rules)
        self.assertNotIn('ether type ip6', rules)
        self.assertNotIn('flush ruleset', rules)

    def test_disabled_employee_loses_bridge_and_gateway_paths(self):
        config = copy.deepcopy(FIXTURE)
        config['networks']['alice']['disabled'] = True
        l2 = render('pve-nftables.conf.j2', config)
        inet = render('nftables.conf.j2', config)
        wg = render('wireguard.conf.j2', config)
        self.assertNotIn('iifname "tap501i0" oifname', l2)
        self.assertIn('iifname "tap501i0" drop', l2)
        self.assertIn('oifname "emp0" drop', inet)
        self.assertNotIn('oifname "emp0" ip daddr 10.231.1.2 tcp dport 22 accept', inet)
        self.assertNotIn('10.230.0.2/32', wg)
        self.assertNotIn('10.230.0.3/32', wg)
        self.assertIn('10.230.0.4/32', wg)

    def test_device_revocation_retains_other_devices(self):
        config = copy.deepcopy(FIXTURE)
        config['devices']['ed-alice-laptop']['enabled'] = False
        wg = render('wireguard.conf.j2', config)
        self.assertNotIn('10.230.0.2/32', wg)
        self.assertIn('10.230.0.3/32', wg)
        self.assertIn('10.230.0.4/32', wg)

    def test_stop_uses_pve_without_destroying_disks(self):
        tasks = (ROLE / 'tasks/disable.yml').read_text()
        self.assertIn('[qm, stop,', tasks)
        self.assertIn('--onboot', tasks)
        self.assertNotIn('qm, destroy', tasks)
        self.assertNotIn('purge', tasks)
        self.assertNotIn('unlink', tasks)
        self.assertIn('delegate_to: "{{ employee_access_pve_host }}"', tasks)
        revoke = (ROLE / 'tasks/revoke.yml').read_text()
        self.assertLess(revoke.index('Clear revoked device authorization'), revoke.index('Terminate both SSH legs'))
        self.assertIn('[pkill, -KILL, -u,', revoke)

    def test_revocation_verification_cannot_override_roster_or_skip_unknown_device(self):
        plays = yaml.safe_load((ROOT / 'ansible/playbooks/disable-employee-workspace.yml').read_text())
        tasks = plays[1]['tasks']
        self.assertFalse(any('ansible.builtin.include_vars' in task for task in tasks))
        guard = next(task for task in tasks if task['name'] == 'Reject a device verification with no matching identity')
        self.assertEqual(guard['ansible.builtin.assert']['that'], 'employee_verify_devices | length == 1')
        check = next(task for task in tasks if task['name'] == 'Verify target company identities have no active processes')
        self.assertEqual(check['loop'], '{{ employee_verify_devices }}')
        self.assertEqual(check['failed_when'], 'employee_disabled_processes.rc != 1')

    def test_workspace_uses_inventory_networks_across_plays(self):
        tasks = (ROOT / 'ansible/roles/employee-workspace/tasks/authorization.yml').read_text()
        self.assertIn('employee_access_networks_json | from_json', tasks)
        self.assertNotIn('].employee_access_networks[', tasks)

    def test_disabled_vm_remains_stopped_after_terraform_reconciliation(self):
        employee = (ROOT / 'terraform/proxmox/employee-workspace.tf').read_text()
        for field in ('started', 'on_boot'):
            self.assertRegex(employee, rf'(?m)^  {field}\s*= var\.employee_access\.boundary_ready && each\.value\.hook_bound && each\.value\.start_ready && !each\.value\.disabled$')
        self.assertRegex(employee, r'(?m)^    disconnected\s*= each\.value\.disabled$')

    def test_boundary_startup_is_scoped_to_employee_vms(self):
        pve_tasks = (ROLE / 'tasks/pve.yml').read_text()
        self.assertNotIn('pve-guests', pve_tasks)
        employee = (ROOT / 'terraform/proxmox/employee-workspace.tf').read_text()
        self.assertNotRegex(employee, r'(?m)^\s*hook_script_file_id\s*=')
        self.assertIn('initialization[0].user_account[0].keys, hook_script_file_id', employee)
        self.assertIn('proxmox_virtual_environment_file.employee_boundary_hook]', employee)
        hook_text = (ROOT / 'terraform/proxmox/employee-boundary-hook.py.tftpl').read_text()
        rendered = hook_text.replace('${vmid}', '501').replace('${gateway_tap}', 'tap500i1').replace('${disabled}', 'false')
        namespace = {'__name__': 'hook_test'}
        exec(compile(rendered, '<hook>', 'exec'), namespace)
        rule = {'rule': {'family': 'bridge', 'table': 'employee_boundary', 'chain': 'forward', 'expr': [{'match': {'op': '==', 'left': {'meta': {'key': 'iifname'}}, 'right': 'tap501i0'}}, {'drop': None}]}}
        self.assertTrue(namespace['has_port_drop']({'nftables': [{'chain': {'family': 'bridge', 'table': 'employee_boundary', 'name': 'forward', 'type': 'filter', 'hook': 'forward', 'prio': -200, 'policy': 'accept'}}, rule]}, 'forward', 'tap501i0', 'iifname'))
        self.assertFalse(namespace['has_port_drop']({'nftables': [{'chain': {'family': 'bridge', 'table': 'employee_boundary', 'name': 'forward', 'type': 'filter', 'hook': 'forward', 'prio': -200, 'policy': 'accept'}}, rule]}, 'forward', 'tap502i0', 'iifname'))
        self.assertFalse(namespace['has_port_drop']({'nftables': []}, 'forward', 'tap501i0', 'iifname'))

    def test_hook_denies_unready_wrong_target_and_disabled_starts(self):
        text = (ROOT / 'terraform/proxmox/employee-boundary-hook.py.tftpl').read_text()
        code = text.replace('$' + '{vmid}', '501').replace('$' + '{gateway_tap}', 'tap500i1').replace('$' + '{disabled}', 'false')
        context = {'__name__': 'hook_test'}
        exec(compile(code, '<hook>', 'exec'), context)
        rules = {'nftables': []}
        for chain, direction in [('input', 'iifname'), ('forward', 'iifname'), ('output', 'oifname')]:
            rules['nftables'].append({'chain': {'family': 'bridge', 'table': 'employee_boundary', 'name': chain, 'type': 'filter', 'hook': chain, 'prio': -200, 'policy': 'accept'}})
            for port in ['tap501i0', 'tap500i1']:
                rules['nftables'].append({'rule': {'family': 'bridge', 'table': 'employee_boundary', 'chain': chain, 'expr': [{'match': {'op': '==', 'left': {'meta': {'key': direction}}, 'right': port}}, {'drop': None}]}})
        with patch.object(context['sys'], 'argv', ['hook', '501', 'pre-start']), patch.object(context['subprocess'], 'run') as start, patch.object(context['subprocess'], 'check_output', return_value=json.dumps(rules)):
            context['main']()
            self.assertEqual(start.call_count, 2)
            self.assertEqual(start.call_args.args[0], ['/usr/bin/python3', '/usr/local/lib/employee-firewall.py', 'verify'])
        with patch.object(context['sys'], 'argv', ['hook', '501', 'pre-start']), patch.object(context['subprocess'], 'run'), patch.object(context['subprocess'], 'check_output', return_value='{"nftables":[]}'), self.assertRaises(RuntimeError):
            context['main']()
        with patch.object(context['sys'], 'argv', ['hook', '999', 'pre-start']), patch.object(context['subprocess'], 'run') as start, self.assertRaises(RuntimeError):
            context['main']()
        start.assert_not_called()
        disabled = {'__name__': 'hook_test'}
        exec(compile(code.replace("if 'false' == 'true':", "if 'true' == 'true':"), '<hook>', 'exec'), disabled)
        with patch.object(disabled['sys'], 'argv', ['hook', '501', 'pre-start']), patch.object(disabled['subprocess'], 'run') as start, self.assertRaises(RuntimeError):
            disabled['main']()
        start.assert_not_called()

    def test_bootstrap_management_survives_interface_rename(self):
        rules = render('nftables.conf.j2')
        rule = 'ip saddr 192.168.50.10/32 ip daddr 192.168.50.2 tcp dport 22 accept'
        self.assertIn(rule, rules)
        self.assertLess(rules.index('iifname "wg-employee" drop'), rules.index(rule))
        self.assertLess(rules.index('iifname "emp0" drop'), rules.index(rule))

    def test_yaml_parse(self):
        files = list(ROLE.rglob('*.yml')) + list((ROOT / 'ansible/roles/employee-workspace').rglob('*.yml')) + list((ROOT / 'ansible/playbooks').glob('*employee-workspace.yml'))
        for path in files:
            with self.subTest(path=path):
                self.assertIsNotNone(yaml.safe_load(path.read_text()))


if __name__ == '__main__':
    unittest.main()
