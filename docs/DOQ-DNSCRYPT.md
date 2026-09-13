# DoQ i DNSCrypt dla pary resolverów ISP

**Wariant wdrożony DNSCrypt:** osobny encrypted-dns-server na obu hostach,
opis i instalator w [DNSCRYPT-INSTALL.md](DNSCRYPT-INSTALL.md).
Poniższa blokada i procedury DNSCrypt dotyczą wyłącznie implementacji dnsdist.

Rozszerzenie przygotowane 13 września 2026. Wymaga osobnego odbioru na dns1
i dns2; nie jest częścią historycznego odbioru produkcji z 7 września.

DoQ wdrożono na dns2 i dns1 13 września; zakres odbioru i ograniczenia
opisują [`DOQ-DNS2-DEPLOYMENT.md`](DOQ-DNS2-DEPLOYMENT.md) oraz
[`DOQ-DNS1-DEPLOYMENT.md`](DOQ-DNS1-DEPLOYMENT.md).
Poniższy opis błędu DNSCrypt pozostaje aktualny.

Do instalacji produkcyjnego DoQ użyj [DOQ-INSTALL.md](DOQ-INSTALL.md).
Ta instrukcja opisuje dodatkowo przygotowanie DNSCrypt w laboratorium;
nie wykonuj jego kroków przy wdrażaniu samego DoQ.

**Wynik laboratorium: DoQ przeszedł testy; wdrożenie DNSCrypt jest
zablokowane przez nieudany test TCP.** Oficjalne pakiety PowerDNS
`2.1.2-1pdns.debian13` i `2.0.9-1pdns.debian13` na arm64 zwróciły dwubajtową
ramkę `00 00` zamiast odpowiedzi TXT z certyfikatem po TCP. dnscrypt-proxy
2.1.8 z `force_tcp = true` zgłosił `Packet too short`. UDP działa.
Pakiet Debiana `1.9.16-0+deb13u1` nie ma skompilowanej obsługi DoQ.

Dlatego szablon ma `enableDNSCrypt = false`. DoQ można testować osobno.
Poniższe kroki DNSCrypt są procedurą przygotowania i odbioru laboratoryjnego,
nie zgodą na wdrożenie tych wadliwych pakietów. Włącz DNSCrypt produkcyjnie
dopiero na wydaniu, które przejdzie test certyfikatu **i zaszyfrowanych
zapytań** UDP/TCP. Nie obchodź problemu wyłączeniem TCP w kliencie.
Pełny zakres sprawdzeń i ograniczenia opisuje
[`DOQ-DNSCRYPT-TESTS.md`](DOQ-DNSCRYPT-TESTS.md).

## Architektura i porty

Na KAŻDYM resolverze działa lokalny dnsdist:

```text
DNS/53, DoT/TCP853, DoH/TCP443 ──────────────────> BIND
DoQ/UDP853, DNSCrypt/UDP+TCP8443 -> dnsdist -> PROXYv2/127.0.0.1:5300 -> BIND
```

BIND zachowuje cache, forwardery, walidację DNSSEC, ACL i obie RPZ.
dnsdist nie ma dodatkowego packet cache ani backendu omijającego BIND-a.
PROXYv2 przekazuje oryginalny adres klienta, także IPv6 przez lokalny backend
IPv4. Logi RPZ i ACL BIND-a mają nadal dotyczyć klienta, nie `127.0.0.1`.
Bez PROXYv2 lokalny proxy mógłby obejść ograniczenie rekursji do sieci ISP.

| Usługa | Port publiczny | Proces |
|---|---|---|
| DNS | UDP/TCP 53 | named |
| DoT | TCP 853 | named |
| DoH HTTP/2 | TCP 443 | named |
| DoQ (RFC 9250) | UDP 853 | dnsdist |
| DNSCrypt v2 | UDP i TCP 8443 | dnsdist |
| Backend PROXYv2 | UDP/TCP 5300, tylko 127.0.0.1 | named |
| Diagnostyka dnsdist | UDP/TCP 5301, tylko 127.0.0.1 | dnsdist |

