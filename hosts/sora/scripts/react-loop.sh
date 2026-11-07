#!/bin/bash
# Poll the signup message reactions and serve any unserved thumbs-up reactor.
while true; do
  python3 "$HOME/.hermes/scripts/react-watcher.py" >> /tmp/react-watcher.log 2>&1
  sleep 60
done
