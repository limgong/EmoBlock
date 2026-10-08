#!/bin/sh
set -eu
cd /opt/emoblocks-demo/https
exec 9>/run/emoblocks-ip-cert-renew.lock
flock -n 9 || exit 0
docker compose -p emoblocks-ip-https --profile certificates run --rm certbot renew --non-interactive --quiet --no-random-sleep-on-renew
docker exec emoblocks-https-proxy caddy reload --force --config /etc/caddy/Caddyfile --adapter caddyfile
