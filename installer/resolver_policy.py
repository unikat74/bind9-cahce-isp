"""Agreed resolver policy. Only addresses/ACLs/upstream reachability vary per site."""
import ipaddress
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOGGING = '''logging {
 channel security_file {
  file "/var/log/named/security.log" size unlimited;
  severity info;
  print-time yes;
 };
 channel rpz_file {
  file "/var/log/named/rpz.log" size unlimited;
  severity info;
  print-time yes;
 };
 category security { security_file; };
 category rpz { rpz_file; };
};
'''
LOCALHOST = '''$TTL 86400
@ IN SOA localhost. root.localhost. ( 1 86400 3600 604800 86400 )
@ IN NS localhost.
@ IN A 127.0.0.1
@ IN AAAA ::1
'''


def networks(values):
    result = {ipaddress.ip_network(n, strict=True) for n in values}
    if not result or any(n.prefixlen == 0 or n.is_multicast for n in result):
        raise ValueError('Explicit non-default unicast prefixes required')
    return sorted(result, key=lambda n: (n.version, int(n.network_address), n.prefixlen))


def render(config):
    if set(config) - {'ssh_administrators'} != {'clients', 'ntp_clients', 'administrators', 'forwarders'}:
        raise ValueError('Expected clients, ntp_clients, administrators, forwarders')
    admins = networks(config['administrators'])
    loopbacks = ['127.0.0.1/32', '::1/128']
    dns = networks(config['clients'] + config['administrators'] + loopbacks)
    ntp = networks(config['ntp_clients'] + config['administrators'] + loopbacks)
    if {n.version for n in networks(config['clients'])} != {4, 6}:
        raise ValueError('DNS client ACL must explicitly cover both families')
    upstreams = [ipaddress.ip_address(a) for a in config['forwarders']]
    if not upstreams or any(a.is_unspecified or a.is_multicast or a.is_loopback for a in upstreams):
        raise ValueError('Explicit reachable unicast forwarders required')
    options = '''// Include INSIDE options {}; do not declare a second options block.
max-cache-size 2G;
recursive-clients 10000;
tcp-clients 1000;
allow-query { klienci_sieci; };
allow-recursion { klienci_sieci; };
allow-query-cache { klienci_sieci; };
allow-transfer { none; };
recursion yes;
dnssec-validation auto;
forward only;
forwarders { ''' + ' '.join(str(a) + ';' for a in upstreams) + ' };\n'
    nft = '# Managed resolver policy; never flush other tables.\ndestroy table inet isp_dns\ntable inet isp_dns {\n'
    for label, nets in [('clients', dns), ('ntp_clients', ntp)]:
        for v in (4, 6):
            members = ', '.join(str(n) for n in nets if n.version == v)
            nft += f' set {label}{v} {{ type ipv{v}_addr; flags interval; auto-merge; elements = {{ {members} }}; }}\n'
    nft += ''' chain input {
  type filter hook input priority -10; policy accept;
  iifname "lo" accept
  ip saddr @ntp_clients4 udp dport 123 counter accept
  ip6 saddr @ntp_clients6 udp dport 123 counter accept
  udp dport 123 counter drop
  ip saddr @clients4 udp dport { 53, 853, 8443 } counter accept
  ip6 saddr @clients6 udp dport { 53, 853, 8443 } counter accept
  ip saddr @clients4 tcp dport { 53, 443, 853, 8443 } counter accept
  ip6 saddr @clients6 tcp dport { 53, 443, 853, 8443 } counter accept
  udp dport { 53, 853, 8443 } counter drop
  tcp dport { 53, 443, 853, 8443 } counter drop
 }
}
'''
    ssh_admins = networks(config['administrators'] + config.get('ssh_administrators', []))
    ssh = ''
    for name, findtime, bantime, action, expression in [
        ('sshd', '10m', '1h', 'nftables-multiport', "':' not in '<ip>'"),
        ('sshd-ip6', '60m', '1d', 'nftables-multiport-ip6[blocktype=drop]', "':' in '<ip>'"),
    ]:
        ssh += f'''[{name}]
enabled = true
backend = systemd
filter = sshd
port = 22
protocol = tcp
journalmatch = _SYSTEMD_UNIT=ssh.service + _COMM=sshd + _COMM=sshd-session
banaction = {action}
findtime = {findtime}
maxretry = 5
bantime = {bantime}
bantime.increment = true
bantime.factor = 2
bantime.maxtime = 7d
ignoreip = {' '.join(['127.0.0.0/8', '::1/128'] + [str(n) for n in ssh_admins])}
ignorecommand = /usr/bin/python3 -c "exit({expression})"

'''
    files = {
        'etc/bind/named.conf.resolver-policy': options,
        'etc/bind/named.conf.logging': LOGGING,
        'etc/bind/db.localhost': LOCALHOST,
        'etc/bind/named.conf.localhost': 'zone "localhost" { type primary; file "/etc/bind/db.localhost"; allow-transfer { none; }; notify no; };\n',
        'etc/nftables.conf': nft,
        'etc/systemd/system/nftables.service.d/isp-dns.conf': '[Service]\nExecStop=\nExecStop=/usr/sbin/nft delete table inet isp_dns\n',
        'etc/fail2ban/jail.d/sshd.local': ssh,
        'etc/chrony/conf.d/isp-clients.conf': ''.join('allow ' + str(n) + '\n' for n in ntp),
        # Disable the old owner; exactly one rotation system per log.
        'etc/logrotate.d/named-security': '# Managed by isp-dns-logrotate.timer; see /etc/logrotate-isp-dns.conf\n',
    }
    for source, target in [
        ('logrotate/isp-dns.conf', 'etc/logrotate-isp-dns.conf'),
        ('systemd/isp-dns-logrotate.service', 'etc/systemd/system/isp-dns-logrotate.service'),
        ('systemd/isp-dns-logrotate.timer', 'etc/systemd/system/isp-dns-logrotate.timer'),
    ]:
        files[target] = (ROOT / source).read_text()
    return files
