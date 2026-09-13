# BIND 9 cache resolver dla ISP

**Status: produkcja odebrana, zakres podstawowy zakończony 7 września 2026.**

Rozszerzenie DoQ i DNSCrypt przez dnsdist jest opisane w
[`docs/DOQ-DNSCRYPT.md`](docs/DOQ-DNSCRYPT.md). Zawiera szablony i obsługę
certyfikatów. DoQ wdrożono na obu serwerach — wyniki odbioru
[dns1](docs/DOQ-DNS1-DEPLOYMENT.md) i [dns2](docs/DOQ-DNS2-DEPLOYMENT.md).
DNSCrypt pozostaje domyślnie wyłączony: testy
wykryły błąd pobierania certyfikatu po TCP w pakietach dnsdist 2.1.2 i 2.0.9.

**Instalacja działającego DoQ:** [`docs/DOQ-INSTALL.md`](docs/DOQ-INSTALL.md).
Zawiera szablon nftables odrzucający UDP 853 spoza ACL od pierwszego pakietu,
jednostki systemd, porty Fail2Ban, odnowienia TLS, testy i wycofanie.

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
- `dnsdist/` — opcjonalny frontend DoQ/DNSCrypt z backendem BIND przez PROXYv2;
- `nftables/` — szablon ACL klientów dla DoQ, DROP bez logowania pakietów;
- `fail2ban/` — nadpisanie portów istniejących jaili DNS, w tym UDP 853;
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
