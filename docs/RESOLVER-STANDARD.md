# Obowiązujący standard resolverów FUZ i Fione

Uzgodniony 15 listopada 2026. Ten dokument i `installer/resolver_policy.py`
określają aktualne założenia. Raporty z datą opisują historię, a `servers/`
jest zanonimizowanym, historycznym snapshotem — nie źródłem nowej instalacji.

## Ustawienia wspólne

| Obszar | Standard |
|---|---|
| BIND cache | max-cache-size 2G; limit cache, nie całego procesu |
| Rekursja | recursive-clients 10000, próg miękki 9900 |
| TCP BIND | tcp-clients 1000 |
| Zapytania/cache/rekursja | allow-query, allow-query-cache, allow-recursion: klienci_sieci |
| Firewall | Stała ACL DNS przed BIND: UDP 53/853/8443, TCP 53/443/853/8443 |
| NTP | Osobna, jawna ACL chrony i zestawy ntp_clients4/6, pozostałe UDP/123 DROP |
| SSH IPv4 | 5 prób/10 min, ban 1h, narastanie ×2 do 7 dni |
| SSH IPv6 | Osobny jail, 5 prób/60 min, ban 1d, narastanie ×2 do 7 dni |
| Wyjątki | Domowy administrator 188.137.37.190/32 w DNS, NTP i SSH |
| Logi | security.log dla Fail2Ban, rpz.log dla obu RPZ; severity info |
| Rotacja | logrotate daily + maxsize 20M, 7 archiwów, compress/delaycompress |
| Kontrola rozmiaru | Co godzinę, osobny timer i plik stanu; próg nie jest twardym limitem |
| Antyhazard | Tylko dns1, 06:00 i 18:00 Europe/Warsaw, bez losowego opóźnienia |
| ThreatFox | Tylko dns1, 03:17 Europe/Warsaw + losowo 0–20 min |
| Pominięte uruchomienie | Persistent=true dla timerów RPZ i logrotate |
| Transfery i NOTIFY | Dwa różne klucze TSIG: hazard-rpz-xfr i threatfox-rpz-xfr; klucze nie działają zamiennie |
| DoQ | dnsdist → PROXYv2 → BIND 127.0.0.1:5300; health check localhost. A |
| localhost | Lokalna autorytatywna strefa: A 127.0.0.1, AAAA ::1, bez forwardowania |
| DNSCrypt | Osobny encrypted-dns-server; UDP/TCP 8443; stan providera zachowywany |
| DNSSEC/RPZ | DNSSEC auto, ThreatFox NXDOMAIN przed antyhazardem policy given |

Firewall zarządza tylko `inet isp_dns`; reload nie usuwa DoQ, DNSCrypt ani
Fail2Ban. Drop-in ExecStop usuwa wyłącznie własną tabelę. Nie używamy globalnego
flush ruleset. SSH, ICMP i port walidacji certyfikatu nie są ograniczane przez
ACL portów DNS. Ochrona przed przeciążeniem łącza nadal wymaga ochrony upstream.

7 archiwów nie oznacza gwarantowanych 7 dni przy rotacji rozmiarowej.
Najnowsze archiwum zostaje nieskompresowane do kolejnej rotacji, aby Fail2Ban
mógł dokończyć odczyt. Nie uruchamiamy równolegle natywnej rotacji BIND.

## Co celowo różni sieci

Publiczne profile bez sekretów: `installer/profiles/fuz.toml`, `fione.toml`.
Adresy listenerów, certyfikaty, bramy, interfejsy i tożsamości DNSCrypt pozostają
hostowe. Każda sieć ma własny Auth-Key ThreatFox, tylko na dns1 w
`/etc/threatfox.env` (root:root 0600). Klucze TSIG są różne także między sieciami.

FUZ: forwardery Cloudflare/Google IPv4 i Google IPv6. Cloudflare IPv6 pominięto
po odpowiedzi bramy network unreachable; nie dodawać go bez testu routingu i DNS.
Fione: również forwardery Cloudflare IPv6. Listę upstreamów weryfikujemy z hosta.
NTP Fione zachowuje m.in. 172.31.254.3/32, ale nie dostaje automatycznie prywatnych
sieci DNS. Wyjątek 78.31.90.144/32 jest tylko dla SSH Fione; nie rozszerza NTP/DNS.

## Nowa instalacja

Najpierw bazowy Debian/BIND/TLS według INSTALL.md. Potem nowy, wspólny etap:

```sh
python3 installer/bootstrap-resolver-policy.py installer/profiles/fuz.toml --output /tmp/fuz-policy
# Przejrzyj profil: właściwa sieć, wszystkie wyjątki NTP/SSH, osiągalne forwardery.
python3 installer/bootstrap-resolver-policy.py installer/profiles/fuz.toml --install
```

