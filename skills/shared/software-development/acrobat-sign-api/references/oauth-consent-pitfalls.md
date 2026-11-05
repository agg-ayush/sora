# Acrobat Sign OAuth consent pitfalls

- `invalid_request` before login usually means a config mismatch. Check that the redirect URI matches the app exactly, including scheme. Apps configured in Acrobat Sign settings only accept `https://` redirects, so `http://localhost...` fails even when the host and path match. Diff the scheme first, then check scopes or the shard.
- `access_denied` with "Only account admins can approve account scopes" means the client ID is valid and registered. Only the scope level is blocked. Retry with `:self` scopes to get a working token right away.
- The app's configured scope level is a ceiling. Each consent picks a level within it. A `:self` consent does not narrow the app, so a later `:account` consent on the same app still works.
- The token acts as whoever logs in during consent. If an admin consents with `:account` scopes, the automation acts as that admin and gets attributed to them in the audit trail. For a service-user integration, give the service user the right to approve account scopes (account admin or the minimum equivalent) and run the consent as the service user.
- `:self` sees only agreements that user sent. To see agreements other users send manually, you need `:account`.
- Admin-created API apps may not show in a non-admin user's API Applications list. That does not mean the app lives in another account. Verify with a consent attempt before claiming it does.
- Delete a fallback app only after the replacement's tokens pass a live API call. Keep at least one working credential at all times.
- Settings > API Applications and Access Tokens are admin-gated features. If the menu or the redirect field is missing, it's a permission issue, not a missing feature.
