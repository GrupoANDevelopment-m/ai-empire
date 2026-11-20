# TLS certificates

`docker-compose.production.yml` mounts this directory at
`/etc/nginx/certs` inside the nginx container.

Place your certificate and key here before starting the stack:

```
fullchain.pem   # the full certificate chain
privkey.pem     # the private key
```

The repository ships no certificate on purpose — a private key must
never be committed. For a local run, generate a self-signed pair:

```bash
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout observability/nginx/certs/privkey.pem \
  -out observability/nginx/certs/fullchain.pem \
  -subj "/CN=localhost"
```

nginx.conf expects exactly these two file names.
