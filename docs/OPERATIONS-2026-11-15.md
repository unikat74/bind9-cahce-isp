# FUZ i Fione — zamknięcie uzgodnień z 15 listopada 2026

Obowiązujący stan i przyszłe wdrożenia: [RESOLVER-STANDARD.md](RESOLVER-STANDARD.md).
Poniższy zapis uzupełnia raporty wcześniejszych etapów; nie jest alternatywną
polityką. Zmiany wykonywano na jednym serwerze naraz, dns2 przed dns1.

## Wykonane na produkcji

- FUZ: DoQ i DNSCrypt, lokalna strefa localhost i test backendu dnsdist localhost A.
- Obie pary: cache 2 GiB, recursive-clients 10000, tcp-clients 1000.
- Fione: stała ACL DNS i NTP w nftables, z zachowaniem dotychczasowych wyjątków;
  BIND allow-query ograniczone do klienci_sieci. Domowy 188.137.37.190/32
  we wszystkich właściwych warstwach. SSH-only 78.31.90.144/32 zachowane.
- Obie pary: dwa TSIG, osobne uprawnienia transferów i NOTIFY dla hazardu/ThreatFox.
  Fione: pozytywne transfery z właściwymi kluczami i odmowy po zamianie kluczy.
- FUZ: osobny jail sshd-ip6 i rozdzielenie naliczania rodzin. IPv4 następnie
  ujednolicone z Fione: 1h i narastanie do 7d. IPv6: 1d i narastanie do 7d.
- Osobne security.log i rpz.log; logrotate daily + maxsize 20M, 7 archiwów,
  opóźniona kompresja i kontrola co godzinę, osobna jednostka i stan.
- Antyhazard na dns1 obu par: 06:00 i 18:00 Europe/Warsaw.
- ThreatFox na dns1 obu par: 03:17 Europe/Warsaw + losowo do 20 min.
- Własny Auth-Key FUZ podmieniony przez operatora; pobranie i replikacja sprawdzone.

IPv6 działa do Google na FUZ. Forwardery Cloudflare IPv6 pozostają pominięte,
ponieważ brama zgłaszała network unreachable do obu adresów. To wyjątek
routingu upstream, a nie wyłączenie IPv6 w resolverach.

## Dowody odbioru i ograniczenia

112 zapytań na parę podczas wdrażania frontendów/firewalla: DNS UDP/TCP,
DoT/DoH, DoQ, DNSCrypt UDP/TCP po obu rodzinach, AD, SERVFAIL i obie RPZ.
Każdą późniejszą zmianę limitów sprawdzono przez rndc status i odpowiedzi DNS.
Lokalny localhost na FUZ daje autorytatywne A/AAAA bez rekursji, DoQ z TLS
przeszło po obu rodzinach po restarcie tylko dnsdist.

Realna rotacja i ponowny zapis obu logów, druga rotacja i gzip -t poprawne.
NTP odpowiada z dozwolonych źródeł IPv4/IPv6; z FUZ do Fione testy spoza ACL
zostały odrzucone i zwiększyły DROP. Chrony nadal odbiera świeże próbki upstream.
Filtry SSH przeszły próbki offline IPv4/IPv6 oraz test ignorecommand;
ban/unban dokumentacyjnego IPv6 sprawdzono w nftables. Nie generowano sztucznych
włamań w produkcyjnym journalu. Stare bany zachowano.

Wyjątek domowy potwierdzono w aktywnych konfiguracjach i zestawach;
nie wykonano testu z fizycznego łącza domowego. Nie restartowano systemów.

## Kopie ostatnich zmian

| Zmiana | dns2 | dns1 |
|---|---|---|
| FUZ TCP 1000 | /root/bind-tcp-1000-2bz1xp4d | /root/bind-tcp-1000-1vzne4tx |
| Fione TCP 1000 | /root/bind-tcp-1000-dkzajmoi | /root/bind-tcp-1000-hqmonn5p |
| Fione rekursja 10000 | /root/bind-recursive-10000-fo7f685r | /root/bind-recursive-10000-4c3dee85 |
| Fione allow-query ACL | /root/bind-allow-query-before-sfrku_cm | /root/bind-allow-query-before-baxu3nh0 |
| FUZ lokalny health check | /root/dnsdist-local-health-before-ipbrcdkt | /root/dnsdist-local-health-before-uxjh6v88 |
| FUZ SSH IPv6 | /root/ssh-ipv6-before-ln2v7hld | /root/ssh-ipv6-before-ng9rmf0s |
| FUZ SSH IPv4 1h | /root/sshd-ban-policy-before-8jg_ccah | /root/sshd-ban-policy-before-2urke28r |

Dodatkowo Fione dns2 NOTIFY: /root/threatfox-notify-before-tf59ughk;
rozdzielenie TSIG: dns2 /root/rpz-tsig-prepare-6mgxark6 i
/root/rpz-tsig-secondary-yav6t3uz; dns1
/root/rpz-tsig-primary-transition-rsrx3930 oraz /root/rpz-tsig-primary-final-t9m4nbjn.
Timer antyhazardu Fione dns1: /root/hazard-timer-before-qho2b1k7.
Timer ThreatFox FUZ dns1: /root/threatfox-timer-before-74c5d37k.
Kopie firewalla i logrotate opisują FIONE-FIREWALL-2026-11-15.md oraz
DNS-LOG-ROTATION-2026-11-15.md. Klucze i kopie z sekretami zostają na hostach.
