# Wdrożenie RPZ ThreatFox i rejestru hazardowego

`dns1` utrzymuje obie strefy primary. `dns2` odbiera je przez transfer
uwierzytelniony TSIG. Obie polityki są aktywne: ThreatFox NXDOMAIN, antyhazard policy given.
Obowiązują limity i zabezpieczenia z [RESOLVER-STANDARD.md](RESOLVER-STANDARD.md).

## dns1 — primary

1. Zapisz Auth-Key ThreatFox w `/etc/threatfox.env` (`root:root`, `0600`).
2. Wygeneruj osobno `threatfox-rpz-xfr.key` i `hazard-rpz-xfr.key`
   w `/etc/bind/keys/` (`root:bind`, `0640`), jak w INSTALL.md.
3. Skopiuj `installer/inventory.env.example` do ignorowanego przez Git pliku
   `installer/inventory.env` i ustaw rzeczywiste adresy obu serwerów.
4. Uruchom `./installer/bootstrap-rpz.sh primary`.
5. Dołącz `/etc/bind/named.conf.rpz` w `named.conf.local`, a
   `/etc/bind/named.conf.rpz-options` wewnątrz `options {}`.
6. Użyj osobnych security_file/rpz_file z instalatora wspólnej polityki.
7. Wykonaj `named-checkconf && systemctl reload named`.
8. Po testach włącz aktualizacje:

```sh
systemctl enable --now threatfox-rpz.timer hazard-rpz.timer
```

## dns2 — secondary

1. Skopiuj oba pliki TSIG z dns1, każdy dla swojej strefy; ustaw `root:bind`, `0640`.
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
tail -f /var/log/named/rpz.log
```

Dla ThreatFox oczekuj NXDOMAIN i wpisu `rpz QNAME NXDOMAIN rewrite`. Dla domeny
obecnej w rejestrze MF oczekuj adresu przekierowania `145.237.235.240`, a dla
jej niezdefiniowanej subdomeny — `NXDOMAIN`.

Pełna kolejność, konfiguracja Certbota i testy są w `docs/INSTALL.md`.
