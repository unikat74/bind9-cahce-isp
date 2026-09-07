# Instalacja BIND ISP — krok po kroku

Poniższa procedura jest dla Debian 13 i BIND 9.20. Wykonuj ją najpierw na
`dns1`, następnie na `dns2`. Przed zmianą zawsze uruchom `named-checkconf`.

## 1. Bazowy resolver

1. Zainstaluj `bind9`, `bind9-utils`, `curl`, `certbot` i `fail2ban`.
2. Skonfiguruj ACL klientów, `allow-recursion` i `allow-query-cache`.
3. Zostaw `allow-transfer { none; };` globalnie.
4. Ustaw forwardery, DNSSEC, `minimal-any yes`, `max-udp-size 1232`.
5. Otwórz dla klientów UDP/TCP 53, TCP 853 i TCP 443; transfery strefy
   dopuszczaj wyłącznie między DNS-ami.

## 2. DoT i DoH

1. Utwórz rekordy A oraz AAAA `dns1.example.net` i `dns2.example.net`.
2. Pobierz certyfikat Let’s Encrypt dla każdej nazwy.
3. Skopiuj certyfikat i klucz do `/etc/bind/tls/` (`root:bind`, pliki `0640`).
4. Dodaj definicje `tls` oraz `http`, potem listenery TCP/853 i TCP/443.
5. Test:

```sh
dig @dns1.example.net google.com A +tls +tls-ca +tls-hostname=dns1.example.net
dig @dns1.example.net google.com A +https +tls-ca +tls-hostname=dns1.example.net
```

## 3. ThreatFox RPZ na dns1

1. Utwórz Auth-Key w ThreatFox i zapisz go wyłącznie jako root:

```sh
install -m 600 -o root -g root /dev/null /etc/threatfox.env
nano /etc/threatfox.env
```

```sh
THREATFOX_AUTH_KEY='WARTOŚĆ_TYLKO_NA_SERWERZE'
```

2. Skopiuj `installer/inventory.env.example` jako `installer/inventory.env`
   i wpisz rzeczywiste adresy. Ten plik jest ignorowany przez Git.
3. Wygeneruj wspólny TSIG i przenieś go bezpiecznym kanałem na dns2:

```sh
install -d -o root -g bind -m 750 /etc/bind/keys
tsig-keygen -a hmac-sha256 threatfox-rpz-xfr > /etc/bind/keys/threatfox-rpz-xfr.key
chown root:bind /etc/bind/keys/threatfox-rpz-xfr.key
chmod 640 /etc/bind/keys/threatfox-rpz-xfr.key
```

4. Uruchom bootstrap na dns1:

```sh
./installer/bootstrap-threatfox-rpz.sh primary
```

5. W `named.conf.local` dodaj:

```conf
include "/etc/bind/named.conf.rpz";
```

   Wewnątrz `options {}` dodaj:

```conf
include "/etc/bind/named.conf.rpz-options";
```

   W bloku `logging {}` dodaj:

```conf
category rpz { security_file; };
```

6. Aktywuj:

```sh
named-checkconf && systemctl reload named
systemctl daemon-reload
systemctl enable --now threatfox-rpz.timer
```

## 4. Secondary RPZ na dns2

1. Skopiuj ten sam plik TSIG do `/etc/bind/keys/` i ustaw `root:bind`, `0640`.
2. Uruchom:

```sh
./installer/bootstrap-threatfox-rpz.sh secondary
```

3. Dodaj te same include’y i kategorię `rpz`, potem:

```sh
named-checkconf && systemctl reload named
rndc zonestatus rpz.threatfox.abuse.ch
```

W logu dns2 oczekuj `Transfer completed` oraz `TSIG threatfox-rpz-xfr`.

## 5. Tryb audytu i blokowanie

Początkowo używaj `policy disabled log yes`. BIND wykrywa domeny IOC, lecz
nie zmienia odpowiedzi. Obserwuj:

```sh
tail -f /var/log/named/security.log | grep --line-buffered 'disabled rpz'
```

Po okresie audytu świadomie zmień `disabled` na `given` tylko jeżeli akceptujesz
blokowanie wskazanych przez ThreatFox domen.

