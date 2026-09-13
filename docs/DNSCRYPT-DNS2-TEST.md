# Test encrypted-dns-server na dns2 — 13 września 2026

**Aktualizacja: po testach usługę udostępniono pełnej ACL klientów dns2.**
Włączono autostart frontendu i firewalla. Początkowe sekcje opisują test;
aktualny zakres przedstawiono na końcu dokumentu.

Uruchomiono osobny `encrypted-dns-server` 0.9.22 amd64 na UDP/TCP 8443,
przed istniejącym BIND-em `127.0.0.1:53`. DNSCrypt w dnsdist pozostaje
wyłączony. DoQ nadal obsługuje dotychczasowy dnsdist. Nie restartowano
BIND-a ani dnsdist; ich PID-y nie zmieniły się podczas wdrożenia.

## Zakres dostępu i procesu

Firewall `inet isp_dnscrypt_test` dopuszcza wyłącznie adresy dns1 w IPv4/IPv6
oraz loopback, odrzucając pozostały UDP/TCP 8443 bez logowania pakietów.
To dostęp do testów między serwerami, nie wdrożenie dla abonentów.
Reguły nie zmieniają portów 53/443/853, SSH ani istniejących jaili Fail2Ban.
DNSCrypt ma dodatkowo limit 100 zapytań/s na adres klienta.

- Usługa: `isp-dnscrypt-test.service`.
- Firewall: `isp-dnscrypt-test-firewall.service`, wymagany przed startem usługi.
- Obie jednostki uruchomiono, lecz nie dodano ich do autostartu po restarcie OS.
- Binarny plik: `/opt/isp-dnscrypt-test/encrypted-dns`.
- Konfiguracja: `/etc/isp-dnscrypt-test.toml`.
- Stan i klucze: `/var/lib/isp-dnscrypt-test/encrypted-dns.state`, katalog 0700,
  plik 0600, osobny użytkownik `isp-dnscrypt-test`.
- Limity systemd: MemoryMax 256M, CPUQuota 100%, TasksMax 64.
- Brak relay Anonymized DNS, przekazywania TLS/QUIC i publicznych upstreamów.
- DNSCrypt v2, PQ wyłączone na potrzeby podstawowego testu zgodności.
- Nie deklarujemy `no_filters` ani `no_logs`.

