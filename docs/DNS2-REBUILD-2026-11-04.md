# Nowy cache dns2 — 4 listopada 2026

Wdrożono na czystym Debianie 13.7: `193.192.179.12`,
`2001:67c:660::54/64`, interfejs `ens18`. Bramy:
`193.192.179.1`, `2001:67c:660::1`. dns1 (`193.192.179.11`,
`2001:67c:660::53`) pozostaje na starej instalacji zgodnie z decyzją operatora.

## Wdrożona konfiguracja bazowa

- BIND 9.20.30: cache 1 GiB, DNSSEC, UDP/TCP 53, DoT 853 i DoH 443.
- DoT: `dns2.cybermax.pl`; DoH: `https://dns2.cybermax.pl/dns-query`.
- ACL BIND i nftables: `193.192.179.0/24`, `117.55.198.0/24`,
  `2001:67c:660::/48`, dodatkowo localhost.
- Forward only do `1.1.1.1`, `1.0.0.1`, `8.8.8.8`, `8.8.4.4`.
- nftables zarządza wyłącznie tabelą `inet isp_dns`; nie usuwa tabel Fail2Ban.
  Ogranicza porty DNS, pozostawia SSH i ICMP; Fail2Ban chroni SSH
  oraz odmowy DNS (IPv4 i IPv6).
- Certyfikat Let's Encrypt ważny do 2027-02-02. Włączony `certbot.timer`
  i hook `/etc/letsencrypt/renewal-hooks/deploy/bind-tls`, kopiujący certyfikat
  oraz klucz do `/etc/bind/tls` z uprawnieniami root:bind 0640 i wykonujący
  `named-checkconf` oraz `rndc reconfig`.
- Chrony, narzędzia dig/kdig/tcpdump i `/usr/local/sbin/check-bind-capacity`.
- Resolver systemowy: `127.0.0.1`, `::1`; zaktualizowane `dns-nameservers`
  w `/etc/network/interfaces`.
- Restart zakończony: kernel `6.12.115+deb13.1-amd64`.

DoQ i DNSCrypt nie zostały wdrożone w tym etapie nowego cache.
Historyczne snapshoty `servers/` nie opisują tej nowej instalacji.

Po uruchomieniu nowego dns1 dołączono antyhazard RPZ: dns2 odbiera
`rpz.hazard.mf.gov.pl` z dns1 jako secondary przez TSIG `hazard-rpz-xfr`.
Pierwsza wersja: 59 425 domen, serial 1793819484. Testy przekierowania
przez DNS/DoT/DoH po IPv4/IPv6 przeszły. Szczegóły i kopie konfiguracji:
`DNS1-REBUILD-2026-11-04.md`, rozdział „Antyhazard”.

## IPv6: nierozwiązane ograniczenie poza hostem

Adres, trasa domyślna i NDP bramy działają. Brama odpowiada na ping.
Ping do Cloudflare i Google zwracał ICMPv6 „Administratively prohibited”
z routera `2a01:11f0::e0`; testy DNS UDP/TCP i HTTPS do zewnętrznych
adresów IPv6 kończyły się timeoutem. Host przed wdrożeniem nie miał reguł
nftables. Nie zmieniano adresu ani bramy na podstawie tych błędów.

Resolver używa upstreamów IPv4. W `/etc/gai.conf` dodano tymczasowe
`precedence ::ffff:0:0/96 100`, aby aplikacje systemowe, w tym Certbot,
preferowały IPv4. Po naprawie routingu/ACL IPv6 należy ponowić testy
zewnętrzne i usunąć ten wpis. IPv6 pozostaje włączone dla klientów.

## Weryfikacja i granice odbioru

- Po restarcie: SSH, named, nftables, chrony i fail2ban działają;
  `systemctl --failed` puste; `dpkg --audit` puste.
- UDP/TCP DNS zwracają NOERROR; podpisana domena ma AD;
  `dnssec-failed.org` zwraca SERVFAIL.
- DoT i DoH po IPv4/IPv6 przeszły lokalne testy kdig z walidacją CA
  i nazwy `dns2.cybermax.pl`; HTTP/2 zwraca 200.
