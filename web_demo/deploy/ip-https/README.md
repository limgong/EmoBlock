# Public IP HTTPS for the current host-network deployment

Caddy terminates TLS on 443 and proxies to the existing loopback-only app at 127.0.0.1:8765. Port 80 serves HTTP-01 certificate validation and redirects other requests to HTTPS. Certbot 5.8.0 requests Let's Encrypt's shortlived IP certificates; certificate issuance/renewal is separate from Caddy. No global Docker firewall repair is required.

Deploy this folder to `/opt/emoblocks-demo/https`, outside the Git checkout. Keep the `.env`, ACME account keys, certificate private keys and runtime folders on the server only. Do not package or commit those folders.

1. Set `.env` to `DEMO_IP=115.159.215.148` and create `config`, `acme`, and `letsencrypt` directories; restrict `letsencrypt` to mode 0700. Copy `Caddyfile.bootstrap` to `config/Caddyfile`. Open inbound TCP 80/443 in the instance security group. Keep the app bound to loopback.
2. Run `docker compose -p emoblocks-ip-https up -d caddy` and `docker compose -p emoblocks-ip-https --profile certificates build certbot`. Verify an HTTP-01 probe externally before contacting the CA.
3. Validate issuance with the command below, first with `--dry-run`, then without it for a publicly trusted certificate. With no supplied account email, registration uses `--register-unsafely-without-email`; configure an email later if desired. Renewals must be automated.

```sh
docker compose -p emoblocks-ip-https --profile certificates run --rm certbot certonly \
  --non-interactive --agree-tos --register-unsafely-without-email \
  --preferred-profile shortlived --webroot --webroot-path /srv/acme \
  --ip-address 115.159.215.148 --cert-name emoblocks-ip
```

4. Validate `Caddyfile.https` against the real certificate, copy it to `config/Caddyfile`, and reload Caddy. Enable secure session cookies with the existing app's same Compose project and persistent volume:

```sh
docker compose -p emoblocks-demo \
  -f /path/to/current/release/web_demo/deploy/compose.private-host.yaml \
  -f /opt/emoblocks-demo/https/compose.app-secure.yaml up -d --no-build app
docker exec emoblocks-https-proxy caddy reload --force --config /etc/caddy/Caddyfile --adapter caddyfile
```

Use this secure-cookie override on subsequent app deployments. Browser tests should use the public HTTPS URL; existing HTTP SSH tunnels are not the public session endpoint.

5. Install the service/timer into `/etc/systemd/system`, set `renew.sh` executable, run `systemctl daemon-reload`, and enable/start `emoblocks-ip-cert-renew.timer`. The timer checks every six hours with a random delay of up to ten minutes. `renew.sh` serializes runs with flock and only reloads Caddy after Certbot exits successfully; `--force` reloads the manually loaded certificate even when the Caddyfile text is unchanged.
6. Verify `certbot renew --dry-run --cert-name emoblocks-ip`, test one real service invocation, and inspect the next scheduled run. Never deploy a staging or self-signed certificate as a successful public HTTPS result.

Acceptance: externally trusted certificate whose SAN contains the public IP; HTTP redirect; Secure/HttpOnly session cookie; five sample imports; cross-origin and cross-session rejection; candidate generation with real LMMS files; browser WAV decoding/playback; active renewal timer. Public TLS, application correctness and physical listening are separate evidence.

References: [Let's Encrypt IP certificates with Certbot](https://letsencrypt.org/2026/03/11/shorter-certs-certbot), [Certbot renewals](https://eff-certbot.readthedocs.io/en/stable/using.html#renewing-certificates).