Archiwum pobrano z oficjalnego wydania 0.9.22; SHA256 porównano z polem
digest zasobu w API GitHub:
`415204cbcfb4c03321e346ad89ee345ec7de2c4f71ffb1b6419b2a2e157b587b`.
Źródło: [wydanie projektu](https://github.com/DNSCrypt/encrypted-dns-server/releases/tag/0.9.22).

## Wyniki

Klient dnscrypt-proxy 2.1.8 uruchamiany tymczasowo na dns1, z wyłączonym
cache, osobno dla każdego adresu i `force_tcp=false/true`.

| Test | Wynik |
|---|---|
| Pobranie i walidacja certyfikatu UDP/TCP, IPv4/IPv6 | OK, klient gotowy |
| Szyfrowane zapytania UDP/TCP, IPv4/IPv6 | NOERROR |
| Poprawny DNSSEC, w tym DNSKEY root | AD |
| dnssec-failed.org | SERVFAIL |
| Hazard: 1xbet.ac / niezdefiniowana subdomena | przekierowanie / NXDOMAIN |
| ThreatFox: wpis wybrany z aktywnego feedu | disabled rpz w logu dla wszystkich 4 wariantów |
| Adres klienta w logu RPZ | 127.0.0.1 — ograniczenie tego frontendu |
| Zewnętrzny klient spoza ACL: UDP/TCP, IPv4/IPv6 | timeout, DROP wzrósł z 0 do 7 |
| Dotychczasowe DoQ IPv4/IPv6, DoT IPv4, DoH IPv6 | NOERROR z walidacją TLS |
| systemctl --failed | brak uszkodzonych jednostek |

Trafienie ThreatFox sprawdzono na pojedynczym wpisie z feedu (nazwa
zaczynająca się od `0x0321...`), z czterema wpisami `disabled rpz` w logu
BIND. Sam wynik NOERROR dla `hitclub.ac` z pierwszej próby nie był dowodem
działania audytu. Nie kopiowano feedu do repozytorium.

## Opóźnienia

Po rozgrzaniu BIND-a: 20 zapytań `example.org A` na wariant, przeplatanych
z bezpośrednim DNS UDP do dns2. Pomiar czasu kdig od klienta na dns1,
z przerwami 50 ms; cache dnscrypt-proxy wyłączony.

| Wariant | Mediana DNSCrypt | Maksimum DNSCrypt | Mediana DNS UDP bezpośrednio |
|---|---:|---:|---:|
| IPv4 UDP | 0,6 ms | 0,7 ms | 0,2 ms |
| IPv4 TCP | 0,7 ms | 0,8 ms | 0,2 ms |
| IPv6 UDP | 0,7 ms | 0,9 ms | 0,2 ms |
| IPv6 TCP | 0,7 ms | 0,9 ms | 0,2 ms |

Różnica obejmuje klienta dnscrypt-proxy, szyfrowanie, transport i frontend,
nie tylko skok po loopback. To próbka przy małym obciążeniu i bliskich
serwerach, nie test przepustowości ani SLA. Odczyt pamięci frontendu po
testach: około 10,5 MiB.

## Ograniczenia przed wdrożeniem dla klientów

Frontend nie przekazuje PROXYv2 do BIND. Polityki RPZ działają, ale BIND
widzi loopback i jego ACL/Fail2Ban nie rozpoznaje pierwotnego adresu klienta.
Dlatego kontrola dostępu musi działać przed frontendem; obecnie jest to
wąska ACL testowa. Nie jest to zamiennik dotychczasowego DoQ z zachowaniem
identyfikacji klienta.

Wbudowany cache ustawiono na 1 wpis, TTL min/max/error 0 i holdon 0.
To ograniczenie cache, nie udokumentowany przełącznik całkowitego wyłączenia:
kod nadal może zachować odpowiedź i wykorzystać ją jako stale przy błędzie
upstreamu. Przed produkcją trzeba rozstrzygnąć wymagania dotyczące audytu,
aktualizacji RPZ i tego zachowania. Nie testowano rotacji certyfikatów,
restartu OS ani dużego obciążenia. Stan kluczy należy zachować między testami.

## Obsługa testu

```sh
journalctl -u isp-dnscrypt-test -f
nft list chain inet isp_dnscrypt_test input
systemctl status isp-dnscrypt-test
```

Publiczne stampy są w journalu startowym. Udostępnienie testu innemu
urządzeniu wymaga wpisania jego rzeczywistego adresu do testowej ACL
w `/etc/nftables.d/isp-dnscrypt-test.nft`, sprawdzenia `nft -c -f` i reloadu
jednostki firewalla. Nie otwieraj portu dla całego Internetu.

Wyłączenie testu na dns2:

```sh
/root/dnscrypt-test-download/stop-test.sh
```

Skrypt zatrzymuje frontend, następnie jego firewall. Zachowuje pliki i
tożsamość provider. Ponowny start: `systemctl start isp-dnscrypt-test`.
Artefakty serwera i konfiguracje źródłowe są w `/root/dnscrypt-test-download/`.
Wyniki oraz konfiguracje klienta są na dns1 w `/root/isp-dnscrypt-test-client/`;
procesy testowych klientów zostały zakończone po próbach.

Zanonimizowane konfiguracje w `experimental/encrypted-dns-server/` są
wyłącznie zapisem tego testu. Nie zawierają kluczy ani publicznych stampów
konkretnego wdrożenia. Nie instaluj ich jako uniwersalnej konfiguracji ISP.

## Udostępnienie klientom — po testach

Na polecenie operatora firewall rozszerzono z pojedynczych adresów dns1 na
pełną aktualną ACL `klienci_sieci` BIND-a, dla UDP/TCP 8443 w IPv4/IPv6.
Obce źródła nadal otrzymują DROP od pierwszego pakietu. Jednostki
`isp-dnscrypt-test` i `isp-dnscrypt-test-firewall` mają teraz autostart.
Nazwy plików, usług i provider zachowano, aby nie zmieniać tożsamości ani stampów.

Na dns2 rozszerzono także cztery jaile DNS: UDP `53,853,8443`,
TCP `53,443,853,8443`. Aktywne reguły zmieniono atomowo bez opróżniania
zestawów; wszystkie dotychczasowe bany zachowano. DNSCrypt nie dostarcza
tym jailom nowego źródła detekcji, ponieważ BIND widzi loopback.

Ponowiono testy pobrania certyfikatu i zaszyfrowanych zapytań UDP/TCP,
IPv4/IPv6, DNSSEC i hazardu. Wszystkie przeszły. Mediany DNSCrypt
0,6–0,8 ms, bezpośredniego DNS UDP 0,2 ms, po 20 próbek na wariant.
Zewnętrzny host spoza ACL: timeout we wszystkich czterech wariantach,
licznik DROP wzrósł z 0 do 6. Procesy BIND, dnsdist i DNSCrypt zachowały PID-y.
Nie ma uszkodzonych jednostek systemd. Autostart zweryfikowano przez
`systemctl is-enabled`, bez restartowania systemu.

Pozostawiono limit 100 zapytań/s na źródłowy adres IP, maksymalnie 128
operacji UDP i 64 połączenia TCP. Klienci za wspólnym NAT współdzielą limit
na adres. Nie przeprowadzono testu obciążenia ISP; ograniczenia cache
oraz braku IP klienta opisane wyżej nadal obowiązują.

Kopie konfiguracji sprzed rozszerzenia ACL i autostartu:
`/root/dnscrypt-clients-20260913T205303Z/`. Przy wycofaniu dostępu klientów
przywróć z tej kopii `isp-dnscrypt-test.nft`, sprawdź `nft -c -f` i wykonaj
reload jednostki firewalla. Aby wyłączyć usługę również po restarcie OS,
użyj `systemctl disable --now isp-dnscrypt-test isp-dnscrypt-test-firewall`.
Kluczy w pliku stanu nie usuwaj. Snapshot aktualnych plików jest w `servers/dns2/`.
