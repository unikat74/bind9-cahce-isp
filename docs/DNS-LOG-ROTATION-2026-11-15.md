# Rotacja logów FUZ i Fione — 15 listopada 2026

Na obu DNS-ach każdej sieci wdrożono wspólny wariant dla security.log i rpz.log:
logrotate daily + maxsize 20M, rotate 7, compress + delaycompress, create
0640 bind bind, su bind bind. Datowane archiwa zawierają także godzinę i sekundy,
więc dodatkowa rotacja rozmiarowa w tym samym dniu nie koliduje z dzienną.
Najnowsze archiwum zostaje nieskompresowane do kolejnej rotacji dla bezpieczeństwa
odczytu Fail2Ban. Zachowuje się 7 archiwów, nie gwarantowane 7 dni przy dużym ruchu.

Konfiguracja: `/etc/logrotate-isp-dns.conf`, poza katalogiem globalnego logrotate.
Jednostki: isp-dns-logrotate.service i isp-dns-logrotate.timer. Timer co godzinę,
Persistent=true, AccuracySec=1min. Stan: `/var/lib/logrotate/isp-dns.status`.
Pozostałe logi systemowe nadal obsługuje standardowy dzienny logrotate.timer.
Kontrola rozmiaru jest okresowa — 20 MiB nie jest twardym limitem pliku.

Wyłączono natywną rotację BIND dla obu kanałów (size unlimited), a stare
wyłączone wpisy named-security na Fione wskazują teraz nową jednostkę.
Postrotate wykonuje rndc reconfig, bez restartu BIND. Fail2Ban nadal czyta
security.log. Historyczne archiwa wcześniejszych schematów pozostawiono.

Odbiór na każdym hoście: realna rotacja obu plików, odmowa AXFR w nowym
security.log i rewrite ThreatFox w nowym rpz.log, druga rotacja i gzip -t,
ponowne wpisy po niej, DNSSEC z AD. Usługi named i Fail2Ban aktywne,
timer ma autostart, jednostka rotacji Result=success, brak failed units.

Kopie poprzedniej konfiguracji:

- FUZ dns2: `/root/dns-logrotate-before-lcl6n281`;
- FUZ dns1: `/root/dns-logrotate-before-ku9l9twr`;
- Fione dns2: `/root/dns-logrotate-before-3btnw615`;
- Fione dns1: `/root/dns-logrotate-before-wdv785ou`.

Rollback pojedynczego hosta: wyłączyć timer isp-dns-logrotate, przywrócić
named.conf.logging (FUZ) albo named.conf (Fione) z kopii, wykonać named-checkconf
i rndc reconfig. Przywrócić zapisany named-security tam, gdzie występował.
Nie usuwać aktywnych logów ani archiwów. Po usunięciu nowych jednostek wykonać
daemon-reload i sprawdzić zapis oraz Fail2Ban.
