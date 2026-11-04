#!/usr/bin/env python3
"""Render or install DoQ on a fresh Debian 13 host with working BIND/TLS."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import tomllib

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('dnscrypt_bootstrap', ROOT / 'installer/bootstrap-dnscrypt.py')
common = importlib.util.module_from_spec(spec)
spec.loader.exec_module(common)


def render(config):
    nets = common.validate(config)
    # Generate only the supported DoQ frontend; DNSCrypt is a separate service.
    frontend = 'setACL(' + json.dumps([str(n) for n in sorted(nets, key=str)]).replace('[', '{').replace(']', '}') + ')\n'
    frontend += '''setLocal("127.0.0.1:5301")
newServer({address="127.0.0.1:5300", name="bind-local", useProxyProtocol=true, checkName="example.org.", checkType="A"})
local cert = "/etc/dnsdist/tls/current/fullchain.pem"
local key = "/etc/dnsdist/tls/current/privkey.pem"
'''
    frontend += f'addDOQLocal("{config["ipv4"]}:853", cert, key)\naddDOQLocal("[{config["ipv6"]}]:853", cert, key)\n'
    firewall = 'destroy table inet isp_doq\ntable inet isp_doq {\n'
    for version in (4, 6):
        members = ', '.join(str(n) for n in sorted(nets, key=str) if n.version == version)
        firewall += f' set clients{version} {{ type ipv{version}_addr; flags interval; auto-merge; elements = {{ {members} }}; }}\n'
    firewall += ''' chain input {
  type filter hook input priority -5; policy accept;
  udp dport 853 ip saddr @clients4 accept
  udp dport 853 ip6 saddr @clients6 accept
  udp dport 853 counter drop
 }
}
'''
    return {'etc/dnsdist/dnsdist.conf': frontend,
            'etc/dnsdist/tls-hostname': config['provider'] + '\n',
            'etc/nftables.d/isp-doq.nft': firewall,
            'etc/systemd/system/isp-doq-firewall.service': (ROOT / 'systemd/isp-doq-firewall.service').read_text(),
            'etc/systemd/system/dnsdist.service.d/isp-doq.conf': (ROOT / 'systemd/dnsdist.service.d/isp-doq.conf').read_text(),
            'usr/local/sbin/deploy-dnsdist-tls': (ROOT / 'scripts/deploy-dnsdist-tls').read_text(),
            'etc/letsencrypt/renewal-hooks/deploy/dnsdist-tls': '#!/bin/sh\nexec /usr/local/sbin/deploy-dnsdist-tls\n'}


def install(config, files):
    common.preflight(config, common.render(config))
    if 'dns-over-quic' not in common.run('dnsdist', '--version'):
        raise ValueError('dnsdist must support dns-over-quic')
    if Path('/etc/dnsdist/tls/current').exists() or 'table inet isp_doq\n' in common.run('nft', 'list', 'tables'):
        raise ValueError('Existing DoQ installation; preserve it and use documented update procedure')
    options = Path('/etc/bind/named.conf.options')
    old_options = options.read_text()
    if 'proxy plain' in old_options:
        raise ValueError('Existing PROXY listener: merge manually')
    backup = Path(tempfile.mkdtemp(prefix='doq-install-', dir='/root'))
    backup.chmod(0o700)
    previous = {}
    for relative in files:
        p = Path('/') / relative
        previous[p] = p.read_bytes() if p.exists() else None
    (backup / 'named.conf.options').write_text(old_options)
    for index, (path, content) in enumerate(previous.items()):
        if content is not None:
            (backup / str(index)).write_bytes(content)
    try:
        for relative, content in files.items():
            path = Path('/') / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
            path.chmod(0o755 if relative.startswith(('usr/', 'etc/letsencrypt/renewal-hooks/')) else 0o644)
        pos = old_options.rfind('};')
        if pos < 0:
            raise ValueError('Cannot locate options block end')
        options.write_text(old_options[:pos] + ''' listen-on port 5300 proxy plain { 127.0.0.1; };
 allow-proxy { 127.0.0.1; };
 allow-proxy-on { 127.0.0.1; };
''' + old_options[pos:])
        common.run('named-checkconf')
        common.run('nft', '-c', '-f', '/etc/nftables.d/isp-doq.nft')
        env = dict(os.environ, RENEWED_LINEAGE='/etc/letsencrypt/live/' + config['provider'])
        subprocess.run(['/usr/local/sbin/deploy-dnsdist-tls', '--init'], env=env, check=True)
        common.run('dnsdist', '--check-config')
        common.run('rndc', 'reconfig')
        common.run('systemctl', 'unmask', 'dnsdist')
        common.run('systemctl', 'daemon-reload')
        common.run('systemctl', 'enable', '--now', 'isp-doq-firewall', 'dnsdist')
        common.run('systemctl', 'is-active', 'dnsdist')
    except Exception:
        subprocess.run(['systemctl', 'stop', 'dnsdist'])
        subprocess.run(['systemctl', 'disable', '--now', 'isp-doq-firewall'])
        options.write_text(old_options)
        for path, content in previous.items():
            if content is None:
                path.unlink(missing_ok=True)
            else:
                path.write_bytes(content)
        subprocess.run(['rndc', 'reconfig'])
        subprocess.run(['systemctl', 'daemon-reload'])
        print('DoQ stopped; backup:', backup, '; retain TLS generation for diagnosis')
        raise
    print('DoQ installed; backup:', backup, '; perform IPv4/IPv6 client tests')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('inventory', type=Path)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--output', type=Path)
    mode.add_argument('--install', action='store_true')
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
