# Kompatybilność klientów DNS, DoT i DoH

Stan zgodności zweryfikowany 7 września 2026 roku. RouterOS i BIND rozwijają
się niezależnie, dlatego każdą nową wersję oraz architekturę sprzętową należy
ponownie sprawdzić przed dodaniem jej do wspieranej macierzy.

Publiczne resolvery udostępniają trzy niezależne protokoły:

- klasyczny DNS — UDP/TCP 53;
- DNS-over-TLS (DoT) — TCP 853;
- DNS-over-HTTPS (DoH) — HTTP/2 na TCP 443, ścieżka `/dns-query`.

Działanie jednego protokołu nie dowodzi zgodności klienta z pozostałymi. W
szczególności starszy MikroTik może prawidłowo używać DNS/53, a jednocześnie nie
potrafić połączyć się bezpośrednio z natywnym DoH BIND-a.

## Polityka wsparcia

| Klient | DNS/53 | DoT/853 | Natywny DoH BIND/443 |
|---|---|---|---|
| Współczesny system lub aplikacja obsługująca standard | wspierany | wspierany | wspierany po teście HTTP/2 i certyfikatu |
| RouterOS 6.49.x, w tym CCR1016/TILE | wspierany | brak udokumentowanego klienta upstream | niewspierany |
| Inny lub nowszy RouterOS | wspierany | tylko jeśli dana wersja faktycznie udostępnia klienta DoT | wyłącznie po teście konkretnej wersji i architektury |

Nie wspieramy bezpośredniego wariantu:

```text
RouterOS 6.x ── DoH/HTTP/1.1 ── BIND native DoH/HTTP/2
```

Nie dołączamy również do instalatora warstwy zgodności przeznaczonej wyłącznie
dla starych RouterOS. Podstawowym rozwiązaniem dla takiego routera jest
klasyczny DNS do resolverów operatora. Połączenia na UDP/TCP 53 są ograniczone
ACL-em do sieci klientów, więc nie tworzą otwartego resolvera internetowego.

## Dlaczego RouterOS 6.49.x nie działa z tym DoH

RouterOS 6.49.x korzysta ze starszego mechanizmu DoH opartego na HTTP/1.1.
Natywny DoH w BIND korzysta z `libnghttp2`, a parametry BIND-a i obsługa
strumieni dotyczą HTTP/2. MikroTik w swojej dokumentacji nadal wskazuje brak
obsługi HTTP/2 jako powód niezgodności z serwisami wymagającymi tego protokołu.

Typowy objaw na MikroTiku:

```text
dns,error DoH server connection error: remote disconnected while in HTTP exchange
```

