# DNSCrypt dla klientów na dns1 — 13 września 2026

Uruchomiono encrypted-dns-server 0.9.22 amd64, jako osobny frontend do
BIND `127.0.0.1:53`, na publicznych adresach dns1, UDP/TCP 8443.
DNSCrypt jest teraz udostępniony klientom na obu resolverach.
DoQ pozostaje w dnsdist, a DNS/DoT/DoH w BIND. Nie restartowano BIND ani dnsdist.

## Konfiguracja

- Jednostki `isp-dnscrypt.service` i `isp-dnscrypt-firewall.service`: active/enabled.
- Usługa wymaga uruchomienia firewalla; tabela `inet isp_dnscrypt`.
- ACL IPv4/IPv6 odpowiada pełnej aktualnej `klienci_sieci` w BIND.
- UDP/TCP 8443 spoza ACL: DROP bez logowania pakietów, od pierwszego pakietu.
- Binarka `/opt/isp-dnscrypt/encrypted-dns`, konfiguracja `/etc/isp-dnscrypt.toml`.
- Osobny użytkownik `isp-dnscrypt`, katalog stanu `/var/lib/isp-dnscrypt` 0700.
- Własna tożsamość provider dla dns1; stan 0600, niezależny od kluczy dns2.
- Limit 100 zapytań/s na IP, 128 operacji UDP, 64 połączenia TCP.
- MemoryMax 256M, CPUQuota 100%, TasksMax 64.
- Brak publicznych upstreamów, relay Anonymized DNS i przekazywania QUIC/TLS.
- DNSCrypt v2; PQ wyłączone. Nie deklarujemy braku filtrowania ani logów.
- Fail2Ban: UDP `53,853,8443`, TCP `53,443,853,8443`, obie rodziny.
  Zmieniono aktywne reguły atomowo i zachowano wszystkie bany:
  po 161 w jailach UDP/TCP i po 4 w dedykowanych jailach IPv6.

Użyto tego samego oficjalnego archiwum co na dns2, po weryfikacji SHA256:
`415204cbcfb4c03321e346ad89ee345ec7de2c4f71ffb1b6419b2a2e157b587b`.

## Odbiór

Klient dnscrypt-proxy 2.1.8 na dns2, osobne uruchomienia IPv4/IPv6,
`force_tcp=false/true`, cache klienta wyłączony. Sprawdzono:

- pobranie i walidację certyfikatu UDP/TCP, zaszyfrowane zapytania w obu rodzinach;
- DNSSEC: AD dla poprawnej domeny i DNSKEY root, SERVFAIL dla dnssec-failed.org;
- hazard: przekierowanie 1xbet.ac oraz NXDOMAIN niezdefiniowanej subdomeny;
- audyt ThreatFox: osobne zapytania bez DO dla wpisu z aktywnego feedu,
  potwierdzone przez log `disabled rpz` (sama odpowiedź DNS nie wystarcza);
- odrzucenie zewnętrznego klienta UDP/TCP IPv4/IPv6: timeout i wzrost DROP;
- regresję DNS UDP/TCP, DoT, DoH, DoQ na dns1 w obu rodzinach;
- autostart przez is-enabled i brak uszkodzonych jednostek, bez rebootu OS.

20 próbek na wariant, rozgrzany BIND, zapytania example.org A przeplatane
z bezpośrednim DNS UDP. Mediany: DNSCrypt IPv4 UDP 0,6 ms, TCP 0,75 ms,
IPv6 UDP 0,6 ms, TCP 0,8 ms. Bezpośredni DNS UDP: 0,2 ms.
To pomiar całej ścieżki przez klienta DNSCrypt i frontend, nie samego loopback.
Nie jest to test wydajności przy obciążeniu ISP.

## Ograniczenia

Tak jak na dns2, BIND widzi loopback zamiast rzeczywistego IP klienta.
Nie ma PROXYv2, więc kontrola źródeł odbywa się w firewallu i frontendzie;
rozszerzenie Fail2Ban przenosi istniejące bany na 8443, ale nie dodaje
wykrywania nadużyć DNSCrypt w logach BIND.

Cache frontendu: pojemność 1, TTL min/max/error 0, holdon 0. To ograniczenie,
nie pełne wyłączenie cache: możliwe jest wykorzystanie zachowanej odpowiedzi
przy błędzie upstreamu. Rotacja certyfikatów i obciążenie abonentów nie
zostały objęte testem. Wspólny NAT oznacza współdzielenie limitu 100 zapytań/s.
Pozostałe szczegóły wynikają z [testu dns2](DNSCRYPT-DNS2-TEST.md).

## Obsługa i rollback

```sh
journalctl -u isp-dnscrypt -f
nft list table inet isp_dnscrypt
systemctl status isp-dnscrypt
```

Klucze i konfigurację skopiowano do chronionego archiwum
`/root/dnscrypt-deploy/identity-and-config.tar.gz`. Nie kopiuj go do Git.
Kopia przed rozszerzeniem ACL i banów:
`/root/dnscrypt-clients-20260913T205653Z/`.

Wyłączenie frontendu i jego autostartu/firewalla:

```sh
/root/dnscrypt-deploy/stop.sh
```

Skrypt zachowuje klucze, konfigurację i rozszerzone porty istniejących banów.
Powrót portów Fail2Ban wymaga przywrócenia jego kopii i aktualizacji aktywnych
reguł; nie odtwarzaj całego starego rulesetu nad aktualnymi banami.
Snapshot konfiguracji dns1 znajduje się w `servers/dns1/`, bez sekretów.
