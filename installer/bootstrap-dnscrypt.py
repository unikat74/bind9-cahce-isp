#!/usr/bin/env python3
"""Render or install the DNSCrypt frontend on Debian 13 amd64; see DNSCRYPT-INSTALL.md."""
import argparse
import hashlib
import io
import ipaddress
import json
import os
from pathlib import Path
import platform
import pwd
import re
import subprocess
import tarfile
import tempfile
import tomllib
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
VERSION = "0.9.22"
DIGEST = "415204cbcfb4c03321e346ad89ee345ec7de2c4f71ffb1b6419b2a2e157b587b"
URL = f"https://github.com/DNSCrypt/encrypted-dns-server/releases/download/{VERSION}/encrypted-dns_{VERSION}_linux-x86_64.tar.bz2"
JAILS = ["named-cache-denied-" + x for x in ("udp", "tcp", "udp6", "tcp6")]


def run(*args, input=None):
    return subprocess.run(args, input=input, text=True, capture_output=True, check=True).stdout


def validate(config):
    if set(config) != {"instance", "provider", "ipv4", "ipv6", "clients"}:
        raise ValueError("Inventory requires exactly instance, provider, ipv4, ipv6, clients")
    if config["instance"] not in ("isp-dnscrypt", "isp-dnscrypt-test"):
        raise ValueError("Unsupported instance name")
    name = config["provider"]
    if not isinstance(name, str) or len(name) > 220 or not all(
        re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", part)
        for part in name.split(".")
    ) or "." not in name:
        raise ValueError("Provider must be a DNS name without the 2.dnscrypt-cert. prefix")
    if name.startswith("2.dnscrypt-cert."):
        raise ValueError("Omit the provider prefix")
    for field, version in (("ipv4", 4), ("ipv6", 6)):
        addr = ipaddress.ip_address(config[field])
        if addr.version != version or addr.is_unspecified or addr.is_multicast or addr.is_loopback:
            raise ValueError(f"Invalid public listener: {field}")
    nets = {ipaddress.ip_network(x, strict=True) for x in config["clients"]}
    if not nets or any(n.prefixlen == 0 or n.is_multicast for n in nets):
        raise ValueError("ACL cannot contain default routes or multicast")
    if not {ipaddress.ip_network("127.0.0.1/32"), ipaddress.ip_network("::1/128")} <= nets:
        raise ValueError("ACL must contain both loopback addresses")
    for field in ("ipv4", "ipv6"):
        addr = ipaddress.ip_address(config[field])
        if not any(addr.version == n.version and addr in n for n in nets):
            raise ValueError(f"Listener {field} must belong to the client ACL")
    return nets


def render(config):
    nets = validate(config)
    instance = config["instance"]
    table = instance.replace("-", "_")
    replacements = {"@INSTANCE@": instance, "@TABLE@": table,
                    "@PROVIDER@": config["provider"], "@IPV4@": config["ipv4"], "@IPV6@": config["ipv6"]}
    def template(path):
        text = (ROOT / path).read_text()
        for key, value in replacements.items():
            text = text.replace(key, value)
        return text
    sets = []
    for version in (4, 6):
        members = ", ".join(str(n) for n in sorted(nets, key=str) if n.version == version)
        sets.append(f" set clients{version} {{ type ipv{version}_addr; flags interval; auto-merge; elements = {{ {members} }}; }}")
    firewall = f"add table inet {table}\nflush table inet {table}\ntable inet {table} {{\n" + "\n".join(sets) + "\n" + """ chain input {
  type filter hook input priority -6; policy accept;
  meta l4proto { tcp, udp } th dport 8443 ip saddr @clients4 counter accept
  meta l4proto { tcp, udp } th dport 8443 ip6 saddr @clients6 counter accept
  meta l4proto { tcp, udp } th dport 8443 counter drop
 }
}
"""
    jail = "# DNSCrypt ports; existing filters, actions and ignoreip remain unchanged.\n"
    for name in JAILS:
        jail += f"\n[{name}]\nport = " + ("53,443,853,8443" if "tcp" in name else "53,853,8443") + "\n"
    return {
        f"etc/{instance}.toml": template("encrypted-dns/encrypted-dns.toml.in"),
        f"etc/nftables.d/{instance}.nft": firewall,
        f"etc/systemd/system/{instance}.service": template("systemd/isp-dnscrypt.service.in"),
        f"etc/systemd/system/{instance}-firewall.service": template("systemd/isp-dnscrypt-firewall.service.in"),
        "etc/fail2ban/jail.d/zz-dnscrypt-ports.local": jail,
    }


def bind_acl(text):
    text = re.sub(r"/\*.*?\*/|//[^\n]*|\#[^\n]*", "", text, flags=re.S)
    matches = re.findall(r'acl\s+"klienci_sieci"\s*\{([^{}]*)\}\s*;', text)
    if len(matches) != 1:
        raise ValueError("Expected one literal klienci_sieci ACL in named.conf.options")
    return {ipaddress.ip_network(x.strip(), strict=False) for x in matches[0].split(";") if x.strip()}


