# Porównanie z 78.31.90.58 — 4 listopada 2026

Wzorzec odczytano na żywo, bez zmian na `78.31.90.58`. Nowe resolvery:
dns1 `193.192.179.11`, dns2 `193.192.179.12`.

| Element | Wzorzec 78.31.90.58 | Nowe dns1/dns2 |
|---|---|---|
| BIND | 9.20.30 | 9.20.30 |
| Rekurencja/cache | forward only, ACL klientów | Tak samo, własne trzy sieci |
| Upstreamy | Cloudflare/Google IPv4 i IPv6 | Te same IPv4; IPv6 wstrzymane przez problem upstreamu |
| DNSSEC | auto | auto |
| Limity TCP/rekurencji | 750 / 1500 | 750 / 1500 |
| Cache | limit zależny od domyślnego ustawienia BIND | jawnie 1 GiB |
| EDNS/odpowiedzi | UDP 1232, minimal responses/any, prefetch 2 9 | zgodne; dodatkowo jawny edns-udp-size 1232 |
| Zwykły DNS | wszystkie interfejsy | konkretne adresy usługi i loopback |
| allow-query | any; rekurencja i cache przez ACL | również same zapytania ograniczone ACL |
| DoT/DoH | TCP 853 / 443, IPv4/IPv6 | działa na własnych adresach i certyfikatach |
| DoQ | dnsdist UDP 853, PROXYv2 do BIND 5300 | brak |
| DNSCrypt | proces encrypted-dns na UDP/TCP 8443 | brak |
| Antyhazard | RPZ, aktualizacja co godzinę | RPZ primary/secondary TSIG, 06:00 i 18:00 zgodnie ze zleceniem |
| ThreatFox | RPZ policy nxdomain | brak |
| Statystyki | jawne ścieżki dump/statistics/memstatistics | brak jawnych ścieżek w options |
| Strefy lokalne | localhost, reverse loopback/broadcast, RFC1918 | tylko root hints i RPZ; brak odpowiedników lokalnych stref wzorca |
| SSH Fail2Ban | osobne jaile v4/v6 | jeden jail systemowy obsługujący obie rodziny |
| DNS Fail2Ban | cztery jaile UDP/TCP × v4/v6 | wdrożone i przetestowane jak niżej |

## Stan po uzupełnieniu dns2

Powyższa tabela opisuje porównanie przed uzupełnieniem frontendów.
Na dns2 wdrożono potem DoQ i DNSCrypt; na dns1 nie rozszerzano frontendów
w tym etapie. Oba nowe hosty mają dodatkową sieć DNS `10.0.0.0/20`.
ThreatFox aktywowano: dns1 pobiera feed z osobnym Auth-Key, dns2 replikuje
strefę przez TSIG. Potwierdzono zgodne seriale i NXDOMAIN na obu hostach. Aktualne kroki: [DNS-EXTENSIONS-INSTALL.md](DNS-EXTENSIONS-INSTALL.md).

## Wdrożona ochrona DNS

Na obu nowych hostach:

- `/var/log/named/security.log`: kategoria BIND security, źródło Fail2Ban.
- `/var/log/named/rpz.log`: osobno zdarzenia antyhazardu, bez banowania klientów
  za trafienie w RPZ.
- Oba logi rotuje BIND: 20 MiB i pięć wersji archiwalnych na log.
  Konfiguracja w `/etc/bind/named.conf.logging`.
- Jaile `named-cache-denied-udp`, `named-cache-denied-tcp`,
  `named-cache-denied-udp6`, `named-cache-denied-tcp6`.
- Jak na wzorcu: dwie odmowy w 60 minut, ban na dwa dni, DROP przez nftables;
  UDP 53/853/8443, TCP 53/443/853/8443.
- Wyjątki: odpowiednie rodziny trzech sieci klientów i localhost. Zwykły ruch
  klientów, także wspólny NAT, nie jest powodem bana w tych jailach.
- Filtry rozdzielają rodziny adresów; dodatkowo obsługują odmowę query bez
  dopisku `(cache)`, występującą przy ograniczeniu allow-query.

Firewall nadal odrzuca DNS spoza ACL przed BIND-em. Takie pakiety nie
powodują logu BIND ani bana Fail2Ban — są już blokowane. Jaile stanowią
dodatkową ochronę odmów docierających do BIND; nie są limiterem ruchu
dozwolonych klientów ani ochroną przed nasyceniem łącza.

## Test wykonania, nie tylko konfiguracji

Najpierw dns2, potem dns1. Izolowane klienty veth/netns `192.0.2.2`
i `2001:db8:ffff::2` wysłały po dwie próby niedozwolonej rekurencji.
Tymczasowy wyjątek firewalla dotyczył wyłącznie interfejsu testowego,
aby zapytania dotarły do ACL BIND. Wynik:

- rzeczywiste odmowy zapisane w security.log;
- automatyczne bany we wszystkich czterech jailach;
- oba adresy obecne w odpowiednich zbiorach nftables;
- próby TCP po banie zablokowane w obu rodzinach;
- na końcu usunięto testowe bany, regułę, trasy i namespace;
- działają DNSSEC i antyhazard; brak failed units na obu hostach.

Kopie sprzed zmiany: `/root/pre-dns-fail2ban/` na każdym hoście.
Dowód testów: `live-test.log` w tym katalogu; skrypt na hoście
`/root/test-dns-f2b.sh`. Nie uruchamiać skryptu deploy ponownie bez przeglądu.
W repozytorium docelowe jaile/filtry/akcja są w `fail2ban/`.
