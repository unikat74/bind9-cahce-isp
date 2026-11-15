# FUZ — cache 2 GiB, DoQ, DNSCrypt i forwardery IPv6

Wdrożono 15 listopada 2026 kolejno dns2 (109.196.32.252 / 2a0d:6040:0:50::3),
odbiór, następnie dns1 (109.196.32.251 / 2a0d:6040:0:50::2).

## Konfiguracja

- BIND: `max-cache-size 2G` na każdym hoście (limit cache, nie całego procesu).
  Każdy host ma około 3,8 GiB RAM dostępnego dla systemu.
- Forward only: 1.1.1.1, 1.0.0.1, 8.8.8.8, 8.8.4.4,
  2001:4860:4860::8888, 2001:4860:4860::8844.
- Nie dodano Cloudflare IPv6: oba hosty otrzymują network unreachable dla
  2606:4700:4700::1111 i ::1001. Wymaga to oddzielnej diagnozy routingu upstream.
- DoQ UDP/853: dnsdist 2.1.3-1pdns.debian13 z podpisanego repo PowerDNS 2.1.
  Backend BIND 127.0.0.1:5300, PROXYv2 zachowuje adres klienta.
- DNSCrypt UDP/TCP 8443: encrypted-dns-server 0.9.22, archiwum zweryfikowane
  przypiętym SHA256 w instalatorze. Instancja `isp-dnscrypt` na obu hostach,
  provider odpowiednio dns1.fuz.pl / dns2.fuz.pl. Klucze wygenerowane lokalnie.
- DNSCrypt przekazuje do BIND na localhost, więc jego logi RPZ pokazują
  127.0.0.1 zamiast klienta; źródłową ACL egzekwuje nftables przed frontendem.
- Tabele `inet isp_doq` i `inet isp_dnscrypt` mają pełne ACL klientów FUZ,
  w tym 172.17.0.0/16. Dotychczasowe `isp_dns` i bany SSH zachowane.
- Usługi frontendów i firewalli oraz timer kontroli DNSCrypt mają autostart.
- Hook Certbota dnsdist aktualizuje oddzielną kopię TLS; hook BIND zachowany.
- Logowanie i reguły RPZ pozostały bez zmian.

## Odbiór

Dla każdego docelowego serwera z drugiego resolvera wykonano 56 zapytań:
IPv4/IPv6 × DNS UDP, DNS TCP, DoT, DoH, DoQ, DNSCrypt UDP, DNSCrypt TCP ×
cloudflare.com (NOERROR z AD), dnssec-failed.org (SERVFAIL),
advocaat-grimbergen.be (ThreatFox NXDOMAIN),
ws-subscriptions-clob.polymarket.com (antyhazard NXDOMAIN).
DoT/DoH/DoQ z walidacją CA i nazwy serwera. DNSCrypt z przypiętym publicznym
kluczem, klient dnscrypt-proxy z istniejącego środowiska testowego Fione.

Próby DoQ i pobrania certyfikatów DNSCrypt UDP/TCP z dns1 Fione po obu rodzinach
zakończyły się brakiem odpowiedzi; liczniki DROP wzrosły na każdym FUZ:
DoQ od 0 do 2, DNSCrypt od 0 do co najmniej 4.

`certbot renew --dry-run --run-deploy-hooks` zakończył się sukcesem na obu hostach,
łącznie z hookami BIND i dnsdist. Kontrole named-checkconf, nft -c, Fail2Ban,
podpisów certyfikatów DNSCrypt i ich stanu na dysku poprawne. Brak failed units,
dpkg --audit puste. Nie wykonywano restartu systemów.

Na dns1 instalator DNSCrypt odziedziczył umask 077 i utworzył katalog programu
z uprawnieniami 0700. Kontrola wykryła 203/EXEC i wyłączyła frontend.
Naprawiono wyłącznie /opt/isp-dnscrypt na 0755 i odtworzono wygenerowane pliki;
nie kasowano stanu providera. Wszystkie powyższe testy przeszły po naprawie.
Instalatory w repozytorium poprawiono: nowe katalogi programu i konfiguracji
mają jawne 0755 niezależnie od umask, istniejące katalogi zachowują uprawnienia.
Parser preflight akceptuje również `acl klienci_sieci` bez cudzysłowów.

## Klucz API ThreatFox

Tylko dns1: `/etc/threatfox.env`, root:root 0600, zmienna `THREATFOX_AUTH_KEY`.
Podmiana przez edytor na hoście, bez wklejania klucza do czatu, CLI ani Git.
Aktualizator odczytuje plik przy każdym uruchomieniu; nie wymaga restartu BIND.
Po podmianie można uruchomić `systemctl start threatfox-rpz.service` i sprawdzić
`systemctl show threatfox-rpz.service -p Result -p ExecMainStatus`.
Operator następnie podmienił klucz na własny FUZ. Ręczna aktualizacja
zakończyła się Result=success, ExecMainStatus=0; oba hosty załadowały serial
2611151326 (27 461 węzłów). Test NXDOMAIN i wpis RPZ potwierdzono na obu.
Dns2 nie potrzebuje API key.

## Kopie i wycofanie

- dns1: `/root/fuz-extensions-before-lqJ6yJML`, `/root/doq-install-bf_gcvau`,
  `/root/dnscrypt-install-ujzupb_e`.
- dns2: `/root/fuz-extensions-before-XSRb9M7U`, `/root/doq-install-ypr1d58i`,
  `/root/dnscrypt-install-b4i5yn0i`.
- Na obu: `/root/fuz-extensions/`, inventory, instalatory, prepare.py,
  certbot-dry-run.log i backup-path. Skrypty nie są idempotentnymi aktualizatorami.
- Testy: dns1 `/root/fuz-accept-tjwafkb2`, dns2 `/root/fuz-accept-h9_z1_q8`.

Wycofanie pojedynczego hosta: zatrzymać/wyłączyć frontend DNSCrypt i jego timer,
następnie dnsdist, potem ich własne jednostki firewalli. Zachować stan i klucze
DNSCrypt. Usunąć tylko hook dnsdist (zostawić bind-tls), przywrócić
named.conf.options z kopii przed rozszerzeniem, wykonać named-checkconf i rndc reconfig.
Nie przywracać całego starego rulesetu nad aktualnymi banami. Zweryfikować DNS,
DoT/DoH i obie RPZ przed pracą na drugim serwerze.
