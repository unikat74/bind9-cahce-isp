# BIND 9 cache resolver dla ISP

**Status: produkcja odebrana, zakres podstawowy zakończony 7 września 2026.**

Konfiguracja referencyjna dla pary BIND 9 na Debianie: rekurencyjny resolver/cache,
DNS-over-TLS, DNS-over-HTTPS, ograniczenie otwartego resolvera, Fail2Ban oraz
ThreatFox RPZ w trybie audytu i rejestr hazardowy MF w aktywnej strefie RPZ.

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

## Dokumentacja

Punktem wejścia jest [`docs/README.md`](docs/README.md). Zawiera uporządkowaną
nawigację dla instalacji, eksploatacji, diagnostyki, kompatybilności i
rollbacku. Końcowy stan produkcji oraz kryteria ponownego otwarcia opisuje
[`docs/PROJECT-STATUS.md`](docs/PROJECT-STATUS.md).

## Zawartość repozytorium

- `bind/` — szablony konfiguracji BIND;
- `servers/` — snapshoty faktycznych konfiguracji dns1 i dns2, z zachowaniem
  ścieżek systemowych i bez sekretów;
- `scripts/` — aktualizacja ThreatFox i rejestru hazardowego RPZ;
- `systemd/` — cykliczne uruchamianie aktualizacji na dns1;
- `installer/bootstrap-rpz.sh` — przygotowanie obu RPZ dla roli primary lub
  secondary;
- `docs/` — wdrożenie i testy.

Pierwsze wdrożenie zaczynaj od dokumentu wskazanego w indeksie jako „Czysty
Debian 13”. Nie kopiuj bezpośrednio snapshotów `servers/` na inny system.

Nigdy nie commituj API key, TSIG secret, certyfikatów TLS ani pobranego feedu RPZ.
