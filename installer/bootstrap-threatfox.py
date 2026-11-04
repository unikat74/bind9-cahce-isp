#!/usr/bin/env python3
"""Prepare/activate ThreatFox primary on dns1 or TSIG secondary on dns2."""
import argparse
import ipaddress
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
KEY = Path('/etc/bind/keys/threatfox-rpz-xfr.key')
ZONE_NAME = 'rpz.threatfox.abuse.ch'


def zone_text(role, peer):
    ipaddress.ip_address(peer)
    if role == 'primary':
        body = f''' type primary;
 file "/etc/bind/rpz/threatfox.rpz";
 allow-transfer {{ key "threatfox-rpz-xfr"; }};
 notify yes;
 also-notify {{ {peer} key "threatfox-rpz-xfr"; }};
'''
    else:
        body = f''' type secondary;
 file "/var/cache/bind/rpz/threatfox.rpz";
 primaries {{ {peer} key "threatfox-rpz-xfr"; }};
 allow-notify {{ key "threatfox-rpz-xfr"; }};
 allow-transfer {{ none; }};
'''
    return 'include "/etc/bind/keys/threatfox-rpz-xfr.key";\nzone "' + ZONE_NAME + '" {\n' + body + '};\n'


def run(*args):
    return subprocess.check_output(args, text=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('role', choices=['primary', 'secondary'])
    parser.add_argument('mode', choices=['prepare', 'activate'])
    parser.add_argument('--peer', required=True, help='Other resolver IP; no names or shell syntax')
    args = parser.parse_args()
    text = zone_text(args.role, args.peer)
    if os.geteuid() != 0:
        raise SystemExit('Run as root on Debian with an existing BIND resolver')
    run('named-checkconf')
    run('install', '-d', '-o', 'root', '-g', 'bind', '-m', '750', '/etc/bind/keys')
    if args.role == 'primary':
        for source, target, mode in [
            ('scripts/update-threatfox-rpz', '/usr/local/sbin/update-threatfox-rpz', 0o750),
            ('systemd/threatfox-rpz.service', '/etc/systemd/system/threatfox-rpz.service', 0o644),
            ('systemd/threatfox-rpz.timer', '/etc/systemd/system/threatfox-rpz.timer', 0o644),
        ]:
            path = Path(target)
            if path.exists() and path.read_bytes() != (ROOT / source).read_bytes():
                raise SystemExit('Existing differing file: ' + target + '; merge manually')
            shutil.copyfile(ROOT / source, path)
            path.chmod(mode)
        run('install', '-d', '-o', 'root', '-g', 'bind', '-m', '750', '/etc/bind/rpz')
        if not KEY.exists():
            # Never expose TSIG in tool output or regenerate an existing identity.
            with open(KEY, 'x', opener=lambda p, flags: os.open(p, flags, 0o640)) as handle:
                subprocess.run(['tsig-keygen', '-a', 'hmac-sha256', 'threatfox-rpz-xfr'], stdout=handle, check=True)
            run('chown', 'root:bind', str(KEY))
        run('systemctl', 'daemon-reload')
    else:
        run('install', '-d', '-o', 'bind', '-g', 'bind', '-m', '750', '/var/cache/bind/rpz')
    if args.mode == 'prepare':
        print('Prepared', args.role, 'only; no zone/policy/timer enabled. Transfer TSIG securely; Auth-Key only on primary.')
        return
    if not KEY.exists():
        raise SystemExit('Transfer the primary TSIG key securely before activation')
    options = Path('/etc/bind/named.conf.options')
    local = Path('/etc/bind/named.conf.local')
    zone = Path('/etc/bind/named.conf.threatfox')
    if zone.exists() or ZONE_NAME in options.read_text():
        raise SystemExit('Existing ThreatFox configuration; do not reactivate or change identity')
    if args.role == 'primary':
        key = Path('/etc/threatfox.env')
        if not key.exists() or key.stat().st_uid != 0 or key.stat().st_mode & 0o077:
            raise SystemExit('Create root-owned /etc/threatfox.env mode 0600 with the separate Auth-Key')
        subprocess.run(['/usr/local/sbin/update-threatfox-rpz'], env=dict(os.environ, RELOAD='no'), check=True)
    before = {options: options.read_bytes(), local: local.read_bytes()}
    backup = Path(tempfile.mkdtemp(prefix='threatfox-activate-', dir='/root'))
    backup.chmod(0o700)
    for p in before:
        (backup / p.name).write_bytes(before[p])
    s = options.read_text()
    if s.count('response-policy {') != 1:
        raise SystemExit('Expected a single existing response-policy block; merge manually')
    try:
        zone.write_text(text)
        local.write_text(local.read_text() + '\ninclude "/etc/bind/named.conf.threatfox";\n')
        run('named-checkconf'); run('rndc', 'reconfig')
        # Do not add a policy referencing an unloaded zone: wait for successful load/transfer.
        for attempt in range(30):
            result = subprocess.run(['rndc', 'zonestatus', ZONE_NAME], text=True, capture_output=True)
            if result.returncode == 0 and 'serial:' in result.stdout:
                break
            time.sleep(1)
        else:
            raise RuntimeError('Zone did not load/transfer; original resolver configuration will be restored')
        options.write_text(s.replace('response-policy {', 'response-policy { zone "' + ZONE_NAME + '" policy nxdomain log yes;', 1))
        run('named-checkconf'); run('rndc', 'reconfig')
        if args.role == 'primary':
            run('systemctl', 'enable', '--now', 'threatfox-rpz.timer')
    except Exception:
        for path, content in before.items():
            path.write_bytes(content)
        zone.unlink(missing_ok=True)
        subprocess.run(['rndc', 'reconfig'])
        raise
    print('Activated', args.role, '; verify live blocking, matching serials and timer. Backup:', backup)


if __name__ == '__main__':
    main()