DNSCrypt używa 8443, ponieważ TCP 443 zajmuje już DoH. DoQ nie jest DoH3.
Ten dodatek szyfruje odcinek klient–resolver; dotychczasowy forwarding
BIND-a do upstreamów pozostaje bez zmian.

## 1. Pakiet i kontrola wstępna

Wykonuj kolejno na jednym serwerze. Zapisz kopię konfiguracji BIND, dnsdist
(jeśli istnieje), hooków Certbota i `nft list ruleset`. Ustal prawdziwe adresy,
nazwę certyfikatu i kompletną ACL klientów. Przykłady poniżej dotyczą dns1
z adresami dokumentacyjnymi; dns2 ma własne adresy, nazwę i klucze DNSCrypt.

Wymagany jest BIND 9.20 i dnsdist z funkcjami `dns-over-quic` oraz `dnscrypt`:

```sh
named -v
named-checkconf
ss -lntup
apt-cache policy dnsdist
```

Do testów DoQ używamy stabilnej gałęzi dnsdist 2.1 z repozytorium
PowerDNS dla Debiana 13. Nie zakładaj obsługi DoQ na podstawie samego numeru
wersji pakietu Debiana. Przed instalacją sprawdź aktualne instrukcje
[repozytorium PowerDNS](https://repo.powerdns.com/).

Jeśli dnsdist jeszcze nie jest używany, zablokuj jego automatyczny start
przed instalacją, aby domyślna konfiguracja nie próbowała zająć portu 53:

```sh
systemctl mask dnsdist.service
install -d -m 0755 /etc/apt/keyrings
curl --fail --show-error --silent https://repo.powerdns.com/FD380FBB-pub.asc \
  -o /etc/apt/keyrings/dnsdist-21-pub.asc
chmod 0644 /etc/apt/keyrings/dnsdist-21-pub.asc
cat > /etc/apt/sources.list.d/dnsdist-21.list <<'EOF'
deb [signed-by=/etc/apt/keyrings/dnsdist-21-pub.asc] https://repo.powerdns.com/debian trixie-dnsdist-21 main
EOF
cat > /etc/apt/preferences.d/dnsdist-21 <<'EOF'
Package: dnsdist*
Pin: origin repo.powerdns.com
Pin-Priority: 600
EOF
apt update
apt install dnsdist python3-nacl python3-dnspython
dnsdist --version
getent passwd _dnsdist
getent group _dnsdist
```

W `dnsdist --version` MUSZĄ wystąpić `dns-over-quic` i `dnscrypt`.
Jeśli którykolwiek warunek nie jest spełniony, nie aktywuj szablonu.
Jeśli dnsdist już obsługuje inne usługi, scal konfigurację indywidualnie;
nie maskuj ani nie nadpisuj działającej usługi tym przykładem.

## 2. Dodatkowy listener BIND-a

```sh
install -o root -g bind -m 0644 bind/named.conf.dnsdist-options /etc/bind/
```

Dodaj wewnątrz istniejącego `options {}`:

```conf
include "/etc/bind/named.conf.dnsdist-options";
```

Pozostaw istniejące listenery 53/853/443 i ACL. Jeżeli `allow-proxy` lub
`allow-proxy-on` już istnieją, scal je zamiast deklarować opcję dwukrotnie.

```sh
named-checkconf && systemctl reload named
ss -lntup | grep ':5300'
```

Port 5300 musi nasłuchiwać wyłącznie na `127.0.0.1`. Nie udostępniaj go na
interfejsie publicznym ani przez DNAT. Zwykły `dig -p 5300` bez PROXYv2 nie
jest poprawnym testem tego listenera.

## 3. TLS i tożsamość DNSCrypt

Certyfikat DoQ może pochodzić z tej samej linii Certbota co DoT/DoH.
dnsdist otrzymuje własną kopię; nie dodawaj `_dnsdist` do grupy `bind`.
DNSCrypt ma osobną, stałą tożsamość provider i krótkoterminowe certyfikaty.

```sh
install -o root -g root -m 0750 scripts/deploy-dnsdist-tls /usr/local/sbin/
install -o root -g root -m 0750 scripts/renew-dnscrypt-cert /usr/local/sbin/
install -o root -g root -m 0755 scripts/dnscrypt-stamp /usr/local/bin/
install -o root -g root -m 0755 scripts/check-dnscrypt-certificate /usr/local/bin/
printf '%s\n' dns1.example.net > /etc/dnsdist/tls-hostname
RENEWED_LINEAGE=/etc/letsencrypt/live/dns1.example.net \
  /usr/local/sbin/deploy-dnsdist-tls --init
/usr/local/sbin/renew-dnscrypt-cert --init
```

`tls-hostname` musi odpowiadać nazwie katalogu linii Certbota i nazwie
certyfikatu (bez sufiksu `-0001`; przy wydawaniu użyj właściwego `--cert-name`).
Hook pomija odnowienia innych linii. Sprawdź, że powstało `tls/current`.

Zabezpiecz kopię `/etc/dnsdist/dnscrypt/provider.key` i `provider.pub`.
Utrata lub zmiana klucza provider wymaga wydania klientom nowych stampów.
Klucz provider jest `root:root 0600`; proces dnsdist czyta tylko podpisane
certyfikaty i klucze resolvera `root:_dnsdist 0640`.

## 4. Konfiguracja dnsdist i firewall

```sh
install -o root -g _dnsdist -m 0640 dnsdist/dnsdist.conf.example /etc/dnsdist/dnsdist.conf
editor /etc/dnsdist/dnsdist.conf
dnsdist --check-config -C /etc/dnsdist/dnsdist.conf
```

Wpisz własne IP, nazwę provider oraz **pełną ACL odpowiadającą
`klienci_sieci`**. Nie używaj `0.0.0.0/0` ani `::/0`. Aktualizacje ACL
abonentów trzeba wykonywać w BIND, dnsdist i regułach firewall razem.
Na etapie DoQ zostaw `enableDNSCrypt = false`, nie otwieraj 8443 i nie
włączaj timera DNSCrypt. Na hoście laboratoryjnym ustaw `true`, aby wykonać
testy DNSCrypt opisane poniżej.

Przed startem frontendu zainstaluj firewall i zależność systemd z sekcji 3
[DOQ-INSTALL.md](DOQ-INSTALL.md). Szablon obsługuje DoQ. Przy odbiorze
DNSCrypt w laboratorium rozszerz firewall dla sieci klientów IPv4/IPv6:

- UDP destination port 853 — DoQ;
- UDP oraz TCP destination port 8443 — DNSCrypt;
- odmowę pozostałych źródeł na tych nowych portach.

Nie zastępuj całego rulesetu i nie zmieniaj reguł SSH. Zachowaj działający
ICMP/ICMPv6 i PMTU. Od 13 września 2026 reguły Fail2Ban na obu serwerach
i w snapshotach obejmują UDP `53,853` oraz TCP `53,443,853`, dla obu rodzin.
Port 8443 dodaj do obu list dopiero przy wdrożeniu DNSCrypt.
Po zmianie wykonaj `fail2ban-client -t` i sprawdź aktywne reguły nftables:
sam reload jaila nie przebudowuje dopasowania portów istniejącej akcji nftables.
Odmowy ACL dnsdist nie trafiają do `named/security.log`, zatem podstawą
ograniczenia nowych portów jest firewall i ACL dnsdist, nie te jaile.
Rozszerzenie portów przenosi dotychczasowe bany na DoQ; nie dodaje detekcji
nadużyć QUIC. Sieci w `ignoreip` nadal są wyłączone z automatycznego banowania.

```sh
systemctl unmask dnsdist.service
systemctl enable --now dnsdist
systemctl status dnsdist --no-pager
ss -lntup | grep -E ':(5300|5301|853|8443)\b'
dig @127.0.0.1 -p 5301 localhost. A
```

Ostatnie polecenie sprawdza lokalną ścieżkę dnsdist → PROXYv2 → BIND.
Nie dowodzi jeszcze działania szyfrowania, dostępu klienta ani rekursji.

## 5. Odbiór z urządzenia klienta

DoQ testuj `kdig` skompilowanym z obsługą QUIC, z pakietu `knot-dnsutils`:

```sh
kdig -4 @dns1.example.net +quic +tls-ca +tls-hostname=dns1.example.net example.org A
kdig -6 @dns1.example.net +quic +tls-ca +tls-hostname=dns1.example.net example.org A
```

Wystaw osobne stampy DNSCrypt dla IPv4 i IPv6:

```sh
dnscrypt-stamp 198.51.100.10 2.dnscrypt-cert.dns1.example.net /etc/dnsdist/dnscrypt/provider.pub
dnscrypt-stamp 2001:db8:100:1::2 2.dnscrypt-cert.dns1.example.net /etc/dnsdist/dnscrypt/provider.pub
```

Stamp jest publiczny. Nie deklaruje `no-log` ani `no-filter`: projekt loguje
RPZ i stosuje aktywną politykę hazardową. Nie ustawia także obietnicy DNSSEC;
walidacja pozostaje w BIND i wymaga testu przez pełną ścieżkę.

Przed konfiguracją klienta sprawdź certyfikaty dla obu rodzin adresów:

```sh
check-dnscrypt-certificate 198.51.100.10 2.dnscrypt-cert.dns1.example.net /etc/dnsdist/dnscrypt/provider.pub
check-dnscrypt-certificate 2001:db8:100:1::2 2.dnscrypt-cert.dns1.example.net /etc/dnsdist/dnscrypt/provider.pub
```

Każde polecenie musi zakończyć się kodem 0 i `OK UDP` oraz `OK TCP`.
To test certyfikatów, nie pełnej wymiany zaszyfrowanego DNS.

Na urządzeniu testowym użyj `dnscrypt-proxy` z własnym plikiem TOML:

```toml
server_names = ['isp-test']
listen_addresses = ['127.0.0.1:5302']
ipv4_servers = true
ipv6_servers = true
dnscrypt_servers = true
doh_servers = false
require_dnssec = false
require_nolog = false
require_nofilter = false
cache = false
force_tcp = false

[static.'isp-test']
stamp = 'SDNS_Z_POPRZEDNIEGO_KROKU'
```

Uruchom `dnscrypt-proxy -config ./isp-test.toml`, potem
`dig @127.0.0.1 -p 5302 example.org A`. Powtórz z `force_tcp = true` oraz ze
stampem IPv6. Flagi `require_* = false` wyłączają selekcję resolvera według
deklaracji stamp, nie weryfikację podpisu certyfikatu DNSCrypt.

Dla DoQ i DNSCrypt (UDP/TCP, IPv4/IPv6) sprawdź:

1. Zwykłą domenę, NXDOMAIN i duże odpowiedzi; poprawny oraz błędny DNSSEC.
2. Aktualną domenę hazardową: A → `145.237.235.240`; niezdefiniowaną
   subdomenę → NXDOMAIN. Porównaj również AAAA z istniejącym DNS/53.
3. Domenę z ThreatFox: audyt bez zmiany odpowiedzi; w logu RPZ ma być IP
   urządzenia klienta. Brak trafienia w feedzie nie potwierdza działania audytu.
4. Z niezaufanego hosta: brak dostępnej rekursji/cache na nowych portach.
5. Zepsutą nazwę/zaufanie TLS oraz błędny klucz provider: klient odrzuca usługę.
6. Regresję DNS/53, DoT i DoH oraz zgodność seriali obu RPZ.

Po odbiorze pierwszego resolvera wykonaj te same czynności na drugim. Oba serwery
obsługują klientów samodzielnie; transfer RPZ pozostaje dotychczasowy.

## 6. Odnowienia i eksploatacja

Dla samego DoQ wykonaj sekcję 5 [DOQ-INSTALL.md](DOQ-INSTALL.md).
Poniższe polecenia z timerem DNSCrypt dotyczą wyłącznie środowiska,
w którym DNSCrypt przeszedł pełny odbiór UDP/TCP.

Po odbiorze na każdym hoście:

```sh
install -o root -g root -m 0750 scripts/deploy-dnsdist-tls \
  /etc/letsencrypt/renewal-hooks/deploy/dnsdist-tls
install -o root -g root -m 0644 systemd/dnscrypt-renew.service systemd/dnscrypt-renew.timer /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now dnscrypt-renew.timer
certbot renew --dry-run --run-deploy-hooks
systemctl start dnscrypt-renew.service
systemctl list-timers dnscrypt-renew.timer certbot.timer
journalctl -u dnscrypt-renew.service -u dnsdist --since today
```

Certyfikaty DNSCrypt są ważne 14 dni; codzienny timer odnawia je przy
pozostałych 7 dniach. Wszystkie jeszcze ważne pary są nadal ładowane, więc
klient ze starszym certyfikatem może działać do jego wygaśnięcia. Wygasłe
pliki zostają na dysku dla diagnostyki/rollbacku i nie trafiają do manifestu.
Klucz provider nie podlega tej rotacji. Błąd podpisu/przygotowania przerywa
aktualizację; błąd sprawdzenia konfiguracji przywraca poprzedni manifest.

Odnowienie zmieniające certyfikaty restartuje **tylko dnsdist**, po kontroli
konfiguracji. Przerywa aktywne sesje DoQ/DNSCrypt; klienci muszą połączyć się
ponownie. DNS/53, DoT i DoH obsługiwane przez BIND działają dalej.
Nie zakładaj, że samo `active` potwierdza odnowienie — powtórz zapytanie DoQ
z walidacją TLS i DNSCrypt z klienta. Monitoruj błędy timerów, daty ważności,
czas odpowiedzi oraz obciążenie obu procesów. DoQ zwiększa także liczbę
połączeń TCP do BIND-a; zachowaj diagnostykę `tcp-clients`.

## 7. Wycofanie rozszerzenia

Wycofuj jeden host naraz, po przełączeniu klientów na działający protokół:

```sh
systemctl disable --now dnscrypt-renew.timer
systemctl stop dnscrypt-renew.service
systemctl disable --now dnsdist
```

Wyłącz hook `/etc/letsencrypt/renewal-hooks/deploy/dnsdist-tls`, zachowując
istniejący `bind-tls`. Usuń dodatkowy include backendu z `options`, następnie
`named-checkconf && systemctl reload named`. Wycofaj wyłącznie nowe reguły
firewalla. Zachowaj klucze provider i konfigurację w chronionej kopii.
Sprawdź DNS/53, DoT/DoH i obie RPZ. Nie przywracaj snapshotów `servers/`
w miejsce aktualnej produkcji.

## Dokumentacja źródłowa

- [dnsdist: DoQ](https://www.dnsdist.org/guides/dns-over-quic.html)
- [dnsdist: DNSCrypt i generowanie certyfikatów](https://www.dnsdist.org/reference/dnscrypt.html)
- [dnsdist: przekazanie adresu klienta](https://www.dnsdist.org/advanced/passing-source-address.html)
- [BIND 9.20: listen-on, allow-proxy, allow-proxy-on](https://bind9.readthedocs.io/en/v9.20.1/reference.html)
- [DNSCrypt: format certyfikatu](https://dnscrypt.info/protocol/)
- [DNSCrypt: format stamp](https://dnscrypt.info/stamps-specifications/)
