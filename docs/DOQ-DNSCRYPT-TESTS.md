# Wynik testów lokalnych DoQ i DNSCrypt — 13 września 2026

Testy wykonano w osobnym kontenerze Debian 13 arm64 uruchomionym w lokalnej
VM. Nie łączono się z produkcyjnymi dns1/dns2. Użyto BIND 9.20.26,
dnsdist 2.1.2 z repozytorium PowerDNS, kdig 3.4.6 i dnscrypt-proxy 2.1.8.
Adresy listenerów zastąpiono loopbackiem `127.0.0.2` i `::1`; backend BIND
pozostał `127.0.0.1:5300`. Certyfikat TLS był laboratoryjny, jawnie zaufany
przez klienta. Polityki RPZ dotyczyły lokalnej strefy `lab.test`.

| Próba | Wynik |
|---|---|
| named-checkconf z dodatkowym listenerem PROXYv2 | OK; BIND oznacza allow-proxy jako experimental |
| dnsdist --check-config z DoQ i DNSCrypt | OK |
| DoQ IPv4 oraz IPv6 z weryfikacją TLS | OK |
| DoQ: zwykłe A, RPZ redirect, NXDOMAIN subdomeny, RPZ audit | OK, obie rodziny |
| DoQ: niezgodna nazwa certyfikatu | klient odrzuca, obie rodziny |
| DNSCrypt UDP IPv4 i IPv6: zwykłe A, redirect, NXDOMAIN, audit | OK |
| DNSCrypt TCP: pobieranie certyfikatu na 2.1.2 | BŁĄD — pusta ramka 00 00 |
| DNSCrypt TCP: ta sama próba na 2.0.9 | BŁĄD — pusta ramka 00 00 |
| Pakiet Debiana dnsdist 1.9.16 | brak funkcji dns-over-quic |
| ACL dnsdist: niezaufany peer 127.0.0.3 | zapytanie odrzucone |
| ACL BIND: niezaufany adres klienta przekazany PROXYv2 | REFUSED, nie dziedziczy uprawnień loopback |
| IP klienta IPv6 w logach RPZ przy backendzie IPv4 | zachowane ::1 zamiast 127.0.0.1 |
| Hook TLS: poprawna para i kontrola konfiguracji | OK |
| Hook TLS: nieprawidłowy klucz | odrzucony, dotychczasowa para zachowana |
| Hook TLS: błąd sterowania usługą po publikacji plików | poprzedni symlink przywrócony |
| DNSCrypt: podpis i zgodność klucza z certyfikatem | OK |
| DNSCrypt: zbliżający się termin ważności | nowy certyfikat; poprzedni ważny nadal w manifeście |
| DNSCrypt: certyfikat wygasły | pominięty w manifeście |
| DNSCrypt: uszkodzony certyfikat | błąd przed podmianą manifestu |
| DNSCrypt: błędna konfiguracja dnsdist | poprzedni manifest przywrócony |
| DNSCrypt: uruchomienie bez zmian | brak podmiany i restartu |

W testach obsługi plików sterowanie systemd było zastąpione wynikiem
„usługa nieaktywna” albo celowo wywołanym błędem. Nie testowano działania
timerów pod PID 1 systemd, automatycznego restartu i reconnect klientów,
AppArmor docelowego hosta, odnowienia Let's Encrypt ani wydajności.
Testy RPZ były deterministyczne, bez pobierania feedów produkcyjnych.
Walidacja DNSSEC była wyłączona w lokalnej strefie testowej; wymaga osobnego
testu przez rzeczywisty resolver. Nie jest to pełny odbiór produkcji.

## Reprodukcja blokady DNSCrypt TCP

Na testowym hoście z włączonym listenerem DNSCrypt:

```sh
python3 scripts/check-dnscrypt-certificate IP_HOSTA \
  2.dnscrypt-cert.NAZWA_HOSTA /etc/dnsdist/dnscrypt/provider.pub
```

Wynik na obu wskazanych pakietach PowerDNS:

```text
OK UDP: 1 waznych certyfikatow
BLAD TCP: ShortHeader: The DNS packet passed to from_wire() is too short.
```

Kod zakończenia: 1. Zwykły `dig ... TXT +tcp` zgłasza `out of range`.
dnscrypt-proxy z `force_tcp = true` zgłasza `Packet too short` i nie
udostępnia działającego resolvera. Nie zastępuj tego testu sprawdzeniem
otwartego portu albo `dnsdist --check-config`: oba były poprawne.

W źródłach gałęzi 2.0 funkcja obsługi TCP w ścieżce `dnsCryptResponse`
tworzy pusty `TCPResponse` i przekazuje go do kolejki. To odpowiada
zaobserwowanej pustej ramce; w repozytorium ISP nie wprowadzano własnej
kompilacji ani poprawki binarnej dnsdist.
[Kod PowerDNS](https://github.com/PowerDNS/pdns/blob/rel/dnsdist-2.0.x/pdns/dnsdistdist/dnsdist-tcp.cc).

Warunek zdjęcia blokady: wydanie z poprawką oraz pozytywny test certyfikatu
i zapytań szyfrowanych DNSCrypt przez UDP/TCP w IPv4/IPv6.
