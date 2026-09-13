# DNSCrypt: instalacja, aktualizacja i obsługa

DNSCrypt działa na dns1 i dns2 jako osobny `encrypted-dns-server` 0.9.22,
UDP/TCP 8443 w IPv4/IPv6, z lokalnym BIND-em jako jedynym upstreamem.
DoQ obsługuje nadal dnsdist. Ten dokument dotyczy działającego wariantu;
DNSCrypt w dnsdist pozostaje wyłączony z powodu błędu certyfikatu TCP.

## Pliki i układ

| Element | dns1 | Istniejący dns2 |
|---|---|---|
| Instancja systemd/użytkownik | `isp-dnscrypt` | `isp-dnscrypt-test` |
| Firewall systemd | `isp-dnscrypt-firewall` | `isp-dnscrypt-test-firewall` |
| Konfiguracja | `/etc/isp-dnscrypt.toml` | `/etc/isp-dnscrypt-test.toml` |
| Tabela nftables | `inet isp_dnscrypt` | `inet isp_dnscrypt_test` |
| Katalog stanu | `/var/lib/isp-dnscrypt` | `/var/lib/isp-dnscrypt-test` |
| Binarka | `/opt/isp-dnscrypt/encrypted-dns` | `/opt/isp-dnscrypt-test/encrypted-dns` |

Nazwa `test` na dns2 jest historyczna: usługa ma obecnie pełną ACL klientów
oraz autostart. Nie zmieniaj nazwy providera ani nie generuj nowego pliku
stanu przy porządkowaniu nazewnictwa. Zmiana tożsamości wymaga nowych stampów.

Źródła do instalacji:

- `installer/bootstrap-dnscrypt.py` — przygotowanie plików, kontrola hosta,
  instalacja na nowym hoście;
- `installer/dnscrypt.toml.example` — osobne inventory DNSCrypt dla każdego hosta;
- `encrypted-dns/encrypted-dns.toml.in` — szablon frontendu;
- `systemd/isp-dnscrypt*.service.in` — szablony jednostek;
- `installer/bootstrap-rpz.sh` — dotychczasowy, niezależny instalator RPZ.

Instalator RPZ wskazuje teraz kolejny etap DNSCrypt, ale sam go nie uruchamia.
Nie wdrażaj bezpośrednio zanonimizowanych snapshotów `servers/`.

## 1. Przygotowanie hosta

Wymagany jest Debian 13 amd64, działający BIND i cztery jaile DNS Fail2Ban
z [INSTALL.md](INSTALL.md). Dla nowego systemu zacznij od
[FRESH-DEBIAN-13.md](FRESH-DEBIAN-13.md). Używaj klonu repozytorium; polecenia
wykonuj w jego katalogu głównym, po jednym resolverze naraz.

```sh
apt install python3 bind9-utils dnsutils knot-dnsutils nftables fail2ban ca-certificates
cp installer/dnscrypt.toml.example installer/dnscrypt.toml
editor installer/dnscrypt.toml
DNSCRYPT_INSTANCE=isp-dnscrypt
```

Na istniejącym dns2 ustaw zamiast tego `DNSCRYPT_INSTANCE=isp-dnscrypt-test`.
Ta zmienna służy późniejszym poleceniom obsługi; instalator czyta nazwę z inventory.

Wpisz własne publiczne adresy IPv4/IPv6, provider i **pełną literalną ACL**
`klienci_sieci` z `/etc/bind/named.conf.options`. Adresy dokumentacyjne trzeba
zastąpić. `clients` zawiera także wykorzystywane sieci prywatne i loopback.
Nie używaj `0.0.0.0/0` ani `::/0`.

Nowa instalacja może używać `instance = "isp-dnscrypt"` na każdym hoście,
bo systemy są niezależne. Dla już działającego dns2 użyj jego aktualnych
wartości `instance` i `provider` odczytanych z konfiguracji. Inventory jest
ignorowane przez Git; nie umieszczaj w nim kluczy.

## 2. Przygotowanie i kontrola bez instalacji

Generowanie plików można wykonać także na komputerze administratora,
bez roota, na Pythonie 3.11 lub nowszym:

```sh
python3 installer/bootstrap-dnscrypt.py installer/dnscrypt.toml --output /tmp/dnscrypt-generated
```

Katalog wyjściowy nie może wcześniej istnieć. Zawiera drzewo `etc/` z pięcioma
plikami: konfiguracją, firewallem, dwiema jednostkami i portami Fail2Ban.
Przejrzyj je przed instalacją. Tryb `--output` nie pobiera programu,
nie modyfikuje usług ani kluczy.

