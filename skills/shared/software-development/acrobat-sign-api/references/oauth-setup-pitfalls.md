# Acrobat Sign OAuth setup pitfalls

## Consent flow (CLI, no web server)
1. Generate the consent URL with a random `state`, saved 0600 alongside which client/redirect it used.
2. Redirect URI `https://localhost:3000/oauth/callback` (Configure OAuth requires `https://`). The browser lands on a dead page; the user pastes the address-bar URL back.
3. Verify `state`, POST the code to `<api_access_point>/oauth/v2/token` with `grant_type=authorization_code`, client id/secret and the same redirect URI.
4. Store access + refresh token, `expires_at`, `api_access_point`, `web_access_point` in a 0600 JSON file. Verify with one live `GET /api/rest/v6/agreements`.

## "Unable to authorize access because the client configuration is invalid: invalid_request"
Rejected before login. Get the app's saved config first; do not keep generating URL variants blind. Causes, in order of likelihood:
1. **Redirect URI mismatch**, including scheme: `http://` vs `https://` is enough. Ask for the exact saved value.
2. **OAuth never configured on the app.** Creating an API Application only yields the ID and secret; redirect URI and scopes live behind a separate **Configure OAuth for Application** action (select the app row to expose it). No redirect field visible means it was never configured. A non-admin user who can create the app can often configure it too; have the user look before escalating.
3. **App registered in a different account.** Consent only works for apps in the logged-in user's account. Note a non-admin user's API Applications list may not show apps an admin created, so absence from the list is weak evidence; fix the redirect first.
4. Scope level higher than the app allows: retry with `:self`.

## "access_denied: Only account admins can approve account scopes"
The app is fine. The consenting user is not an admin. Use `:self` now; `:account` needs an admin to consent once on the same app.

## Acrobat Sign API Applications vs Adobe Developer Console
Two separate systems that both say "API application". Acrobat Sign REST v6 OAuth uses the Sign account's own API Applications (client IDs start with `ats-`). Once the user confirms which one they mean, stop bringing up the other.

## Direct access tokens
Personal Preferences > Access Tokens is admin-gated and often hidden for service users. Minted tokens don't refresh; OAuth refresh tokens do, so OAuth is the production path.

## Scope levels
The app's configured level is a ceiling; each consent picks a level within it. `:self` covers everything the service user sends. Seeing agreements other users send manually needs `:account`, approved by an account admin.
