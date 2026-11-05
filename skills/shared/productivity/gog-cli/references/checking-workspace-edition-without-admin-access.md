# Checking Google Workspace edition/tier when you have no admin access

`gog admin` only exposes `users`/`groups`/`orgunits` — there is no
`customer`/`edition` subcommand, and even those require domain-wide
delegation (admin.directory scopes) that most personal OAuth grants don't
have (`Insufficient permissions for Admin SDK API` is the tell). Hitting the
Admin SDK REST API directly with a token pulled via `gog ... auth token`
also fails for the same reason (401 Invalid Credentials — the token isn't
scoped for Admin SDK). If the user doesn't have Google Admin console access
either (`admin.google.com` needs an actual admin role, not just any
Workspace account), there's no API/console path.

**Working non-admin proxy: Workspace storage quota maps 1:1 to plan tier.**

- 30 GB pooled → Business Starter
- 2 TB per user → Business Standard
- 5 TB per user (or "unlimited"/"as much as you need") → Business Plus or
  Enterprise (these two aren't distinguishable by quota alone — if the
  distinction matters, that residual ambiguity has to be resolved by asking
  IT/an actual admin, not guessed)

Have the user check it themselves — this isn't something `gog`/API tooling
can read for a non-admin account:

- `mail.google.com` → gear icon (top right) → **See all settings** →
  General tab → **Storage**
- or the storage usage bar at the bottom-left of `drive.google.com`

This narrows down edition without needing admin rights, even though it
can't fully distinguish Business Plus from Enterprise.
