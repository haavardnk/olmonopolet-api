#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

if [ -f "$PROJECT_DIR/.env" ]; then
    export $(grep -v '^#' "$PROJECT_DIR/.env" | xargs)
else
    echo "Error: .env file not found in $PROJECT_DIR"
    exit 1
fi

DB_HOST="${DATABASE_HOST:-127.0.0.1}"
DB_PORT="${DATABASE_PORT:-5432}"
DB_NAME="${DATABASE_NAME:-beerdb}"
DB_USER="${DATABASE_USERNAME:-beer}"
DB_PASSWORD="${DATABASE_PASSWORD}"

BACKUP_DIR="${BACKUP_DIR:-$PROJECT_DIR/backups}"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BACKUP_FILE="$BACKUP_DIR/${DB_NAME}_backup_$TIMESTAMP.sql.gz"
FULL_BACKUP_FILE="$BACKUP_DIR/full_backup_$TIMESTAMP.sql.gz"

mkdir -p "$BACKUP_DIR"

echo "Starting database backup..."
echo "Host: $DB_HOST:$DB_PORT"
echo "Database: $DB_NAME"
echo "User: $DB_USER"
echo ""

export PGPASSWORD="$DB_PASSWORD"

echo "Creating full cluster backup (with roles)..."
pg_dumpall -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" | gzip > "$FULL_BACKUP_FILE"
FULL_SIZE=$(ls -lh "$FULL_BACKUP_FILE" | awk '{print $5}')
echo "Full backup: $FULL_BACKUP_FILE ($FULL_SIZE)"

echo "Creating single database backup..."
pg_dump -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" | gzip > "$BACKUP_FILE"
DB_SIZE=$(ls -lh "$BACKUP_FILE" | awk '{print $5}')
echo "Database backup: $BACKUP_FILE ($DB_SIZE)"

unset PGPASSWORD

echo ""
echo "Backup completed successfully!"
