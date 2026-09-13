# Instalacja DoQ i ochrona UDP 853

Procedura odtwarza zakres wdrożony na dns1 i dns2 13 września 2026.
Wykonuj ją kolejno na każdym serwerze, z katalogu głównego repozytorium,
jako root. To rozszerzenie działającego BIND-a, nie instalator całego systemu.
Dla czystego hosta zacznij od [FRESH-DEBIAN-13.md](FRESH-DEBIAN-13.md).
`installer/bootstrap-rpz.sh` instaluje RPZ; nie instaluje tego rozszerzenia.

## Co zmieniono

- dnsdist obsługuje DoQ na UDP 853 w IPv4 i IPv6.
- Lokalny backend BIND `127.0.0.1:5300` przyjmuje PROXYv2 z adresem klienta.
  Cache, DNSSEC i obie RPZ pozostają w BIND. DNS/53, DoT i DoH obsługuje BIND.
- Osobna tabela nftables odrzuca pierwszy pakiet DoQ spoza ACL klientów,
  bez odpowiedzi i bez logowania pakietów; ruch nie trafia do dnsdist/BIND.
- Fail2Ban obejmuje UDP `53,853` i TCP `53,443,853` dla obu rodzin.
  Wykrywa nadal odmowy BIND, nie nadużycia QUIC. `ignoreip` pozostaje w mocy.
- Hook Certbota aktualizuje osobną kopię certyfikatu dnsdist i restartuje
  frontend po kontroli konfiguracji. Zachowuje dotychczasowy hook BIND.
- DNSCrypt pozostaje wyłączony; port 8443 i timer DNSCrypt nie są uruchamiane.
  Przyczynę i testy laboratoryjne opisuje [DOQ-DNSCRYPT-TESTS.md](DOQ-DNSCRYPT-TESTS.md).

DROP działa w INPUT, przed procesami, ale po odebraniu pakietu przez hosta.
Nie eliminuje kosztu odbioru ruchu ani zajęcia łącza. Ochrona przed takim
obciążeniem wymaga ACL na routerze przed serwerami. Nie dołączono komend
routera bez ustalenia platformy, interfejsów i kierunku ruchu.
Pozostałe porty DNS nie otrzymują tutaj nowej blokady źródeł w firewallu.

## 1. Dane, kopia i wymagania

Ustal adresy IPv4/IPv6 konkretnego hosta, jego FQDN, linię Certbota oraz
pełną ACL `klienci_sieci`, łącznie z używanymi sieciami prywatnymi.
W każdym szablonie zastąp adresy dokumentacyjne własnymi. ACL w BIND,
dnsdist i nftables musi być zgodna. Snapshotów `servers/` nie wdrażaj wprost.

Zapisz w chronionym katalogu kopie zmienianych plików i wyniki:

```sh
umask 077
DOQ_BACKUP=$(mktemp -d /root/doq-before-XXXXXXXX)
cp -a /etc/bind "$DOQ_BACKUP/"
cp -a /etc/fail2ban "$DOQ_BACKUP/"
cp -a /etc/letsencrypt/renewal-hooks "$DOQ_BACKUP/"
nft -a list ruleset > "$DOQ_BACKUP/nft-before.txt"
fail2ban-client status --all > "$DOQ_BACKUP/fail2ban-before.txt"
systemctl cat dnsdist.service > "$DOQ_BACKUP/dnsdist-unit-before.txt" 2>&1 || true
```

Jeśli dnsdist lub tabela `isp_doq` już istnieją, zachowaj także ich konfigurację,
drop-iny i stan usług; scal zmiany z istniejącym wdrożeniem. Nie nadpisuj
działającego frontendu innymi listenerami. Kopie zawierające klucze pozostają
na serwerze i nigdy nie trafiają do Git.

Zainstaluj pakiet dnsdist i dodaj backend BIND według sekcji 1–2
[DOQ-DNSCRYPT.md](DOQ-DNSCRYPT.md). Wdrożenie sprawdzono na Debianie 13,
BIND 9.20.26 i dnsdist 2.1.2. Sprawdź obecność `dns-over-quic` w
`dnsdist --version`. Przed pierwszą instalacją pakietu pozostaw dnsdist
zamaskowany zgodnie z tą instrukcją, aż firewall i konfiguracja będą gotowe.