- Izolowany klient netns przez veth ze źródłem `2001:67c:660:ffff::2`
  przeszedł UDP/TCP/DoT/DoH: sprawdzono wejście przez firewall spoza loopback.
  Klient `192.0.2.2` spoza ACL został zablokowany na UDP/TCP 53.
  Interfejsy, trasy i namespace testowe zostały usunięte.
- Próby DNS z komputera administratora spoza ACL również zostały zablokowane.
- Nie przeprowadzono jeszcze testów z rzeczywistych klientów wszystkich
  trzech sieci ani przez zewnętrzny tor IPv6. Nie oznacza to pełnego odbioru
  sieci abonenckiej. dns1 należy migrować dopiero po takim odbiorze dns2.

## Kopie i diagnostyka

### Serwer czasu NTP — dodatkowe wdrożenie tego samego dnia

Chrony udostępnia UDP 123 na IPv4 i IPv6 dla tych samych trzech sieci
co DNS. Plik `/etc/chrony/conf.d/isp-server.conf` zawiera dyrektywy `allow`
i `ratelimit interval 3 burst 8 leak 2`. nftables dopuszcza UDP 123
z istniejących zestawów klientów i blokuje pozostałe źródła.
Nie włączono zastępczego, niesynchronizowanego zegara lokalnego.

Po restarcie chrony odzyskał synchronizację: stratum 3, Leap status Normal.
Test pakietów NTP przez adresy serwera IPv4 i IPv6 potwierdził odpowiedzi
server-mode z poprawnym polem originate timestamp. `chronyc accheck`
potwierdził dostęp dla każdej z trzech sieci i odmowę dla adresów
dokumentacyjnych spoza ACL. Kopia sprzed zmiany:
`/root/chrony-server-backup/`. Klienci mogą używać `193.192.179.12`
lub `2001:67c:660::54` jako serwera NTP.

Na dns2: `/root/dns-bootstrap-backup/` zawiera pierwotne pliki sieci,
hosts, resolv.conf, apt, gai.conf i nftables.conf, fabryczną konfigurację
BIND w `bind-factory/` oraz wynik testu w `acl-test.log`.
Skrypty wykonanych etapów są w `/root/bootstrap-dns2-base.sh`,
`/root/dns2-tls.sh`, `/root/dns2-acl-test.sh`.

Nie uruchamiać ponownie skryptów bootstrap bez przeglądu: zapisują pliki
konfiguracyjne i kopie zapasowe. Przy wycofaniu odtwarzać wybrane pliki
z kopii i sprawdzać składnię przed przeładowaniem; nie restartować całej
sieci w sesji SSH. Brak globalnej operacji `flush ruleset` jest celowy.

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

Dodatkowo na dns2 wdrożono **DoQ i DNSCrypt**. dnsdist 2.1.3 z oficjalnego
repozytorium PowerDNS obsługuje QUIC na UDP 853 i zachowuje adres klienta
przez PROXYv2 do BIND 5300. Certbot ma osobny hook atomowej wymiany TLS.
`isp-dnscrypt` 0.9.22 obsługuje UDP/TCP 8443, nowego providera
`dns2.cybermax.pl`, własny stan i monitoring podpisów/certyfikatów co 15 min.
Stampy publiczne są w `journalctl -u isp-dnscrypt`, sekrety wyłącznie na hoście.

Testy: DoQ z dns1 po IPv4/IPv6 i DNSCrypt klientem dnscrypt-proxy
(UDP/TCP × IPv4/IPv6) potwierdziły odpowiedzi, działanie antyhazardu IDN
i odrzucenie błędnego DNSSEC. Po rozszerzeniu ACL ponowiono kontrolę inventory,
konfiguracji i stanu usług. Kopie: `/root/pre-dns-extensions/`,
`/root/doq-install-*`, `/root/dnscrypt-install-*`, `/root/dns-protection-*`.

Firewall główny i tabele frontendów są atomowo odtwarzane przez `destroy table`
wyłącznie dla własnej tabeli. Naprawia to problem nakładania prefiksów przy
zmianie /21 → /20 bez usuwania reguł Fail2Ban. Klient dnscrypt-proxy był
użyty do testów; jego domyślne usługi/socket/resolvconf są wyłączone.
