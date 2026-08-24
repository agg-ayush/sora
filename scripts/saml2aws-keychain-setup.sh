#!/usr/bin/env bash
# One-time: store DevFactory Keycloak password in macOS Keychain for saml2aws.
set -u
SERVICE="saml2aws"
ACCOUNT="ayushaggarwal018@gmail.com"

# nuke any prior (possibly empty) entry
security delete-generic-password -s "$SERVICE" -a "$ACCOUNT" >/dev/null 2>&1

# read without echo, from the real tty
printf "DevFactory password: " > /dev/tty
read -rs PW < /dev/tty
printf "\n" > /dev/tty

if [[ -z "${PW}" ]]; then
  echo "ERROR: empty password, not saved" > /dev/tty
  exit 1
fi

if security add-generic-password -s "$SERVICE" -a "$ACCOUNT" -w "$PW"; then
  echo "KEYCHAIN OK (len=${#PW})" > /dev/tty
else
  echo "KEYCHAIN FAIL" > /dev/tty
  exit 1
fi
unset PW

echo "You can detach now (Ctrl-b d)" > /dev/tty
sleep 600
