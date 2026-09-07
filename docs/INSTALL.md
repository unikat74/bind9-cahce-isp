# Instalacja BIND 9 dla ISP — pełna instrukcja

Instrukcja opisuje dwa resolvery BIND 9 na Debianie 13:

- `dns1.example.net` — `198.51.100.10`, IPv6 `2001:db8:100:1::2`;
- `dns2.example.net` — `198.51.100.11`, IPv6 `2001:db8:100:1::3`.

To adresy dokumentacyjne. Przed wdrożeniem zastąp je własnymi. Polecenia
wykonuj jako `root`, najpierw na dns1, potem na dns2.

## 1. Rekordy i porty

Utwórz publiczne rekordy:

```dns
dns1.example.net. A     198.51.100.10
dns1.example.net. AAAA  2001:db8:100:1::2
dns2.example.net. A     198.51.100.11
dns2.example.net. AAAA  2001:db8:100:1::3
```

Sprawdź je z zewnętrznego hosta:

```sh
dig +short dns1.example.net A
dig +short dns1.example.net AAAA
dig +short dns2.example.net A
dig +short dns2.example.net AAAA
```

Dopuść UDP/TCP 53, TCP 853 i TCP 443 z sieci klientów. TCP 80 musi być
osiągalny z Internetu podczas walidacji Certbota. Między dns2 i dns1 dopuść
TCP 53 dla transferu stref oraz UDP 53 dla NOTIFY. Jeżeli publikujesz AAAA,
walidacja TCP 80 musi działać także po IPv6.

## 2. Pakiety

Na obu serwerach:

```sh
apt update
apt install bind9 bind9-utils dnsutils curl certbot fail2ban nftables
systemctl enable --now named
named -v
```

Na Debianie 13 jednostka nazywa się `named.service`.

## 3. Sieć

Przykład `/etc/network/interfaces` dla dns1:

```ini
allow-hotplug ens18
iface ens18 inet static
    address 198.51.100.10/25
    gateway 198.51.100.1
    dns-nameservers 127.0.0.1

iface ens18 inet6 static
    address 2001:db8:100:1::2/64
    gateway 2001:db8:100:1::1
```

Dla dns2 zmień adres hosta na `.11` i `::3`. Nie restartuj sieci przez SSH
bez dostępu do konsoli VM. Po restarcie sprawdź:

```sh
ip -br address show dev ens18
ip route
ip -6 route
ping -c 3 1.1.1.1
ping -6 -c 3 2606:4700:4700::1111
```

## 4. Bazowy resolver/cache

W `/etc/bind/named.conf.options` wpisz tylko własne sieci klientów:

```conf
acl "klienci_sieci" {
    127.0.0.1;
    ::1;
    198.51.96.0/21;
    203.0.112.0/22;
    10.20.0.0/24;
    2001:db8:100::/48;
};
```

Wewnątrz `options {}`:

```conf
directory "/var/cache/bind";
allow-query { any; };
recursion yes;
allow-recursion { klienci_sieci; };
allow-query-cache { klienci_sieci; };
allow-transfer { none; };

forward only;
forwarders {
    1.1.1.1; 1.0.0.1;
    2606:4700:4700::1111; 2606:4700:4700::1001;
    8.8.8.8; 8.8.4.4;
    2001:4860:4860::8888; 2001:4860:4860::8844;
};

dnssec-validation auto;
listen-on { any; };
listen-on-v6 { any; };
minimal-responses yes;
minimal-any yes;
qname-minimization relaxed;
max-udp-size 1232;
prefetch 2 9;
version "[Secured]";
hostname "[Secured]";
server-id "[Secured]";
```

Sprawdź:

```sh
named-checkconf
systemctl reload named
dig @127.0.0.1 google.com A
```

Oczekuj `status: NOERROR` i flagi `ra`. Komunikat
`allow-query-cache did not match` oznacza klienta spoza ACL, nie brak wpisu
w cache.

## 5. Let's Encrypt od początku do końca

### 5.1 Kontrola przed wydaniem

Na dns1:

```sh
dig +short dns1.example.net A
dig +short dns1.example.net AAAA
ss -lntp | grep ':80 ' || true
```

