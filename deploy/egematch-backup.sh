#!/bin/bash
# Nightly database backup (root, from cron). Keeps 14 days and tells the console how fresh the last one is.
set -euo pipefail
DIR=/var/backups/egematch
mkdir -p "$DIR" && chmod 700 "$DIR"
FILE="$DIR/db-$(date +%Y%m%d-%H%M).dump"
sudo -u postgres pg_dump -Fc postgres > "$FILE"
find "$DIR" -name 'db-*.dump' -mtime +14 -delete
SIZE=$(( $(stat -c %s "$FILE") / 1048576 ))
install -d -m 750 -o root -g egematch /var/lib/egematch
printf '{"at": "%s", "file": "%s", "size_mb": %s}\n' "$(date -u +%Y-%m-%dT%H:%M:%S+00:00)" "$(basename "$FILE")" "$SIZE" > /var/lib/egematch/backup-status.json
chgrp egematch /var/lib/egematch/backup-status.json && chmod 640 /var/lib/egematch/backup-status.json