```sh
apt install nftables knot-dnsutils
named-checkconf
```

## 2. Certyfikat i frontend

Wymagany jest już działający, zaufany certyfikat dla nazwy tego serwera.
Przykład dotyczy dns1; na dns2 użyj jego nazwy i jego adresów.

```sh
install -d -o root -g _dnsdist -m 0750 /etc/dnsdist
install -o root -g root -m 0750 scripts/deploy-dnsdist-tls /usr/local/sbin/
printf '%s\n' dns1.example.net > /etc/dnsdist/tls-hostname
RENEWED_LINEAGE=/etc/letsencrypt/live/dns1.example.net \
  /usr/local/sbin/deploy-dnsdist-tls --init
install -o root -g _dnsdist -m 0640 dnsdist/dnsdist.conf.example /etc/dnsdist/dnsdist.conf
editor /etc/dnsdist/dnsdist.conf
dnsdist --check-config -C /etc/dnsdist/dnsdist.conf
```

W konfiguracji zmień publiczne adresy listenerów oraz pełną ACL.
Pozostaw `enableDNSCrypt = false`. Nie generuj kluczy DNSCrypt ani nie
instaluj jego timera w ramach tej procedury. `tls-hostname` odpowiada nazwie
linii Certbota i nazwie certyfikatu; szczegóły hooka opisuje dokument rozszerzenia.

## 3. Firewall przed uruchomieniem DoQ

```sh
install -d -m 0755 /etc/nftables.d /etc/systemd/system/dnsdist.service.d
install -o root -g root -m 0644 nftables/isp-doq.nft.example /etc/nftables.d/isp-doq.nft
editor /etc/nftables.d/isp-doq.nft
nft -c -f /etc/nftables.d/isp-doq.nft
install -o root -g root -m 0644 systemd/isp-doq-firewall.service /etc/systemd/system/
install -o root -g root -m 0644 systemd/dnsdist.service.d/isp-doq.conf /etc/systemd/system/dnsdist.service.d/
systemctl daemon-reload
systemctl enable --now isp-doq-firewall.service
nft list table inet isp_doq
systemctl unmask dnsdist.service
systemctl enable --now dnsdist.service
```

Nie kontynuuj po błędzie żadnego kroku. Wypełnij oba zestawy klientów
przed uruchomieniem. Plik dotyka tylko tabeli `inet isp_doq`; nie wykonuje
`flush ruleset`, nie zmienia SSH, ICMP ani reguł Fail2Ban.
DoQ spoza ACL jest odrzucane bez czekania na wpis w logu czy bana.
Dozwolony ruch nadal podlega pozostałym łańcuchom firewalla.

Zależność `Requires` zapewnia start frontendu dopiero po udanym starcie
jednostki firewalla. Nie monitoruje jednak ręcznego usunięcia tabeli nftables.
Nie dodawaj drugiego zarządcy tej samej tabeli ani późnego `flush ruleset`.
Przy zmianie ACL sprawdź plik przez `nft -c -f`, a następnie użyj
`systemctl reload isp-doq-firewall` — atomowo wymienia to wyłącznie tę tabelę.
Uzgodnij zmianę z ACL BIND i dnsdist. Nie restartuj firewalla do zwykłej
aktualizacji: jego zatrzymanie przez zależność zatrzyma również dnsdist.

## 4. Fail2Ban

Wymagane są cztery istniejące jaile `named-cache-denied-{udp,tcp,udp6,tcp6}`
opisane w [INSTALL.md](INSTALL.md). Poniższy plik zmienia wyłącznie porty:

```sh
install -o root -g root -m 0644 fail2ban/zz-doq-ports.local.example \
  /etc/fail2ban/jail.d/zz-doq-ports.local
fail2ban-client -t
```

Na nowej instalacji uruchom Fail2Ban po skonfigurowaniu wszystkich jaili.
Przy działającym Fail2Ban zapisz listy banów z czasami i przeładuj z restartem
tylko dwa zmieniane jaile UDP, bez opcji `--unban`:

```sh
fail2ban-client get named-cache-denied-udp banip --with-time
fail2ban-client get named-cache-denied-udp6 banip --with-time
fail2ban-client reload --restart named-cache-denied-udp
fail2ban-client reload --restart named-cache-denied-udp6
fail2ban-client get named-cache-denied-udp banip --with-time
fail2ban-client get named-cache-denied-udp6 banip --with-time
nft list chain inet f2b-table f2b-chain
```

