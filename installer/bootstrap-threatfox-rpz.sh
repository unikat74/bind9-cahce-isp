#!/bin/sh
# Instalator komponentu ThreatFox RPZ dla BIND 9 / Debian.
set -eu

ROLE=${1:-}
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)

case "$ROLE" in
  primary|secondary) ;;
  *) echo "Użycie: $0 primary|secondary" >&2; exit 64 ;;
esac

[ "$(id -u)" -eq 0 ] || { echo "Uruchom jako root." >&2; exit 1; }
[ -f "$ROOT/installer/inventory.env" ] || {
  echo "Skopiuj installer/inventory.env.example do installer/inventory.env i uzupełnij dane." >&2
  exit 1
}
. "$ROOT/installer/inventory.env"

install -d -o root -g bind -m 0750 /etc/bind/keys
if [ "$ROLE" = primary ]; then
  install -d -o root -g bind -m 0750 /etc/bind/rpz
  [ -f /etc/threatfox.env ] || { echo "Brak /etc/threatfox.env." >&2; exit 1; }
  install -m 0750 "$ROOT/scripts/update-threatfox-rpz" /usr/local/sbin/update-threatfox-rpz
  install -m 0644 "$ROOT/systemd/threatfox-rpz.service" /etc/systemd/system/threatfox-rpz.service
  install -m 0644 "$ROOT/systemd/threatfox-rpz.timer" /etc/systemd/system/threatfox-rpz.timer
  sed "s/DNS2_IPV4/$DNS2_IPV4/g" "$ROOT/bind/dns1/named.conf.rpz" > /etc/bind/named.conf.rpz
  cp "$ROOT/bind/dns1/named.conf.rpz-options" /etc/bind/named.conf.rpz-options
else
  install -d -o bind -g bind -m 0750 /var/cache/bind/rpz
  sed "s/DNS1_IPV4/$DNS1_IPV4/g" "$ROOT/bind/dns2/named.conf.rpz" > /etc/bind/named.conf.rpz
  cp "$ROOT/bind/dns2/named.conf.rpz-options" /etc/bind/named.conf.rpz-options
fi

chown root:bind /etc/bind/named.conf.rpz /etc/bind/named.conf.rpz-options
chmod 0644 /etc/bind/named.conf.rpz /etc/bind/named.conf.rpz-options
echo "Pliki RPZ gotowe. Wykonaj kroki include/logging z docs/INSTALL.md, następnie named-checkconf."