Podobne przypadki i diagnostykę użytkowników zbiera
[wątek społeczności MikroTik](https://forum.mikrotik.com/t/dns-error-doh-server-connection-error-remote-disconnected-while-in-http-exchange/140383).

W tej sytuacji mogą jednocześnie występować następujące fakty:

- rekord A/AAAA nazwy DoH jest prawidłowy;
- TCP 443 i negocjacja TLS dochodzą do skutku;
- certyfikat Let's Encrypt jest poprawny;
- `dig +https` z Debiana działa;
- RouterOS kończy wymianę błędem HTTP.

To wskazuje na niezgodność warstwy HTTP, a nie na problem z cache BIND-a,
rekurencją czy strefami RPZ.

Oficjalna dokumentacja MikroTik opisuje `use-doh-server`, wymóg rozwiązania
nazwy endpointu, instalację CA i listę zgodnych usług:
[DNS over HTTPS w RouterOS](https://help.mikrotik.com/docs/spaces/ROS/pages/37748767/DNS).
Dokumentacja BIND opisuje natywny listener DoH i równoległe strumienie HTTP/2:
[BIND — konfiguracja HTTP/DoH](https://bind9.readthedocs.io/en/v9.20.20/reference.html#http-block-grammar).

## DoT na MikroTiku

Nie należy mylić DoT z DoH. DoT używa osobnego protokołu na TCP 853, a DoH
przenosi pakiet DNS w HTTPS na TCP 443.

W udokumentowanych ustawieniach `/ip dns` RouterOS znajduje się
`use-doh-server`, ale nie ma odpowiednika `use-dot-server`. Dlatego projekt nie
traktuje wbudowanego cache DNS RouterOS 6.49.x jako klienta DoT. Port 853 na
naszych resolverach jest przeznaczony dla urządzeń i aplikacji, które naprawdę
implementują DoT.

Router może przepuszczać ruch DoT klienta końcowego przez firewall, ale nie
oznacza to, że sam używa DoT jako upstreamu.

## Zalecana konfiguracja starego MikroTika

Dla RouterOS 6.49.x usuń niedziałający endpoint DoH i użyj obu resolverów
operatora po DNS/53:

```routeros
/ip dns set use-doh-server="" \
    servers=ADRES_DNS1,ADRES_DNS2 \
    allow-remote-requests=yes
/ip dns cache flush
```

Następnie sprawdź:

```routeros
/ip dns print
/resolve example.net
/log print where topics~"dns"
```

Jeśli router odpowiada klientom LAN, jego własny port 53 musi być dostępny
wyłącznie z zaufanych interfejsów i sieci. Dokumentacja MikroTik również
ostrzega przed wystawieniem `allow-remote-requests=yes` bez ograniczeń
firewalla.

Nie używaj `verify-doh-cert=no` jako rozwiązania problemu HTTP/1.1 kontra
HTTP/2. Wyłączenie walidacji usuwa ochronę przed podszyciem się pod serwer, a
nie dodaje obsługi brakującej wersji HTTP.

## Diagnostyka zgodności

Najpierw sprawdź wersję i architekturę routera:

```routeros
/system resource print
/ip dns print
```

Test kontrolny nowoczesnym klientem:

```sh
dig @dns1.example.net example.net A +https \
  +tls-ca +tls-hostname=dns1.example.net
dig @dns1.example.net example.net A +tls \
  +tls-ca +tls-hostname=dns1.example.net
```

Sprawdzenie negocjacji HTTP/2:

```sh
openssl s_client -connect dns1.example.net:443 \
  -servername dns1.example.net -alpn h2 </dev/null 2>/dev/null | \
  grep 'ALPN protocol'
```

Oczekiwany wynik to `ALPN protocol: h2`. Jeśli powyższe testy działają, a
RouterOS 6.x nadal zapisuje `remote disconnected while in HTTP exchange`, nie
zmieniaj certyfikatu ani ACL BIND-a — klient jest niezgodny z endpointem.

Na produkcyjnym BIND 9.20.26 test z `-alpn h2` wynegocjował `h2`, a test z
`-alpn http/1.1` zakończył się komunikatem `No ALPN negotiated`. Serwer jest
skompilowany z `libnghttp2 1.64.0`. To odpowiada błędowi zaobserwowanemu na
RouterOS 6.49.19/TILE.

Na serwerze można potwierdzić próbę połączenia:

```sh
tcpdump -ni ens18 'host ADRES_ROUTERA and tcp port 443'
journalctl -u named --since '10 minutes ago' --no-pager
```

## Niewspierana proteza dla HTTP/1.1

Jeżeli organizacja musi utrzymać RouterOS 6.x i jednocześnie wymaga DoH, może
samodzielnie postawić zgodny frontend/proxy DNS, który:

1. przyjmie DoH po HTTP/1.1 od MikroTika;
2. zweryfikuje metodę, ścieżkę i typ treści DoH;
3. przekaże zapytanie do BIND-a po DNS na prywatnym adresie lub loopbacku;
4. nie udostępni backendu jako otwartego resolvera.

Do tego celu lepszy jest proxy świadomy protokołu DNS, na przykład `dnsdist`,
niż zwykłe `proxy_pass` w nginx. Oficjalny przewodnik opisuje wejściowy DoH,
ścieżkę `/dns-query`, certyfikaty i przekazywanie do backendu:
[dnsdist — DNS over HTTPS](https://www.dnsdist.org/guides/dns-over-https.html).
Dokumentacja dnsdist obejmuje zarówno DNS over HTTP/1, jak i HTTP/2 oraz
udostępnia liczniki zapytań według wersji HTTP.

Taka warstwa nie jest częścią tego projektu ani wspieranej produkcji. Dodaje
kolejną usługę, aktualizację certyfikatów, monitoring, limity, logi i punkt
awarii. Frontend nie może bez dodatkowego adresu współdzielić TCP 443 z
natywnym listenerem BIND-a; trzeba użyć osobnego adresu IP albo przenieść jeden
z listenerów na wewnętrzny port. Nieszyfrowany backend może nasłuchiwać
wyłącznie na loopbacku lub odseparowanej sieci.

## Informacja dla klienta końcowego

Operator może przekazać klientowi następujący komunikat:

> Resolver obsługuje standardowy DNS, DoT oraz DoH oparty na HTTP/2. Wbudowany
> klient DoH RouterOS 6.x nie jest zgodny z tym endpointem. Dla tego urządzenia
> należy użyć DNS operatora na porcie 53 albo wymienić/aktualizować platformę i
> potwierdzić obsługę HTTP/2. Zewnętrzne proxy zgodności pozostaje po stronie
> klienta i nie jest objęte wsparciem operatora.