def preflight(config, files):
    if os.geteuid() != 0 or platform.machine() != "x86_64":
        raise ValueError("Host check/install requires root on amd64")
    release = Path("/etc/os-release").read_text()
    if not re.search(r'^ID=debian$', release, re.M) or not re.search(r'^VERSION_ID="?13"?$', release, re.M):
        raise ValueError("Supported platform: Debian 13")
    run("named-checkconf")
    if bind_acl(Path("/etc/bind/named.conf.options").read_text()) != validate(config):
        raise ValueError("Inventory ACL differs from BIND; no changes made")
    local = {a["local"] for link in json.loads(run("ip", "-j", "address", "show")) for a in link.get("addr_info", [])}
    if not {config["ipv4"], config["ipv6"]} <= local:
        raise ValueError("Listener addresses do not belong to this host")
    for name in ("isp-dnscrypt", "isp-dnscrypt-test"):
        current_path = Path(f"/etc/{name}.toml")
        if current_path.exists():
            current = tomllib.loads(current_path.read_text())
            if name != config["instance"] or current["dnscrypt"]["provider_name"] != config["provider"]:
                raise ValueError("Inventory would change the existing instance/provider identity")
    answer = run("dig", "@127.0.0.1", "+time=3", "+tries=1", "example.org", "A")
    if "status: NOERROR" not in answer:
        raise ValueError("Local BIND resolver failed the preflight query")
    run("fail2ban-client", "-t")
    for jail in JAILS:
        run("fail2ban-client", "status", jail)
    run("nft", "-c", "-f", "-", input=files[f'etc/nftables.d/{config["instance"]}.nft'])


def install(config, files):
    instance = config["instance"]
    # Never migrate or overwrite the other instance or its provider state.
    if any(Path(f"/etc/{name}.toml").exists() for name in ("isp-dnscrypt", "isp-dnscrypt-test")):
        raise ValueError("DNSCrypt already installed. Use --check and the documented update procedure; preserve state/provider.")
    targets = [Path("/") / path for path in files]
    state = Path(f"/var/lib/{instance}")
    if any(p.exists() for p in targets) or state.exists() or Path(f"/opt/{instance}").exists():
        raise ValueError("Existing files/state found; refusing to overwrite")
    tables = run("nft", "list", "tables")
    if f"table inet {instance.replace('-', '_')}\n" in tables:
        raise ValueError("Firewall table already exists")
    if run("ss", "-H", "-lntu", "sport = :8443").strip():
        raise ValueError("Port 8443 is already in use")
    archive = urllib.request.urlopen(URL, timeout=60).read()
    if hashlib.sha256(archive).hexdigest() != DIGEST:
        raise ValueError("Release SHA256 mismatch")
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:bz2") as tar:
        members = [m for m in tar if m.isfile() and m.name.endswith("/encrypted-dns")]
        if len(members) != 1:
            raise ValueError("Unexpected release archive")
        binary = tar.extractfile(members[0]).read()
    backup = Path(tempfile.mkdtemp(prefix="dnscrypt-install-", dir="/root"))
    backup.chmod(0o700)
    (backup / "nft-before.txt").write_text(run("nft", "-a", "list", "ruleset"))
    bans = {j: set(run("fail2ban-client", "get", j, "banip").split()) for j in JAILS}
    (backup / "bans-before.json").write_text(json.dumps({j: sorted(v) for j, v in bans.items()}))
    try:
        pwd.getpwnam(instance)
    except KeyError:
        run("useradd", "--system", "--home-dir", str(state), "--shell", "/usr/sbin/nologin", instance)
    binary_path = Path(f"/opt/{instance}/encrypted-dns")
    binary_path.parent.mkdir(mode=0o755)
    binary_path.write_bytes(binary)
    binary_path.chmod(0o755)
    try:
        for relative, content in files.items():
            target = Path("/") / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content)
            target.chmod(0o644)
        run("fail2ban-client", "-t")
        run("systemd-analyze", "verify", f"/etc/systemd/system/{instance}.service")
        run("systemctl", "daemon-reload")
        run("systemctl", "start", instance)
        run("systemctl", "is-active", instance)
        for jail in JAILS:
            run("fail2ban-client", "reload", "--restart", jail)
            remaining = set(run("fail2ban-client", "get", jail, "banip").split())
            if bans[jail] - remaining:
                raise ValueError(f"Ban list changed in {jail}; inspect {backup}")
        run("systemctl", "enable", instance, instance + "-firewall")
    except Exception:
        # Only remove files created by this fresh install. Provider state is retained.
        subprocess.run(["systemctl", "disable", "--now", instance, instance + "-firewall"], capture_output=True)
        for target in targets:
            target.unlink(missing_ok=True)
        subprocess.run(["systemctl", "daemon-reload"], capture_output=True)
        for jail in JAILS:
            subprocess.run(["fail2ban-client", "reload", "--restart", jail], capture_output=True)
        print(f"Installation failed; frontend stopped. Preserve state in {state}; evidence: {backup}")
        raise
    print(f"Installed {VERSION}. Backup: {backup}. Perform client tests in docs/DNSCRYPT-INSTALL.md.")
    print(f"Public stamps: journalctl -u {instance}. Secret state: {state}/encrypted-dns.state")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inventory", type=Path)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--output", type=Path, help="Render a new bundle directory without touching the host")
    mode.add_argument("--check", action="store_true", help="Read-only host preflight")
    mode.add_argument("--install", action="store_true", help="Fresh installation only")
    args = parser.parse_args()
    config = tomllib.loads(args.inventory.read_text())
    files = render(config)
    if args.output:
        args.output.mkdir(mode=0o700)  # Refuse existing directories; no accidental overwrite.
        for relative, text in files.items():
            dest = args.output / relative
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(text)
        print(f"Rendered {len(files)} files in {args.output}")
    else:
        preflight(config, files)
        if args.install:
            install(config, files)
        else:
            print("Host checks OK. Existing configuration/state unchanged.")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, subprocess.CalledProcessError, tomllib.TOMLDecodeError) as error:
        raise SystemExit(str(error))