Dla Fione użyj profilu fione.toml. Dla innej sieci utwórz własny profil o polach
clients, ntp_clients, administrators, forwarders oraz opcjonalnym
ssh_administrators (wyjątki tylko dla SSH). Puste lub otwarte ACL są zabronione.
Administratorzy są dodawani do ACL DNS/NTP/SSH; loopback jest dodawany automatycznie.

Instalator ustawia politykę BIND przez include **wewnątrz options**, zachowując
TLS/listenery i RPZ. Instaluje osobną lokalną strefę tylko jeśli jej nie ma,
firewall DNS/NTP, jaile DNS i SSH, logi, logrotate i ACL chrony. Nie instaluje
pakietów, certyfikatów ani kluczy API. Wymaga działających BIND/chrony/Fail2Ban,
Debiana 13, logrotate i Python 3.11+. Nie uruchamiaj po nim starego instalatora
ochrony DNS — jest kompatybilnym etapem częściowym, nie pełnym standardem.

Przed zmianami waliduje profil, chroni dotychczasowe wyjątki DNS/NTP/SSH,
sprawdza dostępność forwarderów, named-checkconf, nft -c, Fail2Ban i logrotate. Zapisuje manifest kopii
w /root/resolver-policy-before-*. Przy błędzie przywraca pliki i własną tabelę
firewalla, bez odtwarzania całego rulesetu nad aktualnymi banami.
Istniejące inline logging lub konkurencyjne wpisy logrotate powodują odmowę
instalacji: najpierw przygotuj migrację z --output i kopią aktualnych plików.
Nie uruchamiamy instalatora ponownie na produkcji tylko w celu testowania go.

Następnie DoQ, DNSCrypt i RPZ według DNS-EXTENSIONS-INSTALL.md. Inventory
frontendów musi zawierać pełną ACL profilu wraz z administratorami i loopback;
preflight porównuje ją z BIND. Nie zmieniaj istniejącego providera/instancji
DNSCrypt (historyczny dns2 Fione ma isp-dnscrypt-test i dns2-test.fione.pl).

DoQ wymaga lokalnej odpowiedzi localhost A z NOERROR i AA; instalator sprawdza
to przed zmianami. Awaria upstreamu nie ma oznaczać niedostępności backendu.
Zewnętrzną rezolucję sprawdzamy osobnym zapytaniem monitorującym.

## RPZ i migracje istniejących hostów

Nowa wspólna instalacja RPZ wymaga **dwóch** plików TSIG. Generuj je tylko na
primary, osobno, z umask 077; ustaw root:bind 0640 i przenieś bez wyświetlania
na secondary. Istniejących kluczy nie regeneruj. ThreatFox bootstrap zarządza
wyłącznie ThreatFox; nie zmienia klucza hazardu.

Przy rozdzielaniu starego wspólnego TSIG: dodaj nowy klucz na dns2, przejściowo
dopuść oba dla hazardu na primary, przełącz podpis NOTIFY i primary/key na dns2,
sprawdź transfer, następnie usuń stary klucz z uprawnień hazardu. Dla obu stref
secondary wymaga allow-notify z właściwym kluczem; allow-transfer none.

Przy migracji logów: usuń tylko stary blok logging/konkurencyjną rotację po
wykonaniu kopii; nie kasuj historii. Po realnej rotacji sprawdź nowe wpisy
security i RPZ, odczyt Fail2Ban oraz gzip -t. Nie używaj copytruncate.

Kolejność każdej zmiany: dns2 → odbiór → dns1. Odbiór: DNS UDP/TCP, DoT/DoH,
DoQ i DNSCrypt UDP/TCP po obu rodzinach; AD, SERVFAIL, obie RPZ, seriale,
transfery TSIG oraz odrzucenia z obcej sieci potwierdzone licznikami. NTP:
prawdziwa odpowiedź z dozwolonej sieci, DROP obcej i nadal świeża synchronizacja
upstream. SSH: separacja rodzin, zachowane bany i wyjątki, ban/unban testowego
adresu dokumentacyjnego w nftables. Sam status active nie wystarcza.

## Walidacja automatyzacji

Testy jednostkowe obejmują politykę, profile, ACL, rozdzielenie kluczy,
parametry SSH i wybór rodzin, zachowanie TLS/RPZ przy edycji options,
blokadę usuwania istniejących klientów, localhost oraz harmonogramy.
Oba wygenerowane profile sprawdzono na Debianie 13: named-checkconf -z
(w tym localhost), nft -c, fail2ban-client -t w kopii konfiguracji,
logrotate --debug z osobnym stanem i systemd-analyze verify. Testy nie
zmieniały aktywnych plików/usług. Powtórz walidację po zmianach profilu.
Pełnego nowego bootstrap-resolver-policy --install nie uruchamiano na świeżej VM;
operacje produkcyjne wykonano wcześniej etapami i mają osobne raporty.
