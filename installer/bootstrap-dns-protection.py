#!/usr/bin/env python3
"""Install bounded BIND security/RPZ logs and four DNS Fail2Ban jails."""
import argparse
import configparser
import io
import json
import ipaddress
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
LOGGING = '''logging {
 channel security_file {
  file "/var/log/named/security.log" versions 5 size 20m;
  severity info;
  print-time yes;
 };
 channel rpz_file {
  file "/var/log/named/rpz.log" versions 5 size 20m;
  severity info;
  print-time yes;
 };
 category security { security_file; };
 category rpz { rpz_file; };
};
'''


def render(networks):
    nets = [ipaddress.ip_network(n, strict=True) for n in networks]
    if not nets or any(n.prefixlen == 0 or n.is_multicast for n in nets):
        raise ValueError('Explicit client prefixes required; default routes/multicast forbidden')
    if {n.version for n in nets} != {4, 6}:
        raise ValueError('Provide client networks for both IPv4 and IPv6')
    config = configparser.ConfigParser(interpolation=None)
    config.read(ROOT / 'fail2ban/jail.d/named-cache-denied.local')
    for section in config.sections():
        version = 6 if section.endswith('6') else 4
        loopback = '::1' if version == 6 else '127.0.0.1/8'
        config[section]['ignoreip'] = loopback + ' ' + ' '.join(str(n) for n in nets if n.version == version)
    output = io.StringIO()
    config.write(output)
    jail = output.getvalue()
    files = {'etc/bind/named.conf.logging': LOGGING,
             'etc/fail2ban/jail.d/named-cache-denied.local': jail}
    for relative in ['filter.d/named-cache-denied.conf', 'filter.d/named-cache-denied-v6.conf',
                     'action.d/nftables-multiport-ip6.conf']:
        files['etc/fail2ban/' + relative] = (ROOT / 'fail2ban' / relative).read_text()
    return files


def run(*args):
    subprocess.run(args, check=True)


def trusted_bans(bans, networks):
    nets = [ipaddress.ip_network(n, strict=False) for n in networks]
    return [ip for ip in bans if any(ipaddress.ip_address(ip).version == n.version
                                    and ipaddress.ip_address(ip) in n for n in nets)]


def install(files, networks):
    if os.geteuid() != 0:
        raise ValueError('Run --install as root on the target Debian server')
    run('named-checkconf')
    conf = Path('/etc/bind/named.conf')
    before = conf.read_text()
    # Refuse a second logging block; existing installs need explicit merging.
    if 'logging {' in before:
        raise ValueError('Existing inline logging block: merge it before installing')
    backup = Path(tempfile.mkdtemp(prefix='dns-protection-', dir='/root'))
    backup.chmod(0o700)
    previous = {}
    targets = {Path('/') / p: content for p, content in files.items()}
    include = 'include "/etc/bind/named.conf.logging";'
    targets[conf] = before if include in before else before + '\n' + include + '\n'
    for index, target in enumerate(targets):
        previous[target] = target.read_bytes() if target.exists() else None
        if target.exists():
            shutil.copy2(target, backup / str(index))
    (backup / 'manifest.json').write_text(json.dumps({str(i): str(p) for i, p in enumerate(targets)}, indent=2))
    subprocess.run(['fail2ban-client', 'status', '--all'], stdout=(backup / 'jails-before.txt').open('w'), check=True)
    run('install', '-d', '-o', 'bind', '-g', 'bind', '-m', '750', '/var/log/named')
    for name in ['security.log', 'rpz.log']:
        path = Path('/var/log/named') / name
        path.touch(exist_ok=True)
        run('chown', 'bind:bind', str(path)); path.chmod(0o640)
    try:
        for path, content in targets.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
            path.chmod(0o644)
        run('named-checkconf')
        run('fail2ban-client', '-t')
        run('rndc', 'reconfig')
        run('fail2ban-client', 'reload')
    except Exception:
        for path, content in previous.items():
            if content is None:
                path.unlink(missing_ok=True)
            else:
                path.write_bytes(content)
        subprocess.run(['rndc', 'reconfig'])
        subprocess.run(['fail2ban-client', 'reload'])
        raise
    # Reloading ignoreip does not remove pre-existing bans for newly trusted clients.
    for jail in ['named-cache-denied-' + suffix for suffix in ('udp', 'tcp', 'udp6', 'tcp6')]:
        bans = subprocess.check_output(['fail2ban-client', 'get', jail, 'banip'], text=True).split()
        clear = trusted_bans(bans, networks)
        if clear:
            run('fail2ban-client', 'set', jail, 'unbanip', *clear)
        print(jail, 'removed pre-existing trusted-client bans:', len(clear))
    print('Installed DNS protection; backup:', backup)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--client-network', action='append', required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--output', type=Path)
    mode.add_argument('--install', action='store_true')
    args = parser.parse_args()
    files = render(args.client_network)
    if args.output:
        args.output.mkdir(mode=0o700)
        for relative, text in files.items():
            dest = args.output / relative
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(text)
    else:
        install(files, args.client_network)


if __name__ == '__main__':
    main()
