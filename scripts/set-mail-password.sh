#!/bin/bash
# Puts the password of info@egematch.ru into the review service on the server, without showing it anywhere:
# it is read silently here and written straight into /etc/egematch/reviews-public.env (readable by root and the service).
set -euo pipefail
KEY="$HOME/.ssh/egematch_vps"
HOST="root@95.163.231.156"
read -r -s -p "Пароль от почты info@egematch.ru (ввод не отображается): " PASSWORD
echo
if [ -z "$PASSWORD" ]; then echo "Пустой пароль — ничего не меняю."; exit 1; fi
printf '%s' "$PASSWORD" | ssh -i "$KEY" "$HOST" 'set -e
  NEW=$(cat)
  FILE=/etc/egematch/reviews-public.env
  grep -v "^REVIEWS_SMTP_PASSWORD=" "$FILE" > "$FILE.tmp" || true
  printf "REVIEWS_SMTP_PASSWORD=%s\n" "$NEW" >> "$FILE.tmp"
  install -m 640 -o root -g egematch "$FILE.tmp" "$FILE" && rm -f "$FILE.tmp"
  systemctl restart egematch-reviews-public
  echo "Готово: пароль сохранён на сервере, сервис перезапущен."'
unset PASSWORD
