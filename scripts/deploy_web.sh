#!/bin/bash
# Publishes web/ to the Moscow server: the site is served from there (docs/server.md), not from Vercel.
# Run after the build scripts and tests: ./scripts/deploy_web.sh
set -euo pipefail
cd "$(dirname "$0")/.."
KEY="$HOME/.ssh/egematch_vps"
HOST="root@95.163.231.156"
rsync -a --delete -e "ssh -i $KEY" --exclude README.md --exclude export_catalog.py --exclude vercel.json web/ "$HOST:/var/www/egematch/"
ssh -i "$KEY" "$HOST" 'chmod -R a+rX /var/www/egematch'
echo "Готово: сайт обновлён на сервере."
