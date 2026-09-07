# Migracja rejestru hazardowego do RPZ

## Stan wdrożenia

Migracja została wdrożona produkcyjnie 7 września 2026 roku na `dns1` i `dns2`.
Stare pliki zostały usunięte z aktywnych katalogów po testach obu serwerów.
Kopie potrzebne do awaryjnego odtworzenia statycznej konfiguracji znajdują się
na każdym serwerze w `/root/legacy-hazardbind-20260907.tar.gz`.

Sumy SHA-256 archiwów produkcyjnych:

- dns1: `c7796d4f5fbd54454d996c2c289d5b0940b9962b2c6007c388117b1786f167ee`;
- dns2: `8cc9f5063d160be26ccde7c4f76c55edd002041130f42033e7e0b01495708c44`.

Archiwa zawierają dawne pliki konfiguracyjne i kopie sprzed migracji. Skrypt
`/opt/hazardBind.pl` oraz jego cron były już nieobecne podczas sprzątania, więc
archiwa ich nie zawierają.

`dns1` pobiera rejestr co godzinę przez `hazard-rpz.timer`, buduje primary
`rpz.hazard.mf.gov.pl`, a `dns2` odbiera tę strefę jako secondary przez transfer
uwierzytelniony TSIG. ThreatFox nadal działa wyłącznie w trybie audytu.

## Pochodzenie rozwiązania

