#!/bin/bash
# Moderation console. It is not on the internet: this opens an SSH tunnel with your key and the page in the browser.
# Close this window (or press Ctrl+C) to close the tunnel.
set -euo pipefail
KEY="$HOME/.ssh/egematch_vps"
HOST="root@95.163.231.156"
PORT=8090
if lsof -iTCP:$PORT -sTCP:LISTEN >/dev/null 2>&1; then
  echo "Порт $PORT уже занят — возможно, туннель уже открыт. Открываю страницу."
  open "http://127.0.0.1:$PORT/"
  exit 0
fi
echo "Открываю туннель к модерации… (Ctrl+C — закрыть)"
ssh -i "$KEY" -o ExitOnForwardFailure=yes -o ServerAliveInterval=30 -N -L 127.0.0.1:$PORT:127.0.0.1:$PORT "$HOST" &
TUNNEL=$!
trap 'kill $TUNNEL 2>/dev/null' EXIT
sleep 2
open "http://127.0.0.1:$PORT/"
wait $TUNNEL
