# Stan i zamknięcie projektu

## Status

**ZAKOŃCZONY — produkcja odebrana 7 września 2026 roku.**

Zakres podstawowy został wdrożony, przetestowany na dns1 i dns2 oraz opisany.
Nie ma otwartych problemów krytycznych blokujących eksploatację resolverów.

## Zrealizowany zakres

13 września przygotowano rozszerzenie repozytorium o DoQ i DNSCrypt przez
dnsdist. Jego konfigurację i osobny odbiór opisuje `DOQ-DNSCRYPT.md`.
Poniższy zakres i wyniki odnoszą się do odbioru podstawowego z 7 września;
nie potwierdzają wdrożenia nowych protokołów.
DoQ wdrożono na dns2, a następnie dns1 13 września.
`DOQ-DNS2-DEPLOYMENT.md` i `DOQ-DNS1-DEPLOYMENT.md` opisują testy,
ograniczenia odbioru i rollback. Wykonano także testy DoQ między serwerami.
DNSCrypt ma przygotowaną konfigurację
i rotację kluczy, ale pozostaje wyłączony z powodu nieudanego testu TCP na
dnsdist 2.1.2 i 2.0.9. Wyniki: `DOQ-DNSCRYPT-TESTS.md`.

- dwa resolvery/cache BIND 9.20 na Debianie 13;
- rekurencja i cache tylko dla zaufanych sieci IPv4/IPv6;
- klasyczny DNS na UDP/TCP 53;
- DoT na TCP 853 oraz natywny DoH/HTTP/2 na TCP 443;
- certyfikaty Let's Encrypt z automatycznym, walidowanym deploy-hookiem;
- ThreatFox RPZ primary/secondary przez TSIG, w trybie audytu;
- rejestr hazardowy MF jako jedna aktywna RPZ primary/secondary;
- bezpieczne pobieranie, IDNA2008/UTS #46, walidacja i atomowa podmiana stref;
- Fail2Ban/nftables dla DNS, DoT, DoH, DoQ i SSH w IPv4 oraz IPv6
  (jaile DNS: UDP `53,853`, TCP `53,443,853`; detekcja z logów odmowy BIND);
- automatyczne timery ThreatFox, hazardu i Certbota;
- diagnostyka pojemności BIND-a;
- usunięcie starego mechanizmu tysięcy stref hazardowych;
- zanonimizowane snapshoty i instalator dla nowego wdrożenia.

## Wynik ostatniego odbioru

| Kontrola | dns1 | dns2 |
|---|---|---|
| `named-checkconf` | poprawny | poprawny |
| `named.service` | active | active |
| uszkodzone jednostki systemd | 0 | 0 |
| liczba stref BIND | 25 | 25 |
| ThreatFox RPZ | primary, zgodny serial | secondary, zgodny serial |
| Hazard RPZ | primary, zgodny serial | secondary, zgodny serial |
| domena hazardowa | adres przekierowania | adres przekierowania |
| niezdefiniowana subdomena hazardowa | NXDOMAIN | NXDOMAIN |
| DNS/53 | działa | działa |
| DoT/853 z walidacją TLS | działa | działa |
| DoH/443 z walidacją TLS | działa | działa |
| Fail2Ban | 6 jaili | 6 jaili |
| certbot.timer | enabled | enabled |

Na dns1 włączone są także `threatfox-rpz.timer` i `hazard-rpz.timer`. dns2 nie
pobiera feedów samodzielnie — odbiera obie strefy przez transfer TSIG.

## Zaakceptowane ograniczenia

- ThreatFox pozostaje w trybie `policy disabled log yes`: wykrywa IOC, ale nie
  zmienia odpowiedzi DNS.
- RouterOS 6.49.x/TILE nie jest wspierany jako bezpośredni klient natywnego DoH
  BIND-a; korzysta z DNS/53. Szczegóły zawiera `CLIENT-COMPATIBILITY.md`.
- RPZ chroni tylko klientów korzystających z resolverów operatora; nie blokuje
  zewnętrznego DoH ani bezpośrednich połączeń do IP.
- Graficzny monitoring Prometheus/Grafana został świadomie odłożony. Nie jest
  wymagany do zamknięcia bieżącego zakresu. Dostępny jest lekki raport
  `/usr/local/sbin/check-bind-capacity`.
- Niewspierany proxy zgodności HTTP/1.1 dla starych MikroTików nie jest częścią
  instalatora ani produkcji.

## Eksploatacja po zamknięciu

Automatyzacja wykonuje rutynowe aktualizacje, ale administrator powinien
okresowo sprawdzać:

```sh
named-checkconf
rndc status
rndc zonestatus rpz.threatfox.abuse.ch
rndc zonestatus rpz.hazard.mf.gov.pl
systemctl --failed
systemctl list-timers certbot.timer threatfox-rpz.timer hazard-rpz.timer
/usr/local/sbin/check-bind-capacity
```

Na dns2 nie oczekuj timerów RPZ. Sprawdzaj zamiast tego zgodność seriali obu
stref z dns1 oraz status ostatniego transferu.

Chronione archiwa starej konfiguracji pozostają na serwerach:

```text
/root/legacy-hazardbind-20260907.tar.gz
```

Sumy kontrolne i procedurę awaryjną zawiera `HAZARD-RPZ-MIGRATION.md`.

## Kiedy ponownie otworzyć projekt

Projekt należy ponownie otworzyć, jeśli wystąpi przynajmniej jeden z warunków:

- seryjne błędy aktualizacji lub transferu RPZ;
- różne seriale primary i secondary po upływie czasu odświeżania;
- błąd odnowienia lub mniej niż 30 dni ważności certyfikatu;
- trwałe wykorzystanie ponad 80% limitu TCP albo rekursji;
- wzrost `SERVFAIL`, odrzuceń, timeoutów lub kolejek listenerów;
- zmiana formatu API ThreatFox albo rejestru MF;
- zmiana polityki z audytu ThreatFox na aktywne blokowanie;
- dodanie centralnego monitoringu graficznego;
- rozszerzenie macierzy wspieranych klientów DoT/DoH.

Zmiany produkcyjne wykonuj kolejno: jeden resolver, test z punktu widzenia
klienta, następnie drugi. Nie restartuj obu resolverów jednocześnie.

## DNSCrypt na dns2 — 13 września 2026

Osobny encrypted-dns-server 0.9.22 udostępniono klientom z ACL BIND po
UDP/TCP 8443, IPv4/IPv6, z autostartem i DROP pozostałych źródeł.
Fail2Ban na dns2 obejmuje dodatkowo 8443; dns1 nie zmieniono.
BIND widzi klienta jako loopback. Limity i ograniczenia cache, wyniki
odbioru oraz rollback: [DNSCRYPT-DNS2-TEST.md](DNSCRYPT-DNS2-TEST.md).
DNSCrypt w samym dnsdist pozostaje wyłączony na obu hostach.

## DNSCrypt na dns1 — 13 września 2026

Udostępniono także na dns1: UDP/TCP 8443, pełna ACL klientów IPv4/IPv6,
autostart, osobne klucze i rozszerzone bany Fail2Ban. DoQ pozostało w dnsdist.
Testy i ograniczenia: [DNSCRYPT-DNS1-DEPLOYMENT.md](DNSCRYPT-DNS1-DEPLOYMENT.md).
