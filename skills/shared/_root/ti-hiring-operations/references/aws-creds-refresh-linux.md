# AWS creds refresh on the Linux box

`hermes-tier-setup/scripts/aws-creds-refresh.sh` is the macOS variant (Keychain `security` CLI) and always fails on Linux ("Empty password").

Use the Linux sister script instead:

```
bash /home/ubuntu/hermes-tier-setup/scripts/aws-creds-refresh-linux.sh [--force]
```

It reads the password from `~/.config/saml2aws/.trilogy-password` and drives saml2aws through a tmux session, then mirrors `[trilogy]` -> `[default]` in `~/.aws/credentials`.

If it still fails, drive the prompt manually:

```
tmux new-session -d -s saml2aws-tty 'saml2aws login -a trilogy --force'
tmux send-keys -t saml2aws-tty Enter   # accept saved username
# then inspect with: tmux capture-pane -t saml2aws-tty -p
```
