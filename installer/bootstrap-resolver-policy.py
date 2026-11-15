#!/usr/bin/env python3
"""Render/apply the agreed policy to one Debian 13 resolver (dns2 first)."""
import argparse
import importlib.util
import ipaddress
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import tomllib

ROOT = Path(__file__).resolve().parents[1]

def load(name):
    spec = importlib.util.spec_from_file_location(name.replace('-', '_'), ROOT / 'installer' / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

policy = load('resolver_policy')
protection = load('bootstrap-dns-protection')
common = load('bootstrap-dnscrypt')


def render(config):
    files = policy.render(config)
    clients = [str(n) for n in policy.networks(config['clients'] + config['administrators'] + ['127.0.0.1/32', '::1/128'])]
    return dict(protection.render(clients), **files)


def options_span(text):
    # Ignore braces in comments/quoted TLS paths; only select a top-level block.
    tokens = re.finditer(r'"(?:\\.|[^"\\])*"|//[^\n]*|/\*.*?\*/|[{}]|\boptions\b', text, re.S)
    depth = 0
    waiting = False
    start = None
    for token in tokens:
        value = token.group()
        if value.startswith(('"', '//', '/*')):
            continue
        if value == 'options' and depth == 0:
            waiting = True
        elif value == '{':
            if waiting and depth == 0:
                start = token.end()
                waiting = False
            depth += 1
        elif value == '}':
            depth -= 1
            if start is not None and depth == 0:
                return start, token.start()
    raise ValueError('Expected one balanced top-level options block')


def apply_options(text, config):
    """Preserve TLS/listeners/RPZ; replace only named policy statements."""
    nets = policy.networks(config['clients'] + config['administrators'] + ['127.0.0.1/32', '::1/128'])
    acl = 'acl "klienci_sieci" { ' + ' '.join(str(n) + ';' for n in nets) + ' };'
    pattern = r'acl\s+"?klienci_sieci"?\s*\{[^{}]*\}\s*;'
    matches = re.findall(pattern, text)
    if len(matches) > 1:
        raise ValueError('Ambiguous client ACL')
    if matches:
        previous = common.bind_acl(matches[0])
        if any(not any(n.version == target.version and n.subnet_of(target) for target in nets) for n in previous):
            raise ValueError('Inventory would remove existing DNS clients; review profile')
        text = re.sub(pattern, lambda _: acl, text)
    else:
        text = acl + '\n' + text
    include = 'include "/etc/bind/named.conf.resolver-policy";'
    if include in text:
        return text
    start, end = options_span(text)
    body = text[start:end]
    # Only these options are replaced; other resolver/TLS/RPZ statements remain.
    names = ['max-cache-size', 'recursive-clients', 'tcp-clients', 'allow-query',
             'allow-recursion', 'allow-query-cache', 'allow-transfer', 'recursion',
             'dnssec-validation', 'forward', 'forwarders']
    for name in names:
        body = re.sub(r'\b' + name + r'\s+(?:\{[^{}]*\}|[^;{}]+)\s*;', '', body)
    return text[:start] + '\n ' + include + body + text[end:]



def install(config, files):
    if os.geteuid() != 0 or 'VERSION_ID="13"' not in Path('/etc/os-release').read_text():
        raise ValueError('Install requires root on Debian 13')
    common.run('named-checkconf')
    for upstream in config['forwarders']:
        answer = common.run('dig', '@' + upstream, 'example.org', 'A', '+time=2', '+tries=1')
        if 'status: NOERROR' not in answer:
            raise ValueError('Forwarder is not reachable from this host: ' + upstream)
    options = Path('/etc/bind/named.conf.options')
    main = Path('/etc/bind/named.conf')
    local = Path('/etc/bind/named.conf.local')
    expanded = common.run('named-checkconf', '-p', '-x')
    # Do not silently overwrite inline logging or a competing logrotate owner.
    if re.search(r'\blogging\s*\{', main.read_text()):
        raise ValueError('Inline logging requires migration; use --output and the migration runbook')
    for p in Path('/etc/logrotate.d').iterdir():
        if not p.is_file():
            continue
        if p.name != 'named-security' and '/var/log/named/' in p.read_text(errors='replace'):
            raise ValueError('Competing logrotate entry: ' + str(p))
    # Existing NTP exceptions must be present in the explicit, separate profile.
    effective = common.run('chronyd', '-p')
    allowed = policy.networks(config['ntp_clients'] + config['administrators'] + ['127.0.0.1/32', '::1/128'])
    for line in effective.splitlines():
        if line.startswith(('deny ', 'peer ', 'acquisitionport ')):
            raise ValueError('Nonstandard chrony policy requires explicit migration')
        if line.startswith('allow '):
            net = ipaddress.ip_network(line.split()[1], strict=False)
            if not any(net.version == n.version and net.subnet_of(n) for n in allowed):
                raise ValueError('Inventory omits an existing NTP exception: ' + str(net))
    targets = {Path('/') / p: content for p, content in files.items()}
    targets[options] = apply_options(options.read_text(), config)
    include = 'include "/etc/bind/named.conf.logging";'
    targets[main] = main.read_text() if include in main.read_text() else main.read_text() + '\n' + include + '\n'
    if 'zone "localhost"' in expanded:
        targets.pop(Path('/etc/bind/db.localhost'))
        targets.pop(Path('/etc/bind/named.conf.localhost'))
    else:
        targets[local] = local.read_text() + '\ninclude "/etc/bind/named.conf.localhost";\n'
    backup = Path(tempfile.mkdtemp(prefix='resolver-policy-before-', dir='/root'))
    backup.chmod(0o700)
    previous = {p: p.read_bytes() if p.exists() else None for p in targets}
    metadata = {p: p.stat() for p in targets if p.exists()}
    for i, (p, data) in enumerate(previous.items()):
        if data is not None:
            (backup / str(i)).write_bytes(data)
    (backup / 'manifest.json').write_text(json.dumps({str(i): str(p) for i, p in enumerate(targets)}, indent=2))
    (backup / 'ruleset.nft').write_text(common.run('nft', '-a', 'list', 'ruleset'))
    old_table = subprocess.run(['nft', 'list', 'table', 'inet', 'isp_dns'], capture_output=True, text=True)
    old_active = subprocess.run(['systemctl', 'is-active', '--quiet', 'nftables']).returncode == 0
    old_enabled = subprocess.run(['systemctl', 'is-enabled', '--quiet', 'nftables']).returncode == 0
    timer_enabled = subprocess.run(['systemctl', 'is-enabled', '--quiet', 'isp-dns-logrotate.timer']).returncode == 0
    ssh_allowed = policy.networks(config['administrators'] + config.get('ssh_administrators', []) + ['127.0.0.0/8', '::1/128'])
    # Read the current allowlist without parsing human-readable client status.
    import ast
    commands = common.run('fail2ban-client', '-d')
    for line in commands.splitlines():
        try:
            command = ast.literal_eval(line)
        except (SyntaxError, ValueError):
            continue
        if isinstance(command, list) and command[:3] == ['set', 'sshd', 'addignoreip']:
            for value in command[3:]:
                net = ipaddress.ip_network(value, strict=False)
                if not any(net.version == n.version and net.subnet_of(n) for n in ssh_allowed):
                    raise ValueError('Profile omits SSH administrative exception: ' + str(net))
    bans = {}
    for jail in ('sshd', 'sshd-ip6'):
        result = subprocess.run(['fail2ban-client', 'get', jail, 'banip'], capture_output=True, text=True)
        if result.returncode == 0:
            bans[jail] = set(result.stdout.split())

    for name in ('security.log', 'rpz.log'):
        p = Path('/var/log/named') / name
        common.run('install', '-d', '-o', 'bind', '-g', 'bind', '-m', '750', str(p.parent))
        p.touch(exist_ok=True)
        common.run('chown', 'bind:bind', str(p))
        p.chmod(0o640)
    try:
        for p, text in targets.items():
            common.install_directory(p.parent)
            p.write_text(text)
            p.chmod(0o644)
        common.run('named-checkconf')
        common.run('chronyd', '-p')
        common.run('fail2ban-client', '-t')
        common.run('nft', '-c', '-f', '/etc/nftables.conf')
        common.run('logrotate', '--debug', '--state', '/var/lib/logrotate/isp-dns.status', '/etc/logrotate-isp-dns.conf')
        common.run('systemctl', 'daemon-reload')
        if old_active:
            common.run('systemctl', 'reload', 'nftables')
        else:
            common.run('systemctl', 'start', 'nftables')
        common.run('systemctl', 'enable', 'nftables')
        common.run('rndc', 'reconfig')
        common.run('fail2ban-client', 'reload')
        for j, values in bans.items():
            if values - set(common.run('fail2ban-client', 'get', j, 'banip').split()):
                raise ValueError('An SSH ban disappeared; inspect saved state/expiry')
        for net in allowed:
            common.run('chronyc', 'allow', str(net))
        common.run('systemctl', 'enable', '--now', 'isp-dns-logrotate.timer')
        answer = common.run('dig', '@127.0.0.1', 'localhost', 'A', '+norecurse')
        if 'status: NOERROR' not in answer or not re.search(r'flags:.*\baa\b', answer):
            raise ValueError('Local authoritative health check failed')
    except Exception:
        if not timer_enabled:
            subprocess.run(['systemctl', 'disable', '--now', 'isp-dns-logrotate.timer'], capture_output=True)
        if not old_active:
            subprocess.run(['systemctl', 'stop', 'nftables'], capture_output=True)
        # Restore only our table, never replay a global ruleset over current bans.
        if old_table.returncode == 0:
            subprocess.run(['nft', '-f', '-'], input='destroy table inet isp_dns\n' + old_table.stdout, text=True)
        else:
            subprocess.run(['nft', 'delete', 'table', 'inet', 'isp_dns'], capture_output=True)
        for p, data in previous.items():
            if data is None:
                p.unlink(missing_ok=True)
            else:
                p.write_bytes(data)
                p.chmod(metadata[p].st_mode & 0o7777)
                os.chown(p, metadata[p].st_uid, metadata[p].st_gid)
        subprocess.run(['systemctl', 'daemon-reload'])
        if not old_enabled:
            subprocess.run(['systemctl', 'disable', 'nftables'], capture_output=True)
        for cmd in [('rndc', 'reconfig'), ('fail2ban-client', 'reload')]:
            subprocess.run(cmd, capture_output=True)
        # Undo runtime NTP additions; reapply the saved effective allow rules.
        subprocess.run(['chronyc', 'deny', 'all'], capture_output=True)
        for line in effective.splitlines():
            if line.startswith('allow '):
                subprocess.run(['chronyc', 'allow', line.split()[1]], capture_output=True)
        raise
    print('Installed resolver policy; backup:', backup, '; validate all transports and ACLs before proceeding to dns1')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('inventory', type=Path)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument('--output', type=Path)
    modes.add_argument('--install', action='store_true')
    args = parser.parse_args()
    config = tomllib.loads(args.inventory.read_text())
    files = render(config)
    if args.output:
        args.output.mkdir(mode=0o700)
        for relative, content in files.items():
            p = args.output / relative
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content)
    else:
        install(config, files)

if __name__ == '__main__':
    main()
