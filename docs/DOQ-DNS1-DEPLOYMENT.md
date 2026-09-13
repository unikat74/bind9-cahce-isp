# Wdrożenie DoQ na dns1 — 13 września 2026

DoQ uruchomiono również na dns1, na publicznych adresach IPv4 i IPv6,
UDP 853. Oba resolvery obsługują teraz DoQ. DNSCrypt pozostaje wyłączony.

## Konfiguracja

Debian 13 amd64, BIND 9.20.26 i dnsdist 2.1.2. Układ odpowiada dns2:
dnsdist → PROXYv2 → BIND `127.0.0.1:5300`, bez dodatkowego cache i bez
backendu omijającego RPZ. Diagnostyka dnsdist: `127.0.0.1:5301`.

ACL dnsdist i tabela nftables `inet isp_doq` pochodzą z pełnej, aktualnej
ACL `klienci_sieci` na dns1. Firewall ogranicza wyłącznie UDP 853.
Dotychczasowe reguły Fail2Ban i pozostałe porty pozostają bez zmian.
`dnsdist.service` wymaga `isp-doq-firewall.service`; obie jednostki są
enabled. Nowy hook Certbota `dnsdist-tls` współistnieje z `bind-tls`.
BIND został przeładowany, zachował działający proces i 25 stref.

## Odbiór

| Kontrola | Wynik |
|---|---|
| DoQ do dns1 po IPv4 i IPv6 z weryfikacją TLS | NOERROR |
| Poprawna domena DNSSEC | flaga AD |
| dnssec-failed.org | SERVFAIL |
| DNSKEY strefy głównej | NOERROR |
| Aktualna domena hazardowa | 145.237.235.240 |
| Niezdefiniowana subdomena hazardowa | NXDOMAIN |
| Domena ThreatFox | NOERROR i wpis disabled rpz, bez blokowania |
| Błędna nazwa certyfikatu TLS | odrzucenie przez klienta |
| DNS UDP/TCP, DoT i DoH na dns1, obie rodziny | NOERROR, także po wykonaniu hooków |
| DoQ dns2 → dns1 i dns1 → dns2, IPv4/IPv6 | zwykły DNS, DNSSEC i obie RPZ działają |
| Adres klienta w logach RPZ dns1 | rzeczywiste IP dns2 w IPv4 i IPv6 |
| Zewnętrzny host spoza ACL, IPv4/IPv6 | brak QUIC; licznik drop wzrósł |
| Certbot dry-run z obydwoma deploy-hookami | sukces |
| named, dnsdist, firewall | active; brak uszkodzonych jednostek systemd |

Testy między serwerami potwierdzają działanie przez sieć, poza lokalną
ścieżką hosta. Nie wykonano testu urządzenia abonenta ani testu obciążenia.
Nie restartowano systemu. Odnowienie sprawdzono przez testowe CA Certbota
z uruchomieniem hooków na aktualnym certyfikacie produkcyjnym.

RPZ na dns1 pozostały primary, na dns2 secondary. Przy odbiorze seriale
były zgodne: ThreatFox `2609130059`, hazard `1789112930`. Włączone są
dotychczasowe timery ThreatFox, hazardu i Certbota.

## Snapshot i rollback

Zanonimizowane konfiguracje DoQ znajdują się w `servers/dns1/`; nie
zawierają certyfikatów, kluczy ani feedów. Snapshot nie jest konfiguracją
do bezpośredniego skopiowania na serwer.

Chroniona kopia na dns1: `/root/doq-dns1-20260913-b98TrF/`.
Zawiera konfigurację sprzed zmiany, firewall, wyniki końcowe i `rollback.sh`.
Skrypt wyłącza dnsdist, nowy hook i osobny firewall DoQ oraz przywraca
poprzednie opcje BIND-a przez reload. Nie odinstalowuje pakietów.
Automatyczny timer rollbacku anulowano po testach.

Przy zmianie sieci klientów aktualizuj ACL BIND-a, dnsdist i zestawy
nftables. Hook odnowienia TLS restartuje dnsdist, co wymaga ponownego
połączenia sesji DoQ; pozostałe protokoły obsługuje BIND.

## Uzupełnienie Fail2Ban — 13 września 2026

Jaile `named-cache-denied-udp` i `named-cache-denied-udp6` rozszerzono
z UDP 53 na UDP `53,853`. Konfiguracja przeszła `fail2ban-client -t`.
Przeładowano tylko te jaile i atomowo zmieniono dopasowanie portów trzech
aktywnych reguł nftables, bez opróżniania zestawów adresów. Liczby banów
w tych jailach przed i po zmianie: odpowiednio 160 i 4; nie usunięto żadnego.
Potwierdzono porty w działających akcjach Fail2Ban i regułach nftables.
Testy DoQ między serwerami po IPv4 i IPv6, z weryfikacją certyfikatu,
zwróciły NOERROR i AD. Usługi named, dnsdist i Fail2Ban są aktywne.

Kopia konfiguracji oraz reguły przed/po zmianie:
`/root/f2b-doq-20260913T185223Z/`. Plik `rollback-rules.nft` przywraca stare
dopasowania portów przy niezmienionych uchwytach reguł. Przy wycofaniu
należy również przywrócić kopię `named-cache-denied.local`, sprawdzić
konfigurację i przeładować oba jaile.

Detekcja nadal opiera się na odmowach BIND. Odmowy ACL dnsdist i błędy
QUIC nie są nowym źródłem banów; sieci w `ignoreip` pozostają wyłączone.
