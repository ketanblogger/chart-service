#!/usr/bin/env bash
# Nightly backup of what cannot be recreated: var/app.db (orders, balances, consultations, rashifal content) and
# var/reports (the reports customers paid for). var/pdfs is a cache and is skipped.
#   sudo -u astro crontab -e   ->   17 2 * * * /srv/astrology/deploy/backup.sh >> /srv/astrology/var/backup.log 2>&1
# Keeps 14 days locally in /srv/astrology/var/backups. COPY THEM OFF THE SERVER as well (last line): a VPS disk is one disk.
set -euo pipefail
APP=/srv/astrology
DEST="$APP/var/backups"
STAMP=$(date +%Y%m%d-%H%M)
mkdir -p "$DEST"
# .backup takes a consistent snapshot while the app keeps writing (never cp a live SQLite file)
sqlite3 "$APP/var/app.db" ".backup '$DEST/app-$STAMP.db'"
gzip -f "$DEST/app-$STAMP.db"
tar -czf "$DEST/reports-$STAMP.tar.gz" -C "$APP/var" reports 2>/dev/null || true
find "$DEST" -type f -mtime +14 -delete
echo "$(date -Is) backup ok: $(ls -1 "$DEST" | wc -l) files, $(du -sh "$DEST" | cut -f1)"
# Offsite (pick one and uncomment): rclone copy "$DEST" remote:astrology-backups   |   rsync -a "$DEST/" user@other-host:astrology-backups/