`certbot --standalone` musi zająć TCP 80. Jeżeli port zajmuje serwer WWW,
zatrzymaj go na czas walidacji albo użyj metody webroot.

### 5.2 Wydanie certyfikatu

Na dns1:

```sh
certbot certonly --standalone \
  --agree-tos --no-eff-email \
  --email administrator@example.net \
  -d dns1.example.net
```

Na dns2 użyj `-d dns2.example.net`. Sprawdź wynik:

```sh
certbot certificates
```

Pliki dns1 będą w:

```text
/etc/letsencrypt/live/dns1.example.net/fullchain.pem
/etc/letsencrypt/live/dns1.example.net/privkey.pem
```

### 5.3 Kopia dla BIND

BIND nie powinien czytać klucza bezpośrednio z restrykcyjnego katalogu
Certbota. Na dns1:

```sh
install -d -o root -g bind -m 750 /etc/bind/tls
install -o root -g bind -m 640 /etc/letsencrypt/live/dns1.example.net/fullchain.pem /etc/bind/tls/dns1.example.net.fullchain.pem
install -o root -g bind -m 640 /etc/letsencrypt/live/dns1.example.net/privkey.pem /etc/bind/tls/dns1.example.net.privkey.pem
```

Na dns2 zamień `dns1` na `dns2`.

### 5.4 Automatyczna aktualizacja po renew

Na dns1 utwórz `/etc/letsencrypt/renewal-hooks/deploy/bind-tls`:

```sh
#!/bin/sh
set -eu
NAME="dns1.example.net"
install -o root -g bind -m 640 "/etc/letsencrypt/live/$NAME/fullchain.pem" "/etc/bind/tls/$NAME.fullchain.pem"
install -o root -g bind -m 640 "/etc/letsencrypt/live/$NAME/privkey.pem" "/etc/bind/tls/$NAME.privkey.pem"
/usr/bin/named-checkconf
/usr/sbin/rndc reload
```

```sh
chmod 750 /etc/letsencrypt/renewal-hooks/deploy/bind-tls
certbot renew --dry-run
systemctl list-timers | grep certbot
```

Na dns2 ustaw w hooku `NAME="dns2.example.net"`.

## 6. DoT i DoH

Przed `options {}` na dns1:

```conf
tls dns_tls {
    key-file "/etc/bind/tls/dns1.example.net.privkey.pem";
    cert-file "/etc/bind/tls/dns1.example.net.fullchain.pem";
};

http dns_doh {
    endpoints { "/dns-query"; };
};
```

Wewnątrz `options {}`:

```conf
listen-on port 853 tls dns_tls { 198.51.100.10; };
listen-on port 443 tls dns_tls http dns_doh { 198.51.100.10; };
listen-on-v6 port 853 tls dns_tls { 2001:db8:100:1::2; };
listen-on-v6 port 443 tls dns_tls http dns_doh { 2001:db8:100:1::2; };
```

Na dns2 użyj jego nazw i adresów. Aktywacja:

```sh
named-checkconf
systemctl reload named
ss -lntup | grep -E ':(53|443|853)\b'
```

Testy:

```sh
dig -4 @dns1.example.net google.com A +tls +tls-ca +tls-hostname=dns1.example.net
dig -6 @dns1.example.net google.com A +tls +tls-ca +tls-hostname=dns1.example.net
dig -4 @dns1.example.net google.com A +https +tls-ca +tls-hostname=dns1.example.net
dig -6 @dns1.example.net google.com A +https +tls-ca +tls-hostname=dns1.example.net
```

Adres DoH to `https://dns1.example.net/dns-query`. Otwarcie go w zwykłej
karcie przeglądarki nie jest miarodajnym testem protokołu.

## 7. Logi

```sh
install -d -o bind -g bind -m 750 /var/log/named
```

W `/etc/bind/named.conf` dodaj jeden blok:

```conf
logging {
    channel security_file {
        file "/var/log/named/security.log" versions 3 size 30m;
        severity dynamic;
        print-time yes;
    };
    category security { security_file; };
    category rpz { security_file; };
};
```

```sh
named-checkconf && systemctl reload named
tail -f /var/log/named/security.log
journalctl -u named -f
```

## 8. ThreatFox na dns1

