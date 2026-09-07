# BIND 9 cache resolver dla ISP

Konfiguracja referencyjna dla pary BIND 9 na Debianie: rekurencyjny resolver/cache,
DNS-over-TLS, DNS-over-HTTPS, ograniczenie otwartego resolvera, Fail2Ban oraz
ThreatFox RPZ w trybie audytu.

## Architektura

```text
klienci ── DNS/DoT/DoH ── dns1 (primary RPZ) ── TSIG/AXFR ── dns2 (secondary RPZ)
                               │
                               └── ThreatFox API
```

`dns1` jest jedyną maszyną z kluczem ThreatFox. `dns2` odbiera strefę RPZ po
zabezpieczonym transferze TSIG.

## Zawartość

- `bind/` — szablony konfiguracji BIND;
- `servers/` — snapshoty faktycznych konfiguracji dns1 i dns2, z zachowaniem
  ścieżek systemowych i bez sekretów;
- `scripts/` — aktualizacja ThreatFox RPZ;
- `systemd/` — codzienne uruchamianie aktualizacji na dns1;
- `docs/` — wdrożenie i testy.

Pierwsze wdrożenie zaczynaj od
[`docs/FRESH-DEBIAN-13.md`](docs/FRESH-DEBIAN-13.md), a następnie korzystaj z
pełnej instrukcji komponentów w [`docs/INSTALL.md`](docs/INSTALL.md).

Nigdy nie commituj API key, TSIG secret, certyfikatów TLS ani pobranego feedu RPZ.
