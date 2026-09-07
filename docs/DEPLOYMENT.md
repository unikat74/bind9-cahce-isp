# Wdrożenie RPZ ThreatFox i rejestru hazardowego

`dns1` utrzymuje obie strefy primary. `dns2` odbiera je przez transfer
uwierzytelniony TSIG. ThreatFox działa w trybie audytu, a rejestr hazardowy w
trybie aktywnej polityki.

## dns1 — primary

1. Zapisz Auth-Key ThreatFox w `/etc/threatfox.env` (`root:root`, `0600`).
2. Wygeneruj `/etc/bind/keys/threatfox-rpz-xfr.key` (`root:bind`, `0640`).
3. Skopiuj `installer/inventory.env.example` do ignorowanego przez Git pliku
   `installer/inventory.env` i ustaw rzeczywiste adresy obu serwerów.
4. Uruchom `./installer/bootstrap-rpz.sh primary`.
5. Dołącz `/etc/bind/named.conf.rpz` w `named.conf.local`, a
   `/etc/bind/named.conf.rpz-options` wewnątrz `options {}`.
6. Dodaj `category rpz { security_file; };` do konfiguracji logowania.
7. Wykonaj `named-checkconf && systemctl reload named`.
8. Po testach włącz aktualizacje:

```sh
systemctl enable --now threatfox-rpz.timer hazard-rpz.timer
```

## dns2 — secondary

1. Skopiuj dokładnie ten sam plik TSIG z dns1 i ustaw `root:bind`, `0640`.
2. Przygotuj `installer/inventory.env`.
3. Uruchom `./installer/bootstrap-rpz.sh secondary`.
4. Dodaj oba include'y i kategorię logowania tak samo jak na dns1.
5. Wykonaj `named-checkconf && systemctl reload named`.
6. Nie włączaj timerów RPZ na dns2.

## Test

```sh
rndc zonestatus rpz.threatfox.abuse.ch
rndc zonestatus rpz.hazard.mf.gov.pl
dig @127.0.0.1 qaqfaxian.com A
tail -f /var/log/named/security.log | grep --line-buffered 'rpz'
```

Dla ThreatFox oczekuj w logu `disabled rpz` bez zmiany odpowiedzi. Dla domeny
obecnej w rejestrze MF oczekuj adresu przekierowania `145.237.235.240`, a dla
jej niezdefiniowanej subdomeny — `NXDOMAIN`.

Pełna kolejność, konfiguracja Certbota i testy są w `docs/INSTALL.md`.
