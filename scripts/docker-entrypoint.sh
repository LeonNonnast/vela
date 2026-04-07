#!/bin/bash
set -e

echo "Vela Docker Entrypoint" >&2
echo "======================" >&2

# Wait for database to be ready
if [[ "$DATABASE_URL" == mysql* ]]; then
  DB_HOST=$(echo "$DATABASE_URL" | sed -n 's/.*@\([^:]*\).*/\1/p')
  DB_PORT=$(echo "$DATABASE_URL" | sed -n 's/.*:\([0-9]*\)\/.*/\1/p')

  until nc -z "$DB_HOST" "$DB_PORT" 2>/dev/null; do
    echo "Waiting for database at $DB_HOST:$DB_PORT..." >&2
    sleep 2
  done
  echo "Database ready" >&2
fi

# Run Alembic migrations (if versions exist)
if ls alembic/versions/*.py 1>/dev/null 2>&1; then
  echo "Running migrations..." >&2
  alembic upgrade head 2>&1 >&2
  echo "Migrations done" >&2
fi

# Ensure tables exist and seed (seed_db.py uses create_all)
echo "Ensuring database schema..." >&2
uv run python scripts/seed_db.py 2>&1 >&2
echo "Database ready" >&2

# Start the application
exec "$@"
