# Wdrożenie DoQ na dns2 — 13 września 2026

DoQ uruchomiono na publicznych adresach IPv4 i IPv6 dns2, UDP 853.
dns1 nie był modyfikowany. DNSCrypt pozostaje wyłączony.

Później tego samego dnia DoQ wdrożono również na dns1 i wykonano pozytywne
testy sieciowe między oboma resolverami w IPv4/IPv6. Wyniki uzupełniające
zawiera [`DOQ-DNS1-DEPLOYMENT.md`](DOQ-DNS1-DEPLOYMENT.md).

## Stan przy odbiorze

- Debian 13 amd64, BIND 9.20.26, dnsdist 2.1.2 z repozytorium PowerDNS.
- BIND zachował działający proces podczas wdrożenia; przez reload dodano
  listener PROXYv2 na `127.0.0.1:5300`.
- dnsdist obsługuje DoQ i diagnostykę na `127.0.0.1:5301`. Brak dodatkowego
  cache lub alternatywnego backendu omijającego BIND/RPZ.
- ACL dnsdist odpowiada pełnej aktualnej ACL `klienci_sieci`.
- Osobna tabela nftables `inet isp_doq` ogranicza tylko UDP 853.
  Dotychczasowe tabele Fail2Ban pozostają bez zmian.
- `isp-doq-firewall.service` ładuje reguły przy starcie; dnsdist wymaga tej
  jednostki i uruchamia się po niej. Obie jednostki są enabled.
- Certbot ma osobny hook `dnsdist-tls` i kopię pary TLS dla dnsdist.
  Dotychczasowy hook `bind-tls` pozostaje aktywny.

## Wykonane testy

| Kontrola | Wynik |
|---|---|
| DoQ IPv4 i IPv6 z weryfikacją certyfikatu | NOERROR |
| Poprawna domena DNSSEC | odpowiedź z flagą AD |
| dnssec-failed.org | SERVFAIL |
| DNSKEY strefy głównej przez DoQ | NOERROR |
| Domena z aktywnego rejestru hazardowego | A = 145.237.235.240 |
| Niezdefiniowana subdomena hazardowa | NXDOMAIN |
| Trafienie ThreatFox | audyt; IP klienta w logu RPZ dla obu rodzin |
| Niezgodna nazwa certyfikatu | klient odrzuca połączenie |
| DNS UDP/TCP 53, DoT, DoH — IPv4 i IPv6 | NOERROR |
| Zewnętrzny host spoza ACL, IPv4 i IPv6 | brak QUIC; wzrost licznika drop |
| Certbot dry-run z obydwoma deploy-hookami | sukces |
| DoQ, DoT i DoH po wykonaniu hooków | działają w obu rodzinach |
| Uszkodzone jednostki systemd | 0 |

Pozytywne zapytania wykonano z dns2 do jego publicznych adresów, a próbę
odmowy z zewnętrznego hosta. Nie wykonano jeszcze pozytywnego testu z
urządzenia abonenta ani testu wydajności. Nie restartowano całego serwera.
Próba Certbota używała testowego CA i aktualnego certyfikatu przy wykonaniu
hooków; nie wymuszała nowego certyfikatu produkcyjnego.

Strefy pozostały secondary. Seriale przy odbiorze: ThreatFox `2609130059`,
hazard `1789112930`. Są to wartości historyczne, nie seriale oczekiwane
przy kolejnych aktualizacjach.

## Pliki i wycofanie

Zanonimizowany snapshot `servers/dns2/` zawiera konfigurację dnsdist,
listener BIND, `tls-hostname`, tabelę `/etc/nftables.d/isp-doq.nft`,
`isp-doq-firewall.service`, drop-in zależności dnsdist i hook `dnsdist-tls`.
Klucze i certyfikaty pozostają wyłącznie na serwerze. Snapshotów nie kopiuj
na produkcję — zawierają adresy dokumentacyjne.

Kopia sprzed zmiany znajduje się na dns2 w
`/root/doq-dns2-20260913-gB1smr/`. Zawiera chronione archiwum, poprzedni
`named.conf.options`, zapis firewalla, wyniki końcowe i `rollback.sh`.
Automatyczny timer wycofania anulowano po pozytywnych testach. Ręczne
uruchomienie skryptu wyłącza DoQ i jego firewall, przywraca opcje BIND-a
oraz wyłącza nowy hook Certbota; nie odinstalowuje pakietów.

Przy zmianie sieci klientów synchronizuj ACL BIND-a, dnsdist i zestawy
nftables. Odnowienie TLS restartuje dnsdist; sesje DoQ wymagają ponownego
połączenia. Pozostałe protokoły obsługuje BIND.

## Uzupełnienie Fail2Ban — 13 września 2026

Jaile `named-cache-denied-udp` i `named-cache-denied-udp6` rozszerzono
z UDP 53 na UDP `53,853`. Konfiguracja przeszła `fail2ban-client -t`.
Przeładowano tylko te jaile i atomowo zmieniono dopasowanie portów trzech
aktywnych reguł nftables, bez opróżniania zestawów adresów. Liczby banów
w tych jailach przed i po zmianie: odpowiednio 25 i 5; nie usunięto żadnego.
Potwierdzono porty w działających akcjach Fail2Ban i regułach nftables.
Testy DoQ między serwerami po IPv4 i IPv6, z weryfikacją certyfikatu,
zwróciły NOERROR i AD. Usługi named, dnsdist i Fail2Ban są aktywne.

Kopia konfiguracji oraz reguły przed/po zmianie:
`/root/f2b-doq-20260913T185231Z/`. Plik `rollback-rules.nft` przywraca stare
dopasowania portów przy niezmienionych uchwytach reguł. Przy wycofaniu
należy również przywrócić kopię `named-cache-denied.local`, sprawdzić
konfigurację i przeładować oba jaile.

Detekcja nadal opiera się na odmowach BIND. Odmowy ACL dnsdist i błędy
QUIC nie są nowym źródłem banów; sieci w `ignoreip` pozostają wyłączone.