Kontrola na docelowym serwerze jako root:

```sh
python3 installer/bootstrap-dnscrypt.py installer/dnscrypt.toml --check
```

Sprawdza platformę, składnię BIND, zgodność ACL i własność adresów IP,
odpowiedź lokalnego BIND, jaile Fail2Ban oraz składnię nftables przez `nft -c`.
Jeśli instancja już istnieje, odrzuca zmianę jej nazwy lub providera.
Nie instaluje ani nie restartuje usług. Literalne ACL są porównywane po
normalizacji adresów; zagnieżdżone ACL i nazwy symboliczne wymagają
indywidualnego przygotowania konfiguracji.

## 3. Nowa instalacja

Po udanej kontroli:

```sh
python3 installer/bootstrap-dnscrypt.py installer/dnscrypt.toml --install
```

Instalator:

1. Powtarza kontrolę hosta i odmawia nadpisania istniejącej instalacji,
   stanu, tabeli firewalla lub zajętego portu 8443.
2. Pobiera oficjalne archiwum 0.9.22 z GitHub i sprawdza przypięty SHA256.
   Wydobywa tylko plik wykonywalny, bez wykonywania skryptów pakietowych.
3. Zakłada użytkownika systemowego, instaluje konfigurację i jednostki.
4. Uruchamia firewall przed frontendem. Nowy provider i jego klucze
   powstają lokalnie przy pierwszym starcie.
5. Dodaje nadpisanie portów istniejących jaili: UDP `53,853,8443`,
   TCP `53,443,853,8443`. Restartuje tylko cztery jaile DNS, bez `--unban`,
   i porównuje listy banów. SSH pozostaje bez zmian.
6. Włącza autostart usługi i jej firewalla.

Restart jaila może krótko przerwać działanie jego reguł. Niezależna ACL
DNSCrypt przez cały czas blokuje obce źródła. Jeśli ban wygaśnie w trakcie
kontroli, porównanie może przerwać instalację — zbadaj zapisane listy i log.

Po błędzie podczas instalowania plików/startu usług skrypt próbuje zatrzymać
frontend i jego firewall, usuwa własne nowe pliki konfiguracyjne i odtwarza
parametry jaili przez reload. Nie usuwa powstałych kluczy ani użytkownika/binarki.
Dane diagnostyczne pozostają w `/root/dnscrypt-install-*/`. Nie uruchamiaj
instalatora ponownie przez usuwanie stanu; najpierw wyjaśnij przyczynę.

Instalator nie zmienia BIND-a, dnsdist, RPZ ani konfiguracji SSH. Po jego
zakończeniu **wykonaj testy funkcjonalne z punktu 5** — sam start usługi
nie jest pełnym odbiorem wdrożenia.

## 4. Aktualizacja istniejącego dns1/dns2

`--install` celowo nie nadpisuje działającej konfiguracji. Do jej aktualizacji
użyj generowania, porównania i kontrolowanej podmiany. Dla zmian samych ACL
pomiń podmianę konfiguracji frontendu i jego restart, jeśli pozostaje identyczna.

Najpierw ustaw instancję zgodnie z tabelą (na dns2 `isp-dnscrypt-test`):

```sh
DNSCRYPT_INSTANCE=isp-dnscrypt
DNSCRYPT_BACKUP=$(mktemp -d /root/dnscrypt-update-XXXXXXXX)
chmod 0700 "$DNSCRYPT_BACKUP"
cp -a "/etc/$DNSCRYPT_INSTANCE.toml" "$DNSCRYPT_BACKUP/"
cp -a "/etc/nftables.d/$DNSCRYPT_INSTANCE.nft" "$DNSCRYPT_BACKUP/"
cp -a "/var/lib/$DNSCRYPT_INSTANCE" "$DNSCRYPT_BACKUP/state"
cp -a "/etc/systemd/system/$DNSCRYPT_INSTANCE.service" "$DNSCRYPT_BACKUP/"
cp -a "/etc/systemd/system/$DNSCRYPT_INSTANCE-firewall.service" "$DNSCRYPT_BACKUP/"
cp -a /etc/fail2ban "$DNSCRYPT_BACKUP/"
cp -a "/opt/$DNSCRYPT_INSTANCE/encrypted-dns" "$DNSCRYPT_BACKUP/encrypted-dns"
nft -a list ruleset > "$DNSCRYPT_BACKUP/nft-before.txt"
```

