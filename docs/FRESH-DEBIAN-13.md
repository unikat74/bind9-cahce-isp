# Czysty Debian 13 dostępny tylko przez SSH

Ten runbook zaczyna się od serwera, na którym działa wyłącznie Debian 13 i
SSH. Nie zakłada działającego BIND, firewalla ani certyfikatów. Wykonuj jeden
etap naraz. Po każdym punkcie kontrolnym zostaw otwartą bieżącą sesję SSH i
otwórz drugą sesję testową.

Przykłady używają adresów dokumentacyjnych. Wpisz własne wartości.

## 0. Przygotuj dane przed logowaniem

Potrzebujesz:

```text
ROLE=dns1                         # dns1 albo dns2
FQDN=dns1.example.net
IPV4=198.51.100.10
PREFIX4=25
GATEWAY4=198.51.100.1
IPV6=2001:db8:100:1::2
PREFIX6=64
GATEWAY6=2001:db8:100:1::1
INTERFACE=ens18
ADMIN_IP=203.0.113.190
CLIENT_NET4=198.51.96.0/21
CLIENT_NET6=2001:db8:100::/48
```

Upewnij się, że masz konsolę VM/IPMI jako awaryjny dostęp. Zmiana sieci lub
firewalla wyłącznie przez SSH może odciąć serwer.

## 1. Pierwsze logowanie i inwentaryzacja

Z komputera administratora:

```sh
ssh root@198.51.100.10
```

Na serwerze wykonaj tylko odczyt:

```sh
cat /etc/os-release
uname -a
hostnamectl
ip -br link
ip -br address
ip route
ip -6 route
cat /etc/network/interfaces
timedatectl status
ss -lntup
df -h
free -h
```

Punkt kontrolny: system ma być Debianem 13, interfejs i brama muszą zgadzać
się z danymi operatora, a SSH powinien nasłuchiwać na TCP 22.

## 2. Aktualizacja systemu i narzędzia administracyjne

```sh
apt update
apt full-upgrade -y
apt install -y sudo vim curl ca-certificates git tmux jq dnsutils chrony python3-idna
systemctl enable --now chrony
timedatectl set-timezone Europe/Warsaw
timedatectl status
```

Sprawdź, czy wymagany jest restart:

```sh
test -f /var/run/reboot-required && cat /var/run/reboot-required || true
```

Jeżeli jest wymagany, uruchom `reboot`, poczekaj i zaloguj się ponownie.

## 3. Nazwa serwera

Dla dns1:

```sh
hostnamectl set-hostname dns1.example.net
```

W `/etc/hosts` pozostaw localhost i dodaj adres serwera:

```text
127.0.0.1       localhost
127.0.1.1       dns1.example.net dns1
198.51.100.10   dns1.example.net dns1
```

Sprawdź:

```sh
hostname
hostname -f
getent hosts dns1.example.net
```

## 4. Konto administracyjne i zabezpieczenie SSH

Najpierw utwórz drugie konto. Nie wyłączaj logowania root, dopóki nie
potwierdzisz dostępu z nowego konta.

```sh
adduser dnsadmin
usermod -aG sudo dnsadmin
install -d -o dnsadmin -g dnsadmin -m 700 /home/dnsadmin/.ssh
```

Z komputera administratora, w nowym terminalu:

```sh
ssh-copy-id dnsadmin@198.51.100.10
ssh dnsadmin@198.51.100.10
sudo -v
```

Dopiero po udanym teście utwórz `/etc/ssh/sshd_config.d/10-hardening.conf`:

```text
PermitRootLogin prohibit-password
PasswordAuthentication no
KbdInteractiveAuthentication no
PubkeyAuthentication yes
MaxAuthTries 4
```

Walidacja i bezpieczne przeładowanie:

```sh
sshd -t
systemctl reload ssh
```

Nie zamykaj starej sesji. Otwórz kolejną sesję kluczem i sprawdź `sudo`.

## 5. Statyczna sieć

Najpierw ustal mechanizm zarządzania siecią:

```sh
systemctl is-active networking || true
systemctl is-active systemd-networkd || true
ls -la /etc/network/interfaces.d/
```

Dla `ifupdown` przykładowe `/etc/network/interfaces` dns1:

```ini
source /etc/network/interfaces.d/*

auto lo
iface lo inet loopback

allow-hotplug ens18
iface ens18 inet static
    address 198.51.100.10/25
    gateway 198.51.100.1

iface ens18 inet6 static
    address 2001:db8:100:1::2/64
    gateway 2001:db8:100:1::1
```

Nie wykonuj `ifdown ens18` w sesji SSH. Zweryfikuj składnię, a zmianę aktywuj
restartem mając otwartą konsolę VM. Po restarcie:

```sh
ip -br address show dev ens18
ip route
ip -6 route
ping -c 3 1.1.1.1
ping -6 -c 3 2606:4700:4700::1111
```

