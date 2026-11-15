# Antyhazard FUZ — 15 listopada 2026

Na dns1 i dns2 aktywowano RPZ `rpz.hazard.mf.gov.pl`, pobraną z
`https://hazard.mf.gov.pl/api/Register`: 59 849 aktywnych domen,
0 odrzuconych, serial początkowy `1794707803`.

dns1 pobiera rejestr i udostępnia strefę dns2 przez TSIG
`hazard-rpz-xfr` (osobny nowy klucz, tylko na hostach).
dns2 jest secondary; potwierdzono transfer z TSIG, status success,
119 701 rekordów i zgodność seriali. Transfer bez klucza jest zabroniony.

W BIND włączono `response-policy` z `policy given` i `break-dnssec yes`.
Nazwy wpisane do rejestru odpowiadają A `145.237.235.240`;
AAAA zwraca pustą odpowiedź, subdomeny NXDOMAIN zgodnie z dotychczasowym
modelem aktualizatora. Testowana domena IDN: `xn--drckglck-75ae.de`.
Przeszły DNS UDP/TCP, DoT i DoH po IPv4/IPv6 na obu serwerach;
zwykła podpisana domena zachowuje AD, dnssec-failed.org zwraca SERVFAIL.

Na dns1 zainstalowano aktualizator repozytorium
`/usr/local/sbin/update-hazard-rpz`, jednostki hazard-rpz.service/timer
i python3-idna. Timer: 06:00 i 18:00 Europe/Warsaw, Persistent=true.
dns2 nie ma timera pobierania. Aktualizator weryfikuje TLS, ogranicza czas
pobierania, wymaga minimum 10 000 domen, sprawdza named-checkzone
i atomowo zastępuje strefę. Błąd pobrania zachowuje ostatnią poprawną strefę.

Kopie konfiguracji przed aktywacją:

- dns1: `/root/hazard-backup-20261115-025659/`;
- dns2: `/root/hazard-backup-20261115-025702/`.

Konfiguracja strefy: `/etc/bind/named.conf.hazard-rpz`.
Primary: `/etc/bind/rpz/hazard.rpz`;
secondary: `/var/cache/bind/rpz/hazard.rpz`.
Zdarzenia polityki: `/var/log/named/rpz.log`.

Przy rollbacku zatrzymać timer na dns1, przywrócić named.conf
i named.conf.options z odpowiedniej kopii, sprawdzić named-checkconf,
wykonać rndc reconfig. Nie usuwać sprawdzonej strefy ani klucza.
