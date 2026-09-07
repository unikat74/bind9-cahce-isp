#!/bin/sh
# Instalator ThreatFox RPZ i rejestru hazardowego RPZ dla BIND 9 / Debian.
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
: "${DNS1_IPV4:?Brak DNS1_IPV4 w inventory.env}"
: "${DNS2_IPV4:?Brak DNS2_IPV4 w inventory.env}"

command -v named-checkzone >/dev/null 2>&1 || {
  echo "Brak named-checkzone. Zainstaluj pakiet bind9-utils." >&2
  exit 1
}

install -m 0755 "$ROOT/scripts/check-bind-capacity" /usr/local/sbin/check-bind-capacity

install -d -o root -g bind -m 0750 /etc/bind/keys
[ -s /etc/bind/keys/threatfox-rpz-xfr.key ] || {
  echo "Brak /etc/bind/keys/threatfox-rpz-xfr.key." >&2
  exit 1
}

for file in /etc/bind/named.conf.rpz /etc/bind/named.conf.rpz-options; do
  if [ -e "$file" ] && [ ! -e "$file.before-rpz-installer" ]; then
    cp -a "$file" "$file.before-rpz-installer"
  fi
done

if [ "$ROLE" = primary ]; then
  [ -s /etc/threatfox.env ] || { echo "Brak /etc/threatfox.env." >&2; exit 1; }
  command -v curl >/dev/null 2>&1 || { echo "Brak curl." >&2; exit 1; }
  python3 -c 'import idna' 2>/dev/null || {
    echo "Brak python3-idna. Zainstaluj: apt install python3-idna" >&2
    exit 1
  }

  install -d -o root -g bind -m 0750 /etc/bind/rpz
  install -m 0750 "$ROOT/scripts/update-threatfox-rpz" /usr/local/sbin/update-threatfox-rpz
  install -m 0755 "$ROOT/scripts/update-hazard-rpz" /usr/local/sbin/update-hazard-rpz
  install -m 0644 "$ROOT/systemd/threatfox-rpz.service" /etc/systemd/system/threatfox-rpz.service
  install -m 0644 "$ROOT/systemd/threatfox-rpz.timer" /etc/systemd/system/threatfox-rpz.timer
  install -m 0644 "$ROOT/systemd/hazard-rpz.service" /etc/systemd/system/hazard-rpz.service
  install -m 0644 "$ROOT/systemd/hazard-rpz.timer" /etc/systemd/system/hazard-rpz.timer

  # Przy pierwszym uruchomieniu strefy nie są jeszcze dołączone do BIND-a.
  RELOAD=no /usr/local/sbin/update-threatfox-rpz
  /usr/local/sbin/update-hazard-rpz
  sed "s/DNS2_IPV4/$DNS2_IPV4/g" "$ROOT/bind/dns1/named.conf.rpz" > /etc/bind/named.conf.rpz
  cp "$ROOT/bind/dns1/named.conf.rpz-options" /etc/bind/named.conf.rpz-options
else
  install -d -o bind -g bind -m 0750 /var/cache/bind/rpz
  sed "s/DNS1_IPV4/$DNS1_IPV4/g" "$ROOT/bind/dns2/named.conf.rpz" > /etc/bind/named.conf.rpz
  cp "$ROOT/bind/dns2/named.conf.rpz-options" /etc/bind/named.conf.rpz-options
fi

chown root:bind /etc/bind/named.conf.rpz /etc/bind/named.conf.rpz-options
chmod 0644 /etc/bind/named.conf.rpz /etc/bind/named.conf.rpz-options
systemctl daemon-reload

echo "Pliki obu RPZ są gotowe. Dodaj include'y według docs/INSTALL.md,"
echo "wykonaj named-checkconf i reload, a timery włącz dopiero po testach."
