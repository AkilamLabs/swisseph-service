# Security policy

## Supported versions

Only the latest release (`ghcr.io/akilamlabs/swisseph-service:latest` and the
newest `vX.Y.Z` tag) receives fixes.

## Reporting a vulnerability

Please do **not** open a public issue. Report privately through GitHub's
[private vulnerability reporting](https://github.com/AkilamLabs/swisseph-service/security/advisories/new)
or by email to **support@astroyogam.in**. You should hear back within 7 days.

## Deployment notes

- The service is designed for a private network next to its consumer
  (localhost or an internal Docker network). Do not expose it to the internet.
- If it must be reachable beyond that network, set `SERVICE_TOKEN`; every
  route except `/v1/health` then requires a matching `X-Service-Token` header
  (compared in constant time).