Restart jaila przebudowuje reguły i może krótko przerwać egzekwowanie jego
banów. Stała ACL DoQ przez cały czas odrzuca obce źródła. Porównaj bany
przed/po i sprawdź błędy Fail2Ban. Jeśli porty TCP były inne niż w przykładzie,
analogicznie przeładuj z restartem oba jaile TCP po zapisaniu ich banów.
Sam zwykły reload może zmienić parametry akcji bez aktualizacji aktywnych
dopasowań portów nftables. Na produkcji 13 września użyto zwykłego reloadu
i atomowej zamiany istniejących reguł po uchwytach, zachowując zestawy banów;
uchwyty są lokalne dla danego rulesetu i nie są przenośną konfiguracją.

Akcje tworzą reguły na żądanie, więc jail bez banów może jeszcze nie mieć
reguły. Sprawdź również aktywną wartość `port` przez
`fail2ban-client get JAIL action AKCJA port` (nazwę akcji pokaże `get JAIL actions`).

## 5. Odbiór i odnowienia

Z dozwolonej sieci wykonaj dla każdego serwera:

```sh
kdig -4 @dns1.example.net +quic +tls-ca +tls-hostname=dns1.example.net +timeout=3 +retry=0 example.org A
kdig -6 @dns1.example.net +quic +tls-ca +tls-hostname=dns1.example.net +timeout=3 +retry=0 example.org A
```

Sprawdź DNSSEC, obie RPZ, oryginalny adres klienta w logu RPZ oraz regresję
DNS UDP/TCP, DoT i DoH w IPv4/IPv6 według sekcji 5 dokumentu rozszerzenia.
Z hosta spoza ACL powtórz DoQ dla obu rodzin: połączenie nie powinno się
zestawić, a licznik DROP w `nft list chain inet isp_doq input` musi wzrosnąć.
Sam timeout bez wzrostu licznika nie dowodzi działania tego firewalla.
Sprawdź także sześć jaili i aktywne reguły UDP `53,853` w obu rodzinach.

Po odbiorze zainstaluj hook TLS i przetestuj odnowienie:

```sh
install -o root -g root -m 0750 scripts/deploy-dnsdist-tls \
  /etc/letsencrypt/renewal-hooks/deploy/dnsdist-tls
certbot renew --cert-name dns1.example.net --dry-run --run-deploy-hooks --no-random-sleep-on-renew
systemctl is-active named dnsdist isp-doq-firewall fail2ban
systemctl is-enabled dnsdist isp-doq-firewall
systemctl --failed
```

Ponownie sprawdź DoQ z walidacją TLS oraz DNS/DoT/DoH. Hook restartuje
dnsdist, co przerywa bieżące sesje DoQ. Wyniki wdrożenia opisano osobno dla
[dns1](DOQ-DNS1-DEPLOYMENT.md) i [dns2](DOQ-DNS2-DEPLOYMENT.md).

## 6. Wycofanie

Na jednym hoście naraz: zatrzymaj i wyłącz dnsdist, usuń jego hook TLS
(zachowaj `bind-tls`), następnie wyłącz `isp-doq-firewall`. Usuń nowy drop-in
i wykonaj `systemctl daemon-reload`. Jeśli wdrożenie zastępowało wcześniejszy
frontend/firewall, przywróć ich zapisane konfiguracje i stan usług.
Usuń dodatkowy include backendu z BIND i wykonaj
`named-checkconf && systemctl reload named`. Usuń nadpisanie portów Fail2Ban
tylko jeśli chcesz przywrócić wcześniejszy zakres banów, następnie zweryfikuj
konfigurację i przebuduj odpowiednie jaile jak wyżej. Nie odtwarzaj całego
starego rulesetu nad aktualnymi banami. Sprawdź DNS/DoT/DoH i obie RPZ.

## Źródła

- [Netfilter: kolejność hooków](https://wiki.nftables.org/wiki-nftables/index.php/Netfilter_hooks)
- [Fail2Ban: klient i reload](https://github.com/fail2ban/fail2ban/blob/1.1.0/man/fail2ban-client.1)
