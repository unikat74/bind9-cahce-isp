# Snapshoty serwerów

Katalogi `dns1/` i `dns2/` odzwierciedlają ścieżki na produkcyjnych
serwerach, np. `dns1/etc/bind/named.conf.options` odpowiada
`/etc/bind/named.conf.options` na dns1.

Celowo wykluczone z repozytorium:

- `/etc/threatfox.env` — Auth-Key ThreatFox;
- `/etc/bind/keys/*.key` i `/etc/bind/rndc.key` — sekrety TSIG/RNDC;
- `/etc/bind/tls/*.pem` — klucze i certyfikaty TLS;
- `/etc/bind/rpz/threatfox.rpz` — pobrany feed ThreatFox;
- `/etc/bind/rpz/hazard.rpz` — wygenerowana strefa rejestru MF.

Snapshoty nie zawierają już starego `db.hazard-redirect` ani
`named.conf.hazard-redirect`. Produkcja korzysta z jednej strefy hazardowej
RPZ, a kopie awaryjne starej konfiguracji pozostają wyłącznie w chronionych
archiwach na serwerach.

Sekrety przechowuj wyłącznie na serwerach lub w menedżerze sekretów.