Punktem wyjścia był używany wcześniej skrypt `/opt/hazardBind.pl`. Jego nagłówek
wskazuje stronę [www.kazuko.pl](https://www.kazuko.pl/) oraz nazwę i wersję
`hazardBind v0.7 [2022-02-18]`. Skrypt pobiera rejestr Ministerstwa Finansów i
dla każdej aktywnej domeny generuje osobną strefę BIND korzystającą ze wspólnego
pliku `db.hazard-redirect`.

Nowy `update-hazard-rpz` jest napisaną od nowa implementacją tej funkcji. Nie
zawiera kopii kodu `hazardBind.pl`; zachowuje źródło danych, przekierowanie oraz
dotychczasową semantykę odpowiedzi DNS, ale zapisuje listę jako jedną strefę
Response Policy Zone.

## Dlaczego przechodzimy na RPZ

Na badanym serwerze stary skrypt tworzył 57 539 aktywnych deklaracji `zone`, a
cały BIND utrzymywał 57 563 strefy. Każda z nich wymaga osobnej struktury strefy,
obsługi w konfiguracji i udziału w operacjach przeładowania. Plik konfiguracyjny
z deklaracjami zajmował około 6,9 MB.

Wersja RPZ przechowuje te same 57 539 domen w jednej strefie. Testowy plik ma
około 4,5 MB i zawiera po dwie reguły na domenę: przekierowanie dokładnej nazwy
oraz NXDOMAIN dla jej pozostałych subdomen. Najważniejsze oczekiwane korzyści:

- znacznie mniej obiektów stref i prostsza konfiguracja BIND;
- ładowanie i aktualizacja jednego pliku zamiast dziesiątek tysięcy stref;
- możliwość przekazania jednej strefy z `dns1` do `dns2` przez IXFR/AXFR i TSIG;
- jedna polityka, którą można najpierw uruchomić w trybie audytu;
- łatwiejsze wycofanie zmiany i kontrola aktualnego numeru seryjnego.

RPZ dodaje wyszukanie polityki podczas zapytania rekurencyjnego, więc nie jest
całkowicie pozbawione kosztu. Dla tej instalacji powinno być jednak wyraźnie
lżejsze operacyjnie od utrzymywania około 57 tysięcy osobnych stref. Faktyczne
zużycie RAM, czas przeładowania i opóźnienia sprawdzimy przed i po przełączeniu;
nie zakładamy z góry konkretnego procentu poprawy.

## Wpływ na bezpieczeństwo

Stary `hazardBind.pl` wyłącza sprawdzanie certyfikatu i nazwy hosta TLS podczas
pobierania rejestru. Pozwala to atakującemu znajdującemu się na trasie podmienić
pobieraną listę. Zapis odbywa się bezpośrednio do aktywnego pliku, bez kontroli
minimalnej liczby wpisów i bez `named-checkzone` przed przeładowaniem BIND-a.

Nowy generator:

- używa systemowej weryfikacji certyfikatu HTTPS i nazwy serwera MF;
- normalizuje IDN zgodnie z IDNA2008/UTS #46, sprawdza składnię domen i usuwa
  duplikaty;
- odrzuca podejrzanie małą listę zamiast zastępować działającą strefę;
- najpierw zapisuje plik tymczasowy i sprawdza go przez `named-checkzone`;
- podmienia poprawny plik atomowo, z prawami `root:bind 0640`;
- nie przeładowuje strefy, jeżeli zawartość rejestru się nie zmieniła;
- nadaje każdej zmienionej wersji serial większy od poprzedniego, również po
  cofnięciu zegara systemowego;
- korzysta z blokady `flock`, aby dwie aktualizacje nie wykonały się równocześnie;
- może przekazywać strefę do `dns2` z uwierzytelnieniem TSIG.

RPZ chroni tylko klientów rzeczywiście korzystających z tych resolverów. Nie
blokuje samodzielnie zewnętrznych DNS, DoH ani bezpośrednich połączeń do adresów
IP. Jeśli operator chce uniemożliwić omijanie polityki, jest to osobne zadanie
dla zapory i polityki sieciowej.

### Domeny ze znakami narodowymi

DNS przesyła międzynarodowe nazwy domen w postaci ASCII Compatible Encoding,
czyli punycode. Przykładowo `drückglück.de` ma postać
`xn--drckglck-75ae.de`, a `faß.de` ma postać `xn--fa-hia.de`. Generator używa
IDNA2008 z mapowaniem UTS #46, takim jak współczesne aplikacje, a następnie
umieszcza postać `xn--…` w RPZ. Dzięki temu polskie `ą ć ę ł ń ó ś ź ż`,
niemieckie `ä ö ü ß` i znaki innych obsługiwanych alfabetów trafiają do tej
samej nazwy DNS, o którą pyta klient.

Pakiet `python3-idna` jest wymagany. Nie należy wracać do wbudowanego kodeka
`str.encode("idna")`, ponieważ implementuje starsze IDNA2003 — na przykład
zmieniłby `faß.de` na inną nazwę `fass.de`.

## Zachowanie zgodne z dotychczasowymi strefami

Generator domyślnie zapisuje dla każdej pozycji:

```dns
example.invalid   300 IN A 145.237.235.240
*.example.invalid 300 IN CNAME .
```

Pierwszy rekord przekierowuje dokładną nazwę. Drugi zwraca NXDOMAIN dla jej
niezdefiniowanych subdomen, co odpowiada zachowaniu dotychczasowej osobnej
strefy master. Opcja `--subdomains allow` ogranicza RPZ tylko do dokładnych nazw,
a `--subdomains redirect` przekierowuje również wszystkie subdomeny.

## Etap testowy — bez wpływu na odpowiedzi DNS

Na `dns1`:

```bash
install -o root -g root -m 0755 scripts/update-hazard-rpz \
  /usr/local/sbin/update-hazard-rpz
mkdir -p -m 2750 /etc/bind/rpz
chown root:bind /etc/bind/rpz

/usr/local/sbin/update-hazard-rpz \
  --output /etc/bind/rpz/hazard.rpz.test

/usr/bin/named-checkzone -k ignore rpz.hazard.mf.gov.pl \
  /etc/bind/rpz/hazard.rpz.test
head -n 12 /etc/bind/rpz/hazard.rpz.test
```

Ponowne uruchomienie bez zmiany rejestru ma wypisać `bez zmian`. Generator:

- weryfikuje certyfikat HTTPS serwera MF;
- odrzuca nieprawidłowe nazwy;
- nie zastępuje dobrej strefy, gdy pobieranie lub walidacja się nie powiedzie;
- zapisuje plik atomowo;
- wymaga co najmniej 10 000 aktywnych wpisów;
- zmienia serial i przeładowuje strefę tylko po zmianie zawartości.

## Kontrola po wdrożeniu

```bash
named-checkconf
rndc zonestatus rpz.hazard.mf.gov.pl
rndc status | grep 'number of zones'
systemctl list-timers hazard-rpz.timer

dig @127.0.0.1 www.reels122.com A +short
dig @127.0.0.1 rpz-test-subdomain.www.reels122.com A
dig @127.0.0.1 google.com A +short
```

Na obu serwerach liczba stref po migracji wynosiła 25 zamiast 57 564. Pierwszy
test hazardowy zwracał adres przekierowania, test subdomeny zwracał NXDOMAIN, a
zwykłe rozwiązywanie nazw działało prawidłowo.

## Rollback

Rollback jest procedurą awaryjną i przywraca statyczny stan sprzed migracji,
ale nie przywraca automatycznej aktualizacji przez stary skrypt. Najpierw
sprawdź i rozpakuj właściwe archiwum na każdym serwerze:

```bash
sha256sum /root/legacy-hazardbind-20260907.tar.gz
tar -tzf /root/legacy-hazardbind-20260907.tar.gz
tar -C / -xzf /root/legacy-hazardbind-20260907.tar.gz
```

Następnie wyłącz aktualizację RPZ i przywróć kopie konfiguracji:

```bash
systemctl disable --now hazard-rpz.timer
cp -a /etc/bind/named.conf.pre-hazard-rpz /etc/bind/named.conf
cp -a /etc/bind/named.conf.rpz-options.pre-hazard-rpz \
  /etc/bind/named.conf.rpz-options
cp -a /etc/bind/named.conf.rpz.pre-hazard-rpz /etc/bind/named.conf.rpz
named-checkconf
rndc reconfig
```

Po awaryjnym przywróceniu trzeba osobno zaprojektować mechanizm aktualizacji;
nie zaleca się ponownego uruchamiania starego `hazardBind.pl` z wyłączoną
weryfikacją TLS. Preferowany powrót do normalnej pracy to naprawa przyczyny i
ponowne włączenie `hazard-rpz.timer` na dns1.
