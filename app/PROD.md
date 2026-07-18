## Production (Docker Compose)

The production stack runs two services:

- `db` — Postgres 16 with a named volume `pgdata`
- `web` — Flask app behind Gunicorn (port `127.0.0.1:8000`)

Always pass `--env-file .env.production` so Compose can interpolate `${POSTGRES_PASSWORD}` in `docker-compose.yml`. The `web.env_file` alone does **not** do that.

### First-time setup

```bash
cp .env.example .env.production
# Edit .env.production with real secrets.
# POSTGRES_PASSWORD must be URI-safe (letters, numbers, - _). Avoid @ : / # ? &.

docker compose --env-file .env.production config   # validate config
docker compose --env-file .env.production up --build -d
```

On startup, `app/entrypoint.sh` runs `flask db upgrade`, then starts Gunicorn.

### Everyday service commands

```bash
# Start / rebuild / stop
docker compose --env-file .env.production up --build -d
docker compose --env-file .env.production stop
docker compose --env-file .env.production start
docker compose --env-file .env.production down          # stop & remove containers (keeps pgdata)
docker compose --env-file .env.production restart web
docker compose --env-file .env.production restart db

# Status & logs
docker compose --env-file .env.production ps
docker compose --env-file .env.production logs -f
docker compose --env-file .env.production logs -f web
docker compose --env-file .env.production logs -f db

# Shell into containers
docker compose --env-file .env.production exec web sh
docker compose --env-file .env.production exec db psql -U gohitha -d carnaticidx
```

### Health checks & smoke tests

```bash
docker compose --env-file .env.production ps
curl -I http://127.0.0.1:8000/
curl -u "$ADMIN_USERNAME:$ADMIN_PASSWORD" -I http://127.0.0.1:8000/review/

# Alembic / extension checks
docker compose --env-file .env.production exec web flask db current
docker compose --env-file .env.production exec db \
  psql -U gohitha -d carnaticidx -c "\dx"
```

The web healthcheck hits `GET /` every 10s with `curl` (expected in access logs).

### Volumes

Postgres data lives in the Docker named volume `pgdata`, not in your local Homebrew Postgres.

```bash
docker volume ls | grep pgdata
docker volume inspect carnaticidx_pgdata

# Wipe Docker DB data (destructive — does not touch local Postgres)
docker compose --env-file .env.production down -v
```

`down` keeps the volume. `down -v` deletes it.

### Preload / backup / restore

**Dump from local Postgres (laptop):**

```bash
pg_dump -U gohitha -d carnaticidx -f backup.sql
```

**Restore into Docker Postgres** — use a **fresh** empty volume. Do **not** restore a full schema dump on top of a DB that already ran migrations (you will get “already exists” / FK errors).

```bash
# Clean slate inside Docker only
docker compose --env-file .env.production down -v
docker compose --env-file .env.production up -d db

# Wait until healthy, then restore schema + data
docker compose --env-file .env.production exec -T db \
  psql -v ON_ERROR_STOP=1 -U gohitha -d carnaticidx < backup.sql

# Start web (migrations should be a no-op if alembic_version matches)
docker compose --env-file .env.production up --build -d web
```

**Backup from Docker Postgres:**

```bash
docker compose --env-file .env.production exec -T db \
  pg_dump -U gohitha -d carnaticidx > backup-docker.sql
```

**Verify row counts:**

```bash
docker compose --env-file .env.production exec db \
  psql -U gohitha -d carnaticidx \
  -c "SELECT COUNT(*) FROM concerts;" \
  -c "SELECT COUNT(*) FROM pieces;" \
  -c "SELECT version_num FROM alembic_version;"
```

### Temporary DB access for laptop ingest (optional)

Postgres is **not** published by default. For a one-off import from your laptop only, temporarily add to the `db` service:

```yaml
ports:
  - "127.0.0.1:5432:5432"
```

Then point a local client at `127.0.0.1:5432` (or use an SSH tunnel on a VPS). Remove the port mapping afterward — never leave Postgres public on a VPS.

### Gunicorn (inside `web`)

Gunicorn is started by the container entrypoint:

```text
flask db upgrade
exec gunicorn -c gunicorn.conf.py "app:app"
```

Config: [`app/gunicorn.conf.py`](app/gunicorn.conf.py)

| Setting | Source |
|---------|--------|
| Bind | `0.0.0.0:${PORT:-8000}` |
| Workers | `WEB_CONCURRENCY` (default: `max(2, cpu_count())`) |
| Threads | `4` (`gthread`) |
| Timeout | `60s` |

```bash
# Follow Gunicorn access/error logs (stdout/stderr)
docker compose --env-file .env.production logs -f web

# Restart Gunicorn (recreates web container → re-runs migrations, then Gunicorn)
docker compose --env-file .env.production restart web

# Change worker count: edit WEB_CONCURRENCY in .env.production, then
docker compose --env-file .env.production up -d --force-recreate web
```

App is available at `http://127.0.0.1:8000/` (intended to sit behind Caddy or another reverse proxy on the host).

## Local development (without Docker)

From `app/` with a virtualenv and local Postgres:

```bash
cd app
# configure app/.env (DATABASE_URI, etc.)
flask run
# or
gunicorn -c gunicorn.conf.py "app:app"
```

`app/.env` is for local runs. `.env.production` (repo root) is for Docker Compose. Keep both out of git.
