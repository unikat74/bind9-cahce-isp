# Nowy cache dns1 — 4 listopada 2026

Nowa instalacja Debian 13.7 na `193.192.179.11/28`,
`2001:67c:660::53/64`, interfejs `ens18`. Bramy:
`193.192.179.1`, `2001:67c:660::1`.

Wdrożono odpowiednik nowej instalacji dns2:

- BIND 9.20.30, cache 1 GiB, walidacja DNSSEC, UDP/TCP 53.
- DoT `dns1.cybermax.pl:853`, DoH `https://dns1.cybermax.pl/dns-query`.
- Certyfikat Let's Encrypt do 2027-02-02, `certbot.timer` i hook
  `/etc/letsencrypt/renewal-hooks/deploy/bind-tls`; klucze pozostają na hoście.
- Dostęp DNS i NTP wyłącznie dla `193.192.179.0/24`, `117.55.198.0/24`,
  `2001:67c:660::/48`; lokalny dostęp DNS dla loopback.
- nftables: tabela `inet isp_dns`; brak globalnego `flush ruleset`.
  SSH zachowany, Fail2Ban chroni SSH oraz odmowy DNS (IPv4 i IPv6).
- Chrony jako serwer NTP UDP 123, ograniczanie częstotliwości odpowiedzi,
  bez zastępczego niesynchronizowanego zegara lokalnego.
- QEMU Guest Agent i obecny kanał `org.qemu.guest_agent.0`.
- Resolver systemowy `127.0.0.1`, `::1`, narzędzia diagnostyczne
  i `/usr/local/sbin/check-bind-capacity`.

Forwardery IPv4: `1.1.1.1`, `1.0.0.1`, `8.8.8.8`, `8.8.4.4`.
Przed wdrożeniem wyjście do Cloudflare IPv6 zwróciło ICMPv6
„Administratively prohibited” z `2a01:11f0::e0`, tak jak na dns2.
Adres i brama IPv6 pozostały bez zmian. W `gai.conf` ustawiono tymczasową
preferencję IPv4 (`precedence ::ffff:0:0/96 100`). Po naprawie upstreamu
należy ponowić zewnętrzne testy IPv6 i usunąć preferencję.

Nie wdrażano w tym etapie DoQ ani DNSCrypt. Historyczne snapshoty
`servers/dns1/` nie opisują nowej instalacji.

## Antyhazard — dołączony po instalacji bazowej

dns1 jest primary `rpz.hazard.mf.gov.pl`. Aktualizator
`/usr/local/sbin/update-hazard-rpz` pobiera rejestr MF o 06:00 i 18:00 czasu Europe/Warsaw przez
`hazard-rpz.timer` (bez losowego opóźnienia, z nadrabianiem pominiętego
uruchomienia po starcie serwera). Pierwsze pobranie: 59 425 domen, zero odrzuconych,
serial 1793819484. Dokładna nazwa otrzymuje A `145.237.235.240`,
zapytanie AAAA nie otrzymuje adresu, pozostałe subdomeny zwracają NXDOMAIN.
Polityka `given`, `break-dnssec yes`; zwykłe domeny nadal podlegają DNSSEC.

dns2 jest secondary; transfer i NOTIFY używają nowego klucza
`hazard-rpz-xfr` w `/etc/bind/keys/`, wyłącznie na serwerach.
Konfiguracja strefy: `/etc/bind/named.conf.hazard`. Kopie plików sprzed
wdrożenia na obu hostach: `/root/pre-hazard-rpz/`.

Przy pierwszym pobraniu urllib zakończył odczyt timeoutem. Zmieniono
funkcję pobierania generatora na curl z weryfikacją TLS, wyłącznie HTTPS
i limitem czasu. Pobranie, walidacja strefy i ponowne uruchomienie usługi
systemd zakończyły się powodzeniem; drugie pobranie wykazało brak zmian.

Test `0-romancasino.com` z obu serwerów do drugiego potwierdził przekierowanie
przez DNS, DoT i DoH po IPv4/IPv6. Test subdomeny zwrócił NXDOMAIN;
test DO=1 zachował politykę, zwykła podpisana domena zachowała AD,
`dnssec-failed.org` nadal zwróciło SERVFAIL. Transfer AXFR bez klucza
z dns2 został odrzucony, a uwierzytelniona strefa na dns2 ma ten sam serial.

## Weryfikacja

### IDN i znaki diakrytyczne — test antyhazardu

Ponowne pobranie rejestru MF: 59 425 aktywnych domen, zero odrzuconych;
dwie nazwy IDN: `drückglück.de` oraz `www.drückglück.de`, odpowiednio
`xn--drckglck-75ae.de` i `www.xn--drckglck-75ae.de`.
Obie sprawdzono na dns1 i dns2 po IPv4/IPv6: UDP, TCP, DoT i DoH
zwracają A `145.237.235.240`. AAAA daje NOERROR bez adresu,
DO=1 nadal przekierowuje, losowa subdomena daje NXDOMAIN.
Bezpośrednie zapytania Unicode przez `dig +idnin` też przekierowują.

