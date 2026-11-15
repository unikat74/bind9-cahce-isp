# Fione — stała ACL DNS na firewallu, 15 listopada 2026

Na polecenie operatora wdrożono kolejno dns2 (78.31.90.59), następnie dns1
(78.31.90.58). BIND na obu ma także ustawiony wcześniej limit cache 2 GiB.

## Zakres

`/etc/nftables.conf` zarządza wyłącznie tabelą `inet isp_dns` — bez flush ruleset.
Stała ACL jest odczytana z aktywnej klienci_sieci w BIND. Łańcuch INPUT,
priorytet -10, przepuszcza loopback i dozwolone źródła; pozostałe odrzuca
na UDP 53/853/8443 oraz TCP 53/443/853/8443. Inne porty nie są zmieniane.
ACL rekursji/cache w BIND pozostaje dodatkowym zabezpieczeniem.

Włączono autostart nftables. Drop-in
`/etc/systemd/system/nftables.service.d/isp-dns.conf` zastępuje ExecStop
usunięciem tylko tabeli isp_dns; start/reload także dotyka tylko własnej tabeli.
Zachowano tabele DoQ, DNSCrypt i Fail2Ban oraz istniejące bany.

Domowy adres operatora 188.137.37.190/32 dodano trwale i w stanie aktywnym do:
BIND, ACL dnsdist, isp_dns, isp_doq, isp_dnscrypt (dns2: isp_dnscrypt_test)
i ignoreip czterech jaili DNS. Wyjątek SSH już istniał. Żaden klucz nie był zmieniany.

## Odbiór

112 zapytań między resolverami: IPv4/IPv6 × DNS UDP/TCP, DoT, DoH, DoQ,
DNSCrypt UDP/TCP × poprawny DNSSEC (AD), błędny DNSSEC (SERVFAIL),
ThreatFox api.kookjar.com (NXDOMAIN), antyhazard dnscrypt-test.1xbet.ac (NXDOMAIN).

Z dns1 FUZ, spoza ACL, sprawdzono brak dostępu do DNS UDP/TCP i TCP
443/853/8443 po obu rodzinach. DoQ także odrzucone. Wzrost liczników DROP
potwierdzono; unikalne zapytanie firewall-deny-check.example.org nie dotarło
do logu BIND. Próby domowego IP nie wykonywano z fizycznej sieci domowej;
potwierdzono zgodność konfiguracji i aktywnych zestawów wszystkich warstw.

Test reload nftables na obu hostach zachował pozostałe tabele i wyjątek
administracyjny. DNS/DNSSEC i DoQ/RPZ po zmianie działają. Brak failed units.
Nie wykonywano restartu systemów. Późniejsze rozszerzenie ACL o adres domowy
wymagało krótkiego restartu tylko dnsdist na każdym hoście.

## Kopie i rollback

- dns1: `/root/dns-firewall-before-rk24vh9m`, `/root/dns-home-access-1bbuhf7d`,
  cache: `/root/bind-cache-2g-ny6bydkn`.
- dns2: `/root/dns-firewall-before-p8r1kdg1`, `/root/dns-home-access-15um9rch`,
  cache: `/root/bind-cache-2g-9eul4qnk`.

Wycofanie samej stałej ACL: wyłączyć/zatrzymać nftables (drop-in usuwa tylko
isp_dns), zachować kopię nowej konfiguracji i przywrócić poprzedni plik
nftables.conf; usunąć własny drop-in i wykonać daemon-reload. Poprzednia usługa
była disabled. Nie uruchamiać starego pliku z flush ruleset na aktywnych banach.
Nie cofać wyjątku domowego przy wycofywaniu samej ACL firewalla.

## Rozdzielenie logów po wdrożeniu firewalla

Na obu hostach (dns2, następnie dns1) zmieniono blok logging w
`/etc/bind/named.conf`: security zapisuje do `/var/log/named/security.log`,
RPZ do `/var/log/named/rpz.log`, severity info, natywna rotacja BIND
20 MiB i 5 wersji na każdy plik, jak w FUZ. Wyłączono osobny wpis
logrotate `/etc/logrotate.d/named-security`, aby uniknąć podwójnej rotacji.
Stare pliki i mieszana historia w security.log pozostają zachowane.

Test RPZ api.kookjar.com zapisał rewrite wyłącznie w rpz.log. Test odmowy
AXFR na localhost zapisał denied w security.log. Fail2Ban nadal czyta
security.log, usługi named i fail2ban aktywne. Przeładowano konfigurację
bez restartu BIND. Kopie: dns1 `/root/bind-split-logs-t3t5ggu6`,
dns2 `/root/bind-split-logs-dlstlmre` (named.conf i named-security).

## Ochrona NTP

Na obu serwerach dodano ntp_clients4/ntp_clients6 z efektywnej ACL chrony,
nie z szerszej ACL DNS. Zachowano m.in. 172.31.254.3/32; do obu warstw dodano
188.137.37.190/32 (chrony: /etc/chrony/conf.d/admin-home.conf).
Firewall przyjmuje UDP/123 tylko z tych zestawów i odrzuca pozostałe źródła.
Nie zmieniano portów DNS, SSH, ICMP, upstreamów NTP ani zegara.

Testy: odpowiedź NTP stratum 2/3 z drugiego DNS-a po IPv4 i IPv6;
próby z FUZ po obu rodzinach bez odpowiedzi, potwierdzone licznikami DROP.
chronyc accheck potwierdza wyjątek domowy i dotychczasowe sieci. Synchronizację
upstream sprawdzono po chronyc burst 2/2; DNS nadal odpowiada z AD.
Kopie nftables.conf: dns1 /root/ntp-firewall-before-gonf8z51,
dns2 /root/ntp-firewall-before-u0q6db15. Chrony bez restartu; runtime allow
oraz plik conf.d zapewniają działanie teraz i po restarcie.
