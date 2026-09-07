# Dokumentacja projektu

Dokumenty są ułożone według zadania, które ma wykonać administrator. Nie trzeba
czytać ich wszystkich po kolei.

## Nawigacja

| Potrzeba | Dokument |
|---|---|
| Instalacja dwóch resolverów na czystym Debianie 13 | [`FRESH-DEBIAN-13.md`](FRESH-DEBIAN-13.md) |
| Pełna konfiguracja BIND, TLS, DoT, DoH, RPZ i Fail2Ban | [`INSTALL.md`](INSTALL.md) |
| Skrócone wdrożenie obu stref RPZ | [`DEPLOYMENT.md`](DEPLOYMENT.md) |
| Diagnostyka obciążenia i zwiększanie limitów | [`DIAGNOSTICS-CAPACITY.md`](DIAGNOSTICS-CAPACITY.md) |
| Zgodność klientów, w tym starszy MikroTik | [`CLIENT-COMPATIBILITY.md`](CLIENT-COMPATIBILITY.md) |
| Historia migracji hazardu, IDN i rollback | [`HAZARD-RPZ-MIGRATION.md`](HAZARD-RPZ-MIGRATION.md) |
| Stan produkcji i kryteria zamknięcia projektu | [`PROJECT-STATUS.md`](PROJECT-STATUS.md) |

## Kolejność dla nowego wdrożenia

1. Wykonaj `FRESH-DEBIAN-13.md`.
2. Korzystaj z `INSTALL.md` przy konfigurowaniu kolejnych komponentów.
3. Sprawdź ograniczenia urządzeń w `CLIENT-COMPATIBILITY.md` przed przekazaniem
   klientowi adresów DoT lub DoH.
4. Wykonaj odbiór opisany w `PROJECT-STATUS.md`.
5. Podczas eksploatacji używaj `DIAGNOSTICS-CAPACITY.md`.

## Co jest źródłem konfiguracji

- `bind/` zawiera szablony RPZ primary i secondary używane przez instalator;
- `scripts/` oraz `systemd/` zawierają pliki instalowane na dns1/dns2;
- `servers/` jest zanonimizowanym snapshotem produkcji, a nie katalogiem do
  bezpośredniego skopiowania na inny serwer;
- `installer/inventory.env.example` jest publicznym przykładem; właściwy
  `inventory.env` pozostaje poza Git;
- feedy RPZ, certyfikaty i sekrety nigdy nie są częścią repozytorium.

Jeżeli krótki dokument wdrożeniowy różni się od pełnej instrukcji, źródłem
prawdy jest `INSTALL.md`, a stan faktycznie przyjętej produkcji opisuje
`PROJECT-STATUS.md`.