Kopia zawiera sekrety: zostaje na hoście, poza Git. Kopię stanu wykonuj poza
trwającą rotacją certyfikatów i zachowuj dotychczasowy plik na właściwej ścieżce.

```sh
python3 installer/bootstrap-dnscrypt.py installer/dnscrypt.toml --check
DNSCRYPT_WORK=$(mktemp -d /tmp/dnscrypt-update-XXXXXXXX)
python3 installer/bootstrap-dnscrypt.py installer/dnscrypt.toml --output "$DNSCRYPT_WORK/generated"
diff -u "/etc/$DNSCRYPT_INSTANCE.toml" "$DNSCRYPT_WORK/generated/etc/$DNSCRYPT_INSTANCE.toml"
diff -u "/etc/nftables.d/$DNSCRYPT_INSTANCE.nft" "$DNSCRYPT_WORK/generated/etc/nftables.d/$DNSCRYPT_INSTANCE.nft"
```

`diff` zwraca 1, gdy są różnice. Przejrzyj je; upewnij się, że provider,
`state_file`, adresy i potrzebne lokalne ustawienia zostają zachowane.
Generator odtwarza bazowe limity wdrożenia, więc nie nadpisuj nim bez przeglądu
późniejszych zmian wydajnościowych.

Podmiana sprawdzonego firewalla (zmienia wyłącznie własną tabelę):

```sh
nft -c -f "$DNSCRYPT_WORK/generated/etc/nftables.d/$DNSCRYPT_INSTANCE.nft"
install -m 0644 "$DNSCRYPT_WORK/generated/etc/nftables.d/$DNSCRYPT_INSTANCE.nft" "/etc/nftables.d/$DNSCRYPT_INSTANCE.nft"
systemctl reload "$DNSCRYPT_INSTANCE-firewall"
```

Jeśli zmieniasz konfigurację samego frontendu, podmień przejrzany plik,
zrestartuj tylko `$DNSCRYPT_INSTANCE` i natychmiast wykonaj testy klientów.
Przy błędzie przywróć konfigurację/binarkę z kopii i ponownie uruchom usługę;
nie odtwarzaj starszego stanu kluczy, jeśli nie ma takiej konieczności.
Dla zmian jednostek wykonaj `systemd-analyze verify`, potem `daemon-reload`.
Nie restartuj firewalla do aktualizacji reguł: jego zatrzymanie zatrzyma frontend.

Na obecnych dns1 i dns2 port 8443 jest już uwzględniony w Fail2Ban.
Na innym istniejącym wdrożeniu plik wygenerowany
`etc/fail2ban/jail.d/zz-dnscrypt-ports.local` należy scalić z lokalnymi portami,
sprawdzić `fail2ban-client -t`, zapisać bany i przeładować z restartem wyłącznie
odpowiednie jaile DNS. Zwykły reload nie gwarantuje aktualizacji aktywnych
reguł nftables. Nie zmieniaj filtrów, `ignoreip` ani parametrów banów.

Aktualizacja wersji programu jest osobnym etapem: instalator jest celowo
przypięty do przetestowanego 0.9.22 i jego SHA256. Nowe wydanie wymaga
weryfikacji źródła, sumy i testów UDP/TCP, a następnie aktualizacji stałych
`VERSION`/`DIGEST` oraz raportu odbioru. Nie pobiera automatycznie `latest`.

## 5. Klienci i odbiór

Stampy są publiczne i pojawiają się w journalu przy starcie:

```sh
journalctl -u "$DNSCRYPT_INSTANCE" --no-pager | grep 'DNS Stamp:'
```

Wybierz stamp publicznego IPv4 i IPv6, nie loopback. Przykład klienta
`dnscrypt-proxy`, uruchamianego na urządzeniu w dozwolonej sieci:

```toml
server_names = ['isp-ipv4', 'isp-ipv6']
listen_addresses = ['127.0.0.1:15353']
ipv4_servers = true
ipv6_servers = true
dnscrypt_servers = true
doh_servers = false
require_dnssec = true
require_nolog = false
require_nofilter = false
force_tcp = false
cache = false

[static.'isp-ipv4']
stamp = 'STAMP_PUBLICZNEGO_IPV4'
[static.'isp-ipv6']
stamp = 'STAMP_PUBLICZNEGO_IPV6'
```

```sh
dnscrypt-proxy -config ./dnscrypt-proxy.toml
# W drugim terminalu:
dig @127.0.0.1 -p 15353 example.org A +dnssec
dig @127.0.0.1 -p 15353 dnssec-failed.org A +dnssec
dig @127.0.0.1 -p 15353 . DNSKEY +dnssec
```

