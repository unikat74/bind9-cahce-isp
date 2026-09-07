# Diagnostyka limitów i pojemności BIND 9

Ten runbook dotyczy BIND 9.20 na resolverach ISP obsługujących klasyczny DNS,
DoT i DoH. Limit zwiększaj dopiero wtedy, gdy pomiary pokazują trwałe zbliżanie
się do niego. Sam komunikat `SERVFAIL` albo `quota reached` nie dowodzi, że
globalny limit klientów jest zbyt niski — przyczyną może być niedostępny
forwarder, błędna domena, utrata pakietów albo adaptacyjna ochrona upstreamu.

## Najważniejsze limity i wartości domyślne

| Parametr | Domyślnie w BIND 9.20 | Co ogranicza |
|---|---:|---|
| `tcp-clients` | 150 | Wszystkie jednoczesne połączenia klienckie TCP przyjmowane przez BIND. |
| `recursive-clients` | 1000 | Trwające zapytania rekurencyjne; próg miękki wynosi 900 dla limitu 1000. |
| `clients-per-query` | 10 | Początkowa liczba klientów oczekujących na ten sam `qname/qtype/qclass`; BIND dostraja ją automatycznie. |
| `max-clients-per-query` | 100 | Górna granica klientów oczekujących na dokładnie to samo zapytanie. |
| `http-listener-clients` | 300 na listener | Aktywne połączenia DoH dla jednego listenera. |
| `http-streams-per-connection` | 100 | Równoległe strumienie HTTP/2 w jednym połączeniu DoH. |
| `tcp-listen-queue` | 10 | Długość kolejki oczekujących połączeń dla każdego gniazda nasłuchującego. |
| `fetches-per-zone` | 0, bez stałego limitu | Równoległe zapytania iteracyjne dotyczące jednej strefy. |
| `fetches-per-server` | 0, bez stałego limitu początkowego | Zapytania do jednego serwera nadrzędnego; BIND może obniżyć limit dynamicznie po wykryciu timeoutów. |
| `max-cache-size` | 90% RAM dla każdego rekurencyjnego cache/view | Dane cache i ich metadane, a nie cała pamięć procesu. |