Utwórz Auth-Key ThreatFox, a następnie:

```sh
install -o root -g root -m 600 /dev/null /etc/threatfox.env
nano /etc/threatfox.env
```

```sh
THREATFOX_AUTH_KEY='WARTOŚĆ_TYLKO_NA_SERWERZE'
```

Nie commituj tego pliku. Przygotuj zmienne projektu i instalator:

```sh
cp installer/inventory.env.example installer/inventory.env
nano installer/inventory.env
./installer/bootstrap-threatfox-rpz.sh primary
```

Wygeneruj TSIG:

```sh
install -d -o root -g bind -m 750 /etc/bind/keys
tsig-keygen -a hmac-sha256 threatfox-rpz-xfr > /etc/bind/keys/threatfox-rpz-xfr.key
chown root:bind /etc/bind/keys/threatfox-rpz-xfr.key
chmod 640 /etc/bind/keys/threatfox-rpz-xfr.key
```

W `named.conf.local` dodaj:

```conf
include "/etc/bind/named.conf.rpz";
```

Wewnątrz `options {}` dodaj:

```conf
include "/etc/bind/named.conf.rpz-options";
```

Pobierz i aktywuj:

```sh
/usr/local/sbin/update-threatfox-rpz
named-checkconf && systemctl reload named
rndc zonestatus rpz.threatfox.abuse.ch
systemctl daemon-reload
systemctl enable --now threatfox-rpz.timer
systemctl list-timers threatfox-rpz.timer
```

## 9. ThreatFox na dns2

Skopiuj ten sam TSIG bezpiecznym kanałem do
`/etc/bind/keys/threatfox-rpz-xfr.key` na dns2 i ustaw `root:bind`, `0640`.
Następnie:

```sh
cp installer/inventory.env.example installer/inventory.env
nano installer/inventory.env
./installer/bootstrap-threatfox-rpz.sh secondary
```

Dodaj oba include'y i kategorię `rpz` jak na dns1, potem:

```sh
named-checkconf && systemctl reload named
rndc zonestatus rpz.threatfox.abuse.ch
journalctl -u named --since '5 minutes ago' | grep -E 'Transfer|TSIG|rpz'
```

Oczekuj `Transfer status: success` i `TSIG threatfox-rpz-xfr`.

## 10. Test audytu RPZ

`policy disabled log yes` wykrywa IOC, ale nie blokuje. Wykonaj zapytanie do
domeny obecnej w aktualnym feedzie i sprawdź:

```sh
tail -n 30 /var/log/named/security.log
```

Oczekiwany wpis zawiera:

```text
disabled rpz QNAME NXDOMAIN rewrite ... via ...rpz.threatfox.abuse.ch
```

Normalna odpowiedź A jest prawidłowa w audycie. Zmiana na `policy given`
włącza realne akcje zapisane w feedzie i powinna nastąpić dopiero po analizie.

## 11. Fail2Ban

Pliki przykładowe są w `servers/dns*/etc/fail2ban/`. Najpierw wpisz własne
adresy administracyjne w `ignoreip`, następnie:

```sh
fail2ban-client -t
systemctl restart fail2ban
fail2ban-client status
nft list ruleset
```

Dla DNS oczekuj UDP 53 oraz TCP 53, 443, 853, osobno dla IPv4 i IPv6.

## 12. Hazard

Snapshot zawiera obecny model wielu lokalnych stref. Zmień dokumentacyjny
adres w `db.hazard-redirect` na właściwy adres strony blokady. Generowany plik
`named.conf.hazard-redirect` zawsze sprawdzaj przez `named-checkconf` przed
reloadem.

## 13. Kontrola końcowa

Na obu serwerach:

```sh
named-checkconf
rndc status
free -h
ps -C named -o pid,%cpu,%mem,rss,vsz,cmd
dig @127.0.0.1 google.com A
ss -lntup | grep -E ':(53|443|853)\b'
fail2ban-client status
```

Na dns2 dodatkowo:

```sh
rndc zonestatus rpz.threatfox.abuse.ch
```

Po każdej zmianie używaj:

```sh
named-checkconf && systemctl reload named
```

Jeżeli walidacja zgłasza błąd, nie przeładowuj usługi.
