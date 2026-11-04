# Uzupełnienie świeżej instalacji: ochrona DNS, DoQ, DNSCrypt, ThreatFox

Wykonuj na jednym serwerze naraz. Punktem startowym jest działający BIND
z DNSSEC, lokalnym resolverem, ACL klientów oraz certyfikatem Let's Encrypt
na DNS/DoT/DoH. Sekrety pozostają na hostach. Snapshoty `servers/` są
historyczne i nie służą do instalacji wprost.

## 1. Ochrona DNS IPv4 i IPv6

Wymagane pakiety: `bind9-utils fail2ban nftables python3`. Po uruchomieniu
bazowego BIND uruchom z katalogu repozytorium (wpisz wszystkie własne sieci):

```sh
python3 installer/bootstrap-dns-protection.py \
  --client-network 193.192.179.0/24 \
  --client-network 117.55.198.0/24 \
  --client-network 10.0.0.0/20 \
  --client-network 2001:67c:660::/48 --install
```

`--output /tmp/dns-protection-rendered` zamiast `--install` generuje pliki
bez zmiany hosta. Instalator zapisuje kopię w `/root/dns-protection-*`,
sprawdza składnię i przeładowuje BIND oraz Fail2Ban. Powtórne uruchomienie
nie dodaje kolejnego include. Istniejący inline `logging {}` wymaga scalenia;
instalator nie usuwa go automatycznie.

Cztery jaile rozdzielają UDP/TCP oraz IPv4/IPv6. Parametry: dwie odmowy
rekurencji w godzinę, ban dwa dni. Zaufane sieci klientów nie są banowane.
Instalator usuwa ich istniejące bany DNS po zmianie `ignoreip`; nie usuwa
banów obcych adresów ani SSH. Sam reload nie usuwa starych banów.

Logi rotuje BIND, po 20 MiB i pięć archiwów:

- `/var/log/named/security.log`: odmowy, czytane przez Fail2Ban;
- `/var/log/named/rpz.log`: zdarzenia RPZ, nie są powodem bana.

Firewall odrzuca obcy ruch przed BIND. Takie pakiety nie trafią do logu BIND
ani Fail2Ban. To dodatkowa ochrona, nie limiter legalnych klientów ani łącza.
Po instalacji sprawdź `fail2ban-client status`, prawdziwe odmowy i wykonanie
ban/unban w obu rodzinach, w tym obecność adresów w `nft -j list ruleset`.
Nie testuj banów na rzeczywistych klientach ani z adresu sesji SSH.

## 2. Wspólne inventory frontendów

```sh
cp installer/dnscrypt.toml.example installer/dnscrypt.toml
editor installer/dnscrypt.toml
```

Przykład nowego dns2 Cybermax (plik ignorowany przez Git):

```toml
instance = "isp-dnscrypt"
provider = "dns2.cybermax.pl"
ipv4 = "193.192.179.12"
ipv6 = "2001:67c:660::54"
clients = ["127.0.0.1/32", "::1/128", "193.192.179.0/24", "117.55.198.0/24", "10.0.0.0/20", "2001:67c:660::/48"]
```

ACL musi być identyczna z literalną ACL `clients` albo `klienci_sieci` w BIND.
Inventory jest wspólne dla nowych instalatorów DoQ i istniejącego DNSCrypt.
Nie zmieniaj tożsamości istniejącego DNSCrypt ani nie usuwaj jego stanu.

## 3. DoQ

Zainstaluj dnsdist z gałęzi 2.1 oficjalnego repozytorium PowerDNS, jak
w [DOQ-DNSCRYPT.md](DOQ-DNSCRYPT.md), sekcja pakietów. Pakiet dnsdist 1.9
z bazowego Debiana 13 nie ma obsługi QUIC. Przed instalacją zamaskuj
`dnsdist`, aby domyślna konfiguracja nie próbowała zająć portu DNS/53.
Wymagane: `python3-cryptography`, `openssl`, `knot-dnsutils` i certyfikat
w `/etc/letsencrypt/live/FQDN/`.

```sh
dnsdist --version  # musi zawierać dns-over-quic
python3 installer/bootstrap-doq.py installer/dnscrypt.toml --output /tmp/doq-rendered
python3 installer/bootstrap-doq.py installer/dnscrypt.toml --install
```

Instalator przeprowadza preflight BIND/ACL/adresów/Fail2Ban, dodaje wyłącznie
lokalny listener PROXYv2 5300, własną tabelę nftables `isp_doq`, dnsdist
z ACL i hook odnowienia certyfikatu. Sprawdza konfigurację przed startem.
Kopie: `/root/doq-install-*`. Nie nadpisuje istniejącego DoQ; aktualizacje
wykonuj według [DOQ-INSTALL.md](DOQ-INSTALL.md), zachowując klucze i konfigurację.
Po niepowodzeniu zachowaj kopię i generację TLS do diagnozy; nie kasuj ich
w celu wymuszenia ponownej instalacji.

## 4. DNSCrypt

```sh
python3 installer/bootstrap-dnscrypt.py installer/dnscrypt.toml --check
python3 installer/bootstrap-dnscrypt.py installer/dnscrypt.toml --install
```

Instalator używa osobnego `encrypted-dns-server` 0.9.22 z przypiętym SHA256,
portu UDP/TCP 8443 i tabeli `isp_dnscrypt`. Monitoring co 15 minut sprawdza
podpisy certyfikatów, stałość providera i zapis stanu. Publiczne stampy:

```sh
journalctl -u isp-dnscrypt --no-pager | grep 'DNS Stamp:'
```

Pełne testy klientem dnscrypt-proxy opisuje [DNSCRYPT-INSTALL.md](DNSCRYPT-INSTALL.md).
Testuj UDP i TCP po IPv4/IPv6, DNSSEC i przekierowanie antyhazardu.
Nie wystarczy sam status usługi ani pobranie certyfikatu.
Pakiet klienta dnscrypt-proxy nie jest wymagany do działania serwera;
jeśli instalujesz go do testów, nie zmieniaj systemowego resolv.conf i wyłącz
jego domyślną usługę/socket/resolvconf po testach.

## 5. ThreatFox: primary dns1, secondary dns2

Tak jak hazard: wyłącznie dns1 pobiera feed. dns2 odbiera strefę
`rpz.threatfox.abuse.ch` przez transfer TSIG i nie ma klucza API ani timera.
Instalator nie zmienia istniejącej strefy hazardowej.

Na dns1:

```sh
python3 installer/bootstrap-threatfox.py primary prepare --peer 193.192.179.12
# Tylko dla nowego pliku; nie nadpisuj istniejącego klucza:
test -e /etc/threatfox.env || install -o root -g root -m 600 /dev/null /etc/threatfox.env
editor /etc/threatfox.env
```

W pliku ustaw `THREATFOX_AUTH_KEY='OSOBNY_KLUCZ'`. Klucz API ma być tylko
na dns1. Nie wklejaj go w polecenia, logi, Git ani do dokumentacji.
`prepare` tworzy nowy TSIG `/etc/bind/keys/threatfox-rpz-xfr.key`, jeśli nie
istnieje; nie regeneruje istniejącej tożsamości. Przenieś ten plik na dns2
przez zweryfikowane połączenia SSH, bez wyświetlania zawartości; ustaw
root:bind 0640. Przygotuj dns2:

```sh
python3 installer/bootstrap-threatfox.py secondary prepare --peer 193.192.179.11
```

Dopiero gdy dns1 ma własny Auth-Key, aktywuj **najpierw primary**, następnie
secondary na drugim serwerze:

```sh
# dns1:
python3 installer/bootstrap-threatfox.py primary activate --peer 193.192.179.12
rndc zonestatus rpz.threatfox.abuse.ch
# dns2:
python3 installer/bootstrap-threatfox.py secondary activate --peer 193.192.179.11
rndc zonestatus rpz.threatfox.abuse.ch
```

`prepare` nie włącza timera ani pustej strefy. Aktywacja primary wymaga
pobrania i `named-checkzone`; aktywacja secondary oczekuje na udany transfer
przed dołączeniem polityki NXDOMAIN. Po błędzie odtwarza pliki konfiguracji.
Sprawdź zgodność seriali, log transferu z TSIG i NXDOMAIN dla aktualnej
pozycji feedu na obu serwerach. `dnssec-failed.org` nadal ma zwracać SERVFAIL,
a zwykła podpisana domena zachowywać AD.

Na nowych hostach wykonano przygotowanie i aktywację z osobnym Auth-Key
wyłącznie na dns1; transfer TSIG i NXDOMAIN na obu hostach potwierdzono. ThreatFox na primary jest pobierany raz dziennie o 05:00 Europe/Warsaw;
antyhazard pozostaje o 06:00 i 18:00. Bez losowego opóźnienia; pominięte uruchomienie jest
nadrabiane po starcie serwera. Dla starszej wspólnej instalacji obu feedów
pozostaje też `bootstrap-rpz.sh` opisany w [INSTALL.md](INSTALL.md).

## 6. Zmiana sieci klientów i odbiór

Przy zmianie ACL aktualizuj BIND, firewall główny, dnsdist, firewall DoQ,
firewall DNSCrypt, inventory i `ignoreip` DNS. NTP ma osobną ACL — zgoda
na DNS nie rozszerza automatycznie dostępu NTP. Cybermax: prywatna sieć DNS
ma maskę **10.0.0.0/20**, nie /21.

Nowe szablony frontendów używają atomowego `destroy table` i odtworzenia
wyłącznie własnej tabeli. Debian 13/nftables 1.1.3 obsługuje tę składnię.
Samo `flush table` nie czyści elementów istniejących zestawów; przy zmianie
/21 na /20 może powodować błąd nakładających się prefiksów. Nie używaj
`flush ruleset`, ponieważ usunąłby reguły innych usług i Fail2Bana.

Przed przeładowaniem: `named-checkconf`, `dnsdist --check-config`,
`nft -c -f PLIK`, `fail2ban-client -t`. Następnie przeładuj odpowiednie
własne tabele, BIND i Fail2Ban oraz zrestartuj sam frontend dnsdist.
Usuń stare bany adresów nowo zaufanych sieci i potwierdź brak ich również
w nftables. Nie usuwaj banów spoza nowej ACL.

Odbiór z dozwolonego klienta obejmuje DNS UDP/TCP, DoT, DoH, DoQ i DNSCrypt,
obie rodziny adresów, AD dla poprawnej domeny, SERVFAIL dla dnssec-failed.org,
przekierowanie IDN z rejestru MF i brak dostępu spoza ACL.