Generator poprawnie normalizuje IDNA2008/UTS46 także `faß.de`, `bücher.de`,
`żółć.pl`, `äöü.de` i `école.fr`. Są to testy konwersji; tych nazw
nie dodawano do rejestru ani do polityki. Dla znaków innych niż ü aktualny
rejestr nie dostarczył aktywnych przykładów IDN. Skrypt odbioru na dns1:
`/root/check-hazard-idn.py`; wszystkie asercje przeszły.

Z dns2 sprawdzono DNS UDP/TCP, DoT i DoH po obu rodzinach adresów;
otrzymano NOERROR i AD. kdig weryfikował CA i nazwę certyfikatu.
Pakiety NTP z dns2 otrzymały poprawne odpowiedzi stratum 3 po IPv4 i IPv6,
z weryfikacją pola originate timestamp. `dnssec-failed.org` zwróciło SERVFAIL.

Po restarcie działa kernel `6.12.115+deb13.1-amd64`. Wszystkie pięć usług
(named, nftables, chrony, fail2ban, qemu-guest-agent) działa, lista failed
i `dpkg --audit` są puste. Ponowiono z dns2 testy UDP/TCP/DoT/DoH oraz NTP
po IPv4 i IPv6; NTP po restarcie odpowiadał ze stratum 2.
Test izolowanego klienta netns potwierdził dostęp IPv6 do wszystkich
czterech wariantów DNS i zablokowanie UDP/TCP 53 ze źródła `192.0.2.2`
spoza ACL. Wynik: `/root/dns-bootstrap-backup/acl-test.log`.
Namespace testowy usunięto. ACL chrony sprawdzono dla każdej z trzech
sieci i adresów IPv4/IPv6 spoza nich.

To odbiór między serwerami; nie zastępuje testów z rzeczywistych klientów
każdej z trzech dozwolonych sieci ani testu zewnętrznego toru IPv6.

## Kopie

`/root/dns-bootstrap-backup/` na dns1: pierwotne network, hosts, resolv.conf,
apt, gai.conf, nftables.conf, fabryczne bind i konfiguracja chrony.
Wykonane skrypty: `/root/bootstrap-dns1-base.sh`, `/root/dns1-tls.sh`.
Nie uruchamiać ich ponownie bez przeglądu — nadpisują konfigurację i kopie.

## Uzupełnienia i ostateczna ACL DNS

Dostęp DNS: `193.192.179.0/24`, `117.55.198.0/24`, **`10.0.0.0/20`**,
`2001:67c:660::/48` oraz localhost. NTP zachował wcześniejsze trzy sieci;
zgoda na DNS nie rozszerzała NTP. Zaktualizowano BIND, firewall i wyjątki
czterech jaili DNS Fail2Ban. Usunięto wcześniejsze bany klientów 10.0/20
z jaili i nftables. Aktywne ignoreip obejmują /20; po zmianie próbka 200
odpowiedzi do realnych klientów nie zawierała REFUSED (zawierała pojedyncze
SERVFAIL/NXDOMAIN, więc nie stanowi dowodu poprawności każdej domeny).

Ochrona: `/var/log/named/security.log` dla Fail2Ban, oddzielny `rpz.log`,
rotacja BIND 20 MiB × 5 archiwów. Jaile UDP/TCP × IPv4/IPv6 przeszły
rzeczywisty test odmowa → ban → reguła nftables → blokada → unban.
Nowy instalator usuwa stare bany nowo zaufanych klientów.

ThreatFox przygotowany jako primary na dns1 i secondary na dns2 przez
osobny TSIG `threatfox-rpz-xfr`. Klucz API ma być tylko na dns1;
nie użyto klucza wzorcowego hosta. Feed i polityka zostały aktywowane po zapisaniu osobnego Auth-Key na dns1.
Potwierdzono transfer TSIG i serial 2611041923 na obu hostach.
Domena z feedu `kg.afktogel.org` zwraca NXDOMAIN przez DNS UDP/TCP, DoT
i DoH po IPv4/IPv6 na obu hostach, a na dns2 także DoQ i DNSCrypt UDP/TCP.
Antyhazard IDN i walidacja DNSSEC nadal działają. Pominięto jeden rekord
feedu przekraczający limit nazwy DNS (256 bajtów); pozostała strefa przeszła
named-checkzone. Instrukcja aktywacji:
[DNS-EXTENSIONS-INSTALL.md](DNS-EXTENSIONS-INSTALL.md).
