# BIND 9 cache resolver dla ISP

Konfiguracja referencyjna dla pary BIND 9 na Debianie: rekurencyjny resolver/cache,
DNS-over-TLS, DNS-over-HTTPS, ograniczenie otwartego resolvera, Fail2Ban oraz
ThreatFox RPZ w trybie audytu oraz migrację rejestru hazardowego MF do RPZ.

Obsługa rejestru hazardowego jest nową implementacją funkcji używanego wcześniej
skryptu `hazardBind v0.7 [2022-02-18]`, którego nagłówek wskazuje
[www.kazuko.pl](https://www.kazuko.pl/). Powody migracji oraz wpływ na wydajność
i bezpieczeństwo opisuje dokument `docs/HAZARD-RPZ-MIGRATION.md`.
Publiczny adres przekierowania rejestru hazardowego to `145.237.235.240`.

## Architektura

```text
klienci ── DNS/DoT/DoH ── dns1 (primary RPZ) ── TSIG/AXFR ── dns2 (secondary RPZ)
                               ├── ThreatFox API
                               └── rejestr hazardowy MF
```

`dns1` jest jedyną maszyną z kluczem ThreatFox i jedyną pobierającą oba źródła.
`dns2` odbiera obie strefy RPZ po zabezpieczonym transferze TSIG. Stary model
dziesiątek tysięcy stref hazardowych został usunięty z aktywnej konfiguracji.

## Zawartość

- `bind/` — szablony konfiguracji BIND;
- `servers/` — snapshoty faktycznych konfiguracji dns1 i dns2, z zachowaniem
  ścieżek systemowych i bez sekretów;
- `scripts/` — aktualizacja ThreatFox i rejestru hazardowego RPZ;
- `systemd/` — cykliczne uruchamianie aktualizacji na dns1;
- `installer/bootstrap-rpz.sh` — przygotowanie obu RPZ dla roli primary lub
  secondary;
- `docs/` — wdrożenie i testy.

Diagnostykę obciążenia, wartości domyślne limitów i bezpieczne skalowanie opisuje
[`docs/DIAGNOSTICS-CAPACITY.md`](docs/DIAGNOSTICS-CAPACITY.md).

Pierwsze wdrożenie zaczynaj od
[`docs/FRESH-DEBIAN-13.md`](docs/FRESH-DEBIAN-13.md), a następnie korzystaj z
pełnej instrukcji komponentów w [`docs/INSTALL.md`](docs/INSTALL.md).
Migrację istniejących stref hazardowych prowadzi osobna instrukcja
[`docs/HAZARD-RPZ-MIGRATION.md`](docs/HAZARD-RPZ-MIGRATION.md).

Nigdy nie commituj API key, TSIG secret, certyfikatów TLS ani pobranego feedu RPZ.
