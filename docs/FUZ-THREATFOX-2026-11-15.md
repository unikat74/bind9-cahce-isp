# ThreatFox FUZ — 15 listopada 2026

Na polecenie operatora użyto jego istniejącego Auth-Key z dns1.fione.pl.
Przeniesiono go przez SSH bez wyświetlania do `/etc/threatfox.env`
na dns1.fuz.pl (root, 0600). dns2.fuz.pl nie ma klucza API.
Nie zmieniano konfiguracji dns1.fione.pl.

dns1 pobiera RPZ ThreatFox, dns2 otrzymuje ją przez osobny nowy TSIG
`threatfox-rpz-xfr`. Transfer TSIG zakończył się sukcesem, serial
początkowy obu stref `2611150227`. Aktywna polityka `policy nxdomain`
ma pierwszeństwo przed antyhazardem. Timer pobierania tylko na dns1:
codziennie 05:00 Europe/Warsaw, Persistent=true.

Aktualizator zachowuje poprzednią strefę przy błędzie pobrania/walidacji.
Pominięto jeden rekord o długości nazwy na drucie 256 bajtów; pozostała
strefa przeszła named-checkzone. Test uruchomienia przez systemd zakończył
się Result=success, ExecMainStatus=0.

Potwierdzono NXDOMAIN dla `advocaat-grimbergen.be` z aktualnego feedu:
DNS UDP/TCP, DoT, DoH po IPv4 i IPv6 na obu serwerach.
Log rpz.log potwierdza rewrite przez strefę ThreatFox.
Antyhazard IDN nadal zwraca 145.237.235.240, zwykła domena zachowuje AD,
dnssec-failed.org zwraca SERVFAIL.

Konfiguracja: `/etc/bind/named.conf.threatfox` oraz response-policy
w named.conf.options. Aktualizator: `/usr/local/sbin/update-threatfox-rpz`.
Strefa primary: `/etc/bind/rpz/threatfox.rpz`, secondary:
`/var/cache/bind/rpz/threatfox.rpz`.

Kopie aktywacji:

- dns1: `/root/threatfox-activate-kzmgztk1/`;
- dns2: `/root/threatfox-activate-1bgaa1ax/`.

Rollback: wyłączyć timer na dns1, odtworzyć named.conf.options
i named.conf.local z odpowiedniej kopii, sprawdzić named-checkconf
i wykonać rndc reconfig. Zachować klucze i ostatnią poprawną strefę.

## Własny klucz FUZ

Operator podmienił Auth-Key na własny w `/etc/threatfox.env` na dns1.
Aktualizacja zakończyła się sukcesem; serial 2611151326 i 27 461 węzłów
potwierdzono na obu hostach. Test blokady NXDOMAIN i log RPZ poprawne.
Klucz pozostaje poza repozytorium i nie jest potrzebny na dns2.