Źródłem wartości jest oficjalna dokumentacja
[BIND 9.20 — Configuration Reference](https://bind9.readthedocs.io/en/v9.20.20/reference.html).
Polecenia `rndc status`, `rndc recursing`, `rndc stats` oraz `rndc reset-stats`
opisuje oficjalna dokumentacja
[rndc dla stabilnego BIND 9.20](https://bind9.readthedocs.io/en/stable/manpages.html).

Nie ustawiaj wartości `0` tylko po to, aby usunąć ograniczenia. Publiczny
resolver bez bezpiecznych limitów łatwiej wyczerpać ruchem błędnym lub celowym.

## Jak czytać `rndc status`

```sh
rndc status
```

Przykład:

```text
recursive clients: 9/900/1000
recursive high-water: 160
tcp clients: 101/500
TCP high-water: 147
```

- `9/900/1000` oznacza: 9 bieżących klientów rekursji, próg miękki 900 i
  twardy limit 1000;
- `101/500` oznacza 101 bieżących połączeń TCP przy limicie 500;
- `high-water` jest najwyższą wartością od uruchomienia procesu albo ostatniego
  wyzerowania tego licznika;
- wartości szczytowe można wyzerować przed okresem pomiarowym:

```sh
rndc reset-stats recursive-high-water tcp-high-water
```

Nie zeruj ich bez zapisania wcześniejszego wyniku w systemie monitoringu.

## Szybki raport

Instalator umieszcza skrypt diagnostyczny w
`/usr/local/sbin/check-bind-capacity`. Domyślnie pokazuje status, pamięć,
limity deskryptorów, liczbę połączeń TCP/53, DoH/443 i DoT/853, przepełnienia
kolejki TCP, bieżące `Recv-Q/Send-Q`, conntrack oraz istotne logi z 15 minut:

```sh
/usr/local/sbin/check-bind-capacity
SINCE='2 hours ago' /usr/local/sbin/check-bind-capacity
```

Ręczny zestaw minimum:

```sh
rndc status
systemctl show named -p MemoryCurrent -p TasksCurrent -p LimitNOFILE
ps -C named -o pid,%cpu,%mem,rss,vsz,etime,cmd
ss -s
ss -Htan state established
journalctl -u named --since '1 hour ago' --no-pager | \
  grep -Ei 'tcp-clients|recursive-clients|clients-per-query|quota reached|spill|SERVFAIL|too many open files'
```

## Rekursje, upstreamy i `quota reached`

Gdy rośnie liczba `recursive clients`, wykonaj jednorazowo:

```sh
rndc recursing
less /var/cache/bind/named.recursing
```

Plik pokazuje klientów czekających na zakończenie rekursji oraz aktywne fetches
dla domen. Nie publikuj go — zawiera adresy klientów i odpytywane nazwy.

W konfiguracji tego projektu używane jest `forward only`. Komunikaty podobne do:

```text
quota reached resolving 'example/A/IN': 1.1.1.1#53
```

mogą oznaczać, że BIND wykrył timeouty lub przeciążenie danego forwardera i
dynamicznie ograniczył wysyłanie do niego zapytań. Najpierw porównaj wszystkie
forwardery:

```sh
for server in 1.1.1.1 1.0.0.1 8.8.8.8 8.8.4.4; do
  dig @"$server" example.net A +tries=1 +time=2 +stats
done
```

Jeżeli problem dotyczy jednego upstreamu, usuń lub napraw ten upstream zamiast
zwiększać `recursive-clients`.

## Statystyki BIND

Konfiguracja wskazuje:

```conf
statistics-file "/var/cache/bind/named_stats.txt";
```

Zrzut tworzy polecenie:

```sh
rndc stats
tail -n 250 /var/cache/bind/named_stats.txt
```

`rndc stats` dopisuje kolejne sekcje do pliku. Do monitorowania zapisuj różnice
liczników między kolejnymi pomiarami, zwłaszcza `QrySuccess`, `QrySERVFAIL`,
rekursje i zapytania odrzucone. Nie uruchamiaj pełnego `querylog` na stałe na
obciążonym resolverze; generuje bardzo dużo I/O i ujawnia historię klientów.

## Progi operacyjne

Oceniaj pomiary z godzin szczytu przez co najmniej kilka dni:

- poniżej 70% limitu — stan normalny;
- 70–80% — obserwacja trendu i przyczyny;
- 80–90% przez dłuższy czas — przygotowanie zwiększenia o 25–50%;
- powyżej 90%, odrzucenia lub osiąganie limitu — pilna diagnostyka, a następnie
  kontrolowane zwiększenie, jeśli ruch jest prawidłowy.

Krótki szczyt nie jest wystarczającym powodem do wielokrotnego podniesienia
limitu. Najpierw sprawdź, czy nie jest to skan, atak, uszkodzony klient albo
wolny forwarder.

### Kolejka przyjmowania TCP

`tcp-clients` i `tcp-listen-queue` rozwiązują różne problemy. Pierwszy parametr
ogranicza już przyjęte połączenia, a drugi połączenia czekające w kolejce na
`accept()`. Sprawdź:

```sh
ss -lnt 'sport = :53 or sport = :443 or sport = :853'
nstat -az | grep -E 'TcpExtListen(Overflows|Drops)'
```

Liczniki `nstat -az` są ogólnosystemowe i narastają od startu hosta — obejmują
również SSH oraz inne usługi. Zapisz dwa odczyty w odstępie podczas ruchu
szczytowego. Dopiero ich wzrost wraz z pełnym `Recv-Q` wskazuje na zbyt krótką
kolejkę BIND-a. Wtedy można zacząć od:

```conf
tcp-listen-queue 128;
```

Wartość nie może efektywnie przekroczyć systemowego `net.core.somaxconn`.
Po zmianie wykonaj kontrolowany restart jednego resolvera, aby mieć pewność, że
wszystkie gniazda zostały utworzone z nową kolejką, i potwierdź `Send-Q` przez
`ss -lnt`. Następnie obserwuj przyrost liczników, zanim zmienisz drugi serwer.

## Zwiększanie limitów

Parametry dodaj wewnątrz `options {}` w `/etc/bind/named.conf.options`:

```conf
// Przykład — wartości należy dobrać z pomiarów.
tcp-clients 750;
recursive-clients 1500;
http-listener-clients 500;
http-streams-per-connection 100;
tcp-listen-queue 128;
max-cache-size 1g;
```

Zwykle pozostaw `clients-per-query 10` i `max-clients-per-query 100`, ponieważ
BIND sam dostraja pierwszy parametr. Ich zwiększenie pomaga tylko wtedy, gdy
logi wskazują odrzucenia wielu legalnych klientów czekających na tę samą nazwę.

Procedura bezpiecznej zmiany:

1. Zapisz `rndc status`, pamięć procesu, bieżące statystyki i logi.
2. Zwiększ jeden rodzaj limitu o 25–50%, nie wszystkie naraz.
3. Sprawdź konfigurację i przeładuj BIND:

```sh
named-checkconf
rndc reconfig
rndc status
```

4. Potwierdź DNS, DoT, DoH i obie strefy RPZ.
5. Obserwuj przez co najmniej jeden pełny okres szczytu: wykorzystanie limitu,
   RAM, CPU, `SERVFAIL`, odrzucenia i opóźnienia.
6. Jeśli stan się pogorszył, przywróć poprzednią wartość i wykonaj ponownie
   `named-checkconf && rndc reconfig`.

## Limity systemowe

Najpierw porównaj limit BIND-a z limitem deskryptorów procesu:

```sh
systemctl show named -p LimitNOFILE
pid=$(systemctl show named -p MainPID --value)
grep 'Max open files' "/proc/$pid/limits"
```

Na sprawdzonych serwerach Debian 13 limit wynosi 524288, więc nie jest obecnie
wąskim gardłem. Jeśli na innym systemie jest zbyt niski, utwórz override:

```sh
systemctl edit named
```

```ini
[Service]
LimitNOFILE=262144
```

Zmiana limitu systemd wymaga restartu procesu, nie tylko `rndc reconfig`:

```sh
systemd-analyze verify named.service
systemctl restart named
systemctl show named -p LimitNOFILE
```

Restart wykonuj kolejno: najpierw jeden resolver, test z perspektywy klienta,
potem drugi. Nigdy nie restartuj obu jednocześnie.

Jeśli rosną `TcpExtListenOverflows` lub `TcpExtListenDrops`, sprawdź dodatkowo
`tcp-listen-queue` i systemowe `net.core.somaxconn`. Jeśli zapełnia się
`nf_conntrack_count`, problem leży w zaporze/conntrack, a nie w `tcp-clients`.

## Stan bazowy tej instalacji

Pomiar wykonany 7 września 2026 po migracji hazardu do RPZ:

| Serwer | Rekursje | Szczyt rekursji | TCP | Szczyt TCP | RAM BIND |
|---|---:|---:|---:|---:|---:|
| dns1 | 9/900/1000 | 160 | 101/500 | 147 | około 276 MB |
| dns2 | 1/900/1000 | 40 | 2/500 | 32 | około 196 MB |

Aktualny `tcp-clients 500` daje odpowiedni zapas. Nie zwiększaj go ponownie bez
nowych pomiarów pokazujących trwałe wykorzystanie co najmniej 70–80%.

Na dns1 systemowe liczniki wykazywały historycznie 331294 przepełnienia i
342273 odrzucenia kolejki listenerów, ale nie wzrosły w kontrolnym oknie 10
sekund. Na dns2 było odpowiednio 8 i 66. Wartości te nie pozwalają przypisać
zdarzeń konkretnie BIND-owi, dlatego należy monitorować ich przyrost w godzinach
szczytu. Obecny `net.core.somaxconn` wynosi 4096, natomiast listener BIND-a ma
domyślną kolejkę 10; jeśli liczniki nadal rosną, pierwszym kandydatem do zmiany
jest `tcp-listen-queue`, a nie kolejne zwiększenie `tcp-clients`.