Weryfikuj kolejno jedną pozycję `server_names` dla IPv4, potem IPv6;
powtórz z `force_tcp=true`. Pozostawienie obu serwerów w jednym teście może
ukryć awarię jednego z nich. Wymagane: poprawne pobranie certyfikatu i
zapytania, AD dla poprawnego DNSSEC, SERVFAIL dla błędnego DNSSEC.

Sprawdź aktualną domenę hazardową, jej niezdefiniowaną subdomenę i wpis
ThreatFox z aktywnego feedu. Potwierdź odpowiednie logi RPZ, także
`disabled rpz`; sam NOERROR/NXDOMAIN nie jest dowodem trafienia w RPZ.
Następnie sprawdź dotychczasowe DNS UDP/TCP, DoT/DoH i DoQ w obu rodzinach.

Z adresu **spoza ACL** sprawdź UDP/TCP 8443, IPv4/IPv6: timeout i wzrost
licznika DROP w `nft list table inet isp_dnscrypt` (na dns2: `isp_dnscrypt_test`).
Samo milczenie serwera nie wystarcza jako dowód. Zapisz czasy odpowiedzi,
stan systemd i listy banów przed/po. Nie porównuj pojedynczego zimnego
zapytania z rozgrzanym cache innego protokołu jako pomiaru narzutu.

## 6. Logi, klucze i ograniczenia

```sh
journalctl -u "$DNSCRYPT_INSTANCE" -f
tail -f /var/log/named/security.log
systemctl is-active "$DNSCRYPT_INSTANCE" "$DNSCRYPT_INSTANCE-firewall"
systemctl is-enabled "$DNSCRYPT_INSTANCE" "$DNSCRYPT_INSTANCE-firewall"
nft list ruleset
```

Plik `encrypted-dns.state` zawiera prywatną tożsamość i klucze; katalog ma
0700, plik 0600. Program sam generuje i rotuje certyfikaty DNSCrypt.
Nie używa Let's Encrypt i nie potrzebuje naszego starego timera
`dnscrypt-renew.timer` przeznaczonego dla dnsdist. Nie uruchamiaj tego timera
w tym wariancie. Utrata stanu oznacza zmianę stampów dla klientów.

BIND widzi `127.0.0.1`, ponieważ ten frontend nie wysyła PROXYv2. Nie ma
pełnego audytu per klient w BIND. ACL jest egzekwowana przez nftables;
`[access_control]` z tokenami jest wyłączone. Limit frontendu to 100 zapytań/s
na źródłowy IP, także wspólny dla klientów za NAT; ustawienie wymaga
monitorowania przy ruchu abonentów. Maksima: 128 operacji UDP i 64 połączenia TCP.

Cache frontendu ograniczono do jednego wpisu z TTL 0, ale nie jest całkowicie
wyłączony: możliwe jest podanie zachowanej odpowiedzi przy błędzie upstreamu.
Oba RPZ pozostają w BIND. Nie deklarujemy braku filtrowania/logów.
Hostowy DROP chroni proces przed obcymi źródłami, ale nie usuwa kosztu
odbioru pakietów ani zajęcia łącza — to wymaga filtrowania na routerze.

## 7. Wycofanie

```sh
systemctl disable --now "$DNSCRYPT_INSTANCE"
systemctl disable --now "$DNSCRYPT_INSTANCE-firewall"
```

Pozostaw klucze w chronionym katalogu. Nie usuwaj całego rulesetu.
Wycofanie samych portów Fail2Ban jest opcjonalne i wymaga kontroli aktywnych
reguł po przeładowaniu jaili; nie usuwaj banów SSH. DNS/DoT/DoH/DoQ nie
wymagają wycofywania, ponieważ nie były zastępowane przez ten frontend.

## Walidacja dostarczonego instalatora

Wykonano testy walidatora i ochrony istniejącej instalacji, wygenerowano
konfigurację oraz uruchomiono tryb `--check` na działających dns1 i dns2.
Kontrola obejmuje rzeczywiste ACL, BIND, Fail2Ban i parser nftables na Debianie 13.
Pełnego nowego `--install` nie uruchamiano ponownie na produkcji ani na
świeżym hoście; dotychczasowe wdrożenia wykonano wcześniej etapami.

```sh
python3 -m unittest discover -s installer/tests -v
```

Raporty: [dns1](DNSCRYPT-DNS1-DEPLOYMENT.md), [dns2](DNSCRYPT-DNS2-TEST.md).