## 6. Instalacja usług DNS i ochrony

```sh
apt install -y bind9 bind9-utils certbot fail2ban nftables tcpdump
systemctl enable --now named
systemctl enable --now fail2ban
named -v
named-checkconf
systemctl status named --no-pager
```

Zapisz kopię fabrycznej konfiguracji:

```sh
cp -a /etc/bind /root/bind-before-isp
```

## 7. Pobranie projektu

```sh
install -d -o root -g root -m 755 /opt/bind9-cache-isp
git clone https://github.com/unikat74/bind9-cahce-isp.git /opt/bind9-cache-isp/source
cd /opt/bind9-cache-isp/source
git log -1 --oneline
```

Katalog `servers/` jest zanonimizowanym przykładem, nie konfiguracją do
bezmyślnego skopiowania. Przed użyciem zmień domeny, IP, prefiksy klientów i
interfejsy.

## 8. Bazowy BIND

Otwórz `docs/INSTALL.md` i wykonaj kolejno rozdziały:

1. `Bazowy resolver/cache`;
2. `Let's Encrypt od początku do końca`;
3. `DoT i DoH`;
4. `Logi`.

Po każdym pliku konfiguracyjnym:

```sh
named-checkconf
```

Po zakończeniu etapu:

```sh
systemctl reload named
dig @127.0.0.1 google.com A
ss -lntup | grep -E ':(53|443|853)\b'
```

Nie kontynuuj, jeżeli klasyczny DNS na localhost nie zwraca `NOERROR` i `ra`.

## 9. Certyfikat, DoT i DoH

Przed Certbotem sprawdź rekordy A/AAAA i TCP 80. Następnie użyj dokładnych
poleceń z `docs/INSTALL.md`. Po instalacji wymagane są cztery testy:

```sh
dig -4 @dns1.example.net google.com A +tls +tls-ca +tls-hostname=dns1.example.net
dig -6 @dns1.example.net google.com A +tls +tls-ca +tls-hostname=dns1.example.net
dig -4 @dns1.example.net google.com A +https +tls-ca +tls-hostname=dns1.example.net
dig -6 @dns1.example.net google.com A +https +tls-ca +tls-hostname=dns1.example.net
```

Przed przekazaniem danych klientowi sprawdź tabelę zgodności w
`docs/CLIENT-COMPATIBILITY.md`. W szczególności nie deklaruj bezpośredniego DoH
z BIND-em jako wspieranego dla RouterOS 6.49.x.

## 10. ThreatFox, hazard i para dns1/dns2

Najpierw uruchom instalator obu RPZ w roli primary na dns1. Potwierdź
`rndc zonestatus` dla ThreatFox i hazardu, a dopiero potem uruchom instalator w
roli secondary na dns2. TSIG przenoś wyłącznie z potwierdzonymi odciskami SSH
obu serwerów. Dokładna kolejność znajduje się w rozdziałach 8–10
`docs/INSTALL.md`.

Po stronie dns2 oczekuj:

```text
Transfer status: success
TSIG threatfox-rpz-xfr
```

Zostaw `policy disabled log yes` dla ThreatFox przez okres obserwacji. Rejestr
hazardowy używa `policy given` i aktywnie zwraca adres przekierowania lub
NXDOMAIN zgodnie z regułami strefy.

## 11. Firewall — wdrażanie bez utraty SSH

Przed włączeniem polityki `drop` zawsze najpierw dodaj regułę zezwalającą na
SSH z `ADMIN_IP`. W osobnej sesji uruchom `tmux`, zastosuj reguły i natychmiast
sprawdź nowe połączenie SSH. Nie zapisuj niedziałającego rulesetu jako
trwałego.

Minimalne usługi przychodzące:

- TCP 22 wyłącznie z adresów administracyjnych;
- UDP/TCP 53 z sieci klientów i pomiędzy DNS-ami;
- TCP 443 i 853 z sieci klientów;
- TCP 80 podczas wydawania/odnawiania certyfikatu standalone.

## 12. Odbiór końcowy

```sh
named-checkconf
rndc status
rndc zonestatus rpz.threatfox.abuse.ch
rndc zonestatus rpz.hazard.mf.gov.pl
systemctl --failed
systemctl status named fail2ban chrony --no-pager
timedatectl status
free -h
df -h
ps -C named -o pid,%cpu,%mem,rss,vsz,cmd
fail2ban-client status
nft list ruleset
/usr/local/sbin/check-bind-capacity
```

Z innego hosta sprawdź klasyczny DNS, DoT, DoH oraz odmowę rekurencji dla IP
spoza ACL. Dopiero po tym serwer jest gotowy do wpisania klientom jako DNS.
Progi alarmowe i strojenie limitów opisuje `docs/DIAGNOSTICS-CAPACITY.md`.
