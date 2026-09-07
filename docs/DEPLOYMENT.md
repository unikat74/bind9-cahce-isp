# Wdrożenie ThreatFox RPZ

1. Na `dns1` zapisz klucz w `/etc/threatfox.env` (`root:root`, `0600`).
2. Zainstaluj skrypt i jednostki systemd z tego repozytorium.
3. Umieść TSIG w `/etc/bind/keys/threatfox-rpz-xfr.key` na obu serwerach
   (`root:bind`, `0640`).
4. Wstaw rzeczywiste IP zamiast `DNS1_IPV4` / `DNS2_IPV4`.
5. Dołącz `named.conf.rpz` w `named.conf.local`, a `named.conf.rpz-options`
   wewnątrz bloku `options`.
6. Dodaj `category rpz { security_file; };` w bloku `logging`.
7. Zweryfikuj: `named-checkconf`, potem `systemctl reload named`.

## Test

```sh
dig @127.0.0.1 qaqfaxian.com A
tail -f /var/log/named/security.log | grep --line-buffered 'disabled rpz'
rndc zonestatus rpz.threatfox.abuse.ch
```

