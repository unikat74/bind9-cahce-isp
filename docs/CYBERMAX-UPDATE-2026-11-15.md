# Cybermax — ujednolicenie resolverów, 15 listopada 2026

Aktualizowano istniejącą parę: dns2 193.192.179.12 / 2001:67c:660::54,
odbiór, potem dns1 193.192.179.11 / 2001:67c:660::53. Bez aktualizacji pakietów,
restartu systemu i restartu BIND. Restartowano wyłącznie dnsdist po zmianie
jego ACL i testu backendu. Własne API key, TSIG, certyfikaty i tożsamości
DNSCrypt zachowane.

## Zmiany

- Nowy wspólny installer/bootstrap-resolver-policy.py zastosowano na obu hostach.
  Profil: installer/profiles/cybermax.toml. Starsze literalne `acl clients`
  migruje do `klienci_sieci`, bez pozostawiania dwóch ACL.
- Cache 1 → 2 GiB, recursive-clients 1500 → 10000, tcp-clients 750 → 1000.
- Zachowano klientów DNS: 193.192.179.0/24, 117.55.198.0/24, 10.0.0.0/20,
  2001:67c:660::/48 i loopback; dodano domowy 188.137.37.190/32 we wszystkich
  warstwach DNS oraz NTP/SSH. Odpowiedź DNS i NTP z domowego źródła potwierdzono;
  RPZ zapisało źródło 188.137.37.190.
- NTP ma osobne zestawy w firewallu, zgodne z dotychczasową ACL chrony;
  nie rozszerzono go o 10.0.0.0/20. Zachowano stare wyjątki SSH dla sieci publicznych.
- SSH IPv4: 5 prób/10min, ban 1h, narastanie ×2 do 7d. Osobny jail IPv6:
  5 prób/60min, ban 1d, narastanie do 7d; rodziny nie naliczają się podwójnie.
- Osobne logi security/RPZ: logrotate daily/maxsize 20M, 7 archiwów,
  compress/delaycompress, kontrola co godzinę. Natywna rotacja BIND wyłączona.
- Lokalna autorytatywna strefa localhost A/AAAA; dnsdist health check localhost A.
  Frontendy zachowały listenery, provider i stan; ich ACL oraz tabele firewalli
  zsynchronizowano z rozszerzoną ACL BIND.
- Hazard miał już harmonogram 06:00/18:00 i osobny TSIG. ThreatFox miał już
  osobny TSIG oraz uwierzytelnione NOTIFY; timer dns1 zmieniono z 05:00 na
  03:17 + losowo do 20min, Europe/Warsaw. Dns2 nie pobiera feedów samodzielnie.
- Zachowano cztery działające forwardery IPv4. Na obu hostach wszystkie
  zapytania do Cloudflare i Google IPv6 zwracały timeout; nie dopisano ich
  do forwarders. Nie oznacza to awarii całego IPv6: IPv6 klientów i NTP działa.

## Odbiór

112 zapytań z drugiego resolvera: IPv4/IPv6 × DNS UDP/TCP, DoT, DoH, DoQ,
DNSCrypt UDP/TCP × NOERROR+AD, błędny DNSSEC SERVFAIL, ThreatFox NXDOMAIN,
antyhazard NXDOMAIN dla subdomeny. TLS z walidacją CA/nazwy; DNSCrypt z
przypiętym dotychczasowym publicznym kluczem.

Pełne transfery obu RPZ poprawne z własnym kluczem, odmowy po zamianie kluczy.
Wymuszona replikacja potwierdzona w logu: hazard serial 1794589206,
ThreatFox 2611150340, podpisy właściwymi TSIG.

NTP: poprawne odpowiedzi IPv4/IPv6 między DNS-ami i IPv4 z domu, stratum 3.
Obce źródło FUZ odrzucone na NTP i portach DNS po obu rodzinach, wzrost DROP.
Chrony po burst 2/2 odbiera świeże próbki upstream i ma Leap status Normal.
Test IPv6 ban → element nftables → unban poprawny; istniejące bany SSH zachowane.
Dwie rzeczywiste rotacje, gzip -t i nowe wpisy security/RPZ po rotacji poprawne.
Usługi aktywne, timery/autostart włączone, brak failed units.

## Kopie i artefakty

| Host | Pełna kopia przed zmianą | Manifest instalatora | Frontendy |
|---|---|---|---|
| dns2 | /root/cybermax-before-Lh8LMXAf | /root/resolver-policy-before-vrtex7sb | /root/cybermax-frontends-before-qh5_39kh |
| dns1 | /root/cybermax-before-VHQoCpQD | /root/resolver-policy-before-h5f4jj9p | /root/cybermax-frontends-before-xx8u54l6 |

Na hostach /root/cybermax-policy zawiera użyty pakiet repozytorium, profil,
frontend.toml (publiczne inventory, bez sekretów) i backup-path.
Testy: dns1 /root/cybermax-accept-vkc8rvft, dns2 /root/cybermax-accept-pr52u84f.
Przy rollbacku odtwarzać konkretne konfiguracje z kopii, nie stan kluczy DNSCrypt
ani całą starą tabelę Fail2Ban. Przywracać tylko własne tabele firewalli;
wyłączyć nowy timer logrotate przed przywróceniem natywnej rotacji. Każdy plik
sprawdzić odpowiednim parserem, zacząć od dns2, a dns1 ruszyć dopiero po odbiorze.
