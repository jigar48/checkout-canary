# Stores behind bot protection (Cloudflare and similar)

checkout-canary is a bot that visits your store. Many stores sit behind a service that challenges
bots, so a monitor can get an HTTP 403 and a page like "Performing security verification" instead of
the shop. **checkout-canary does not try to get around bot protection, CAPTCHAs or challenges.** If
you own the store and want the monitor to be allowed, you add an allow rule on the protection side and
let the monitor identify itself. This page describes the two settings that support that.

Only use this on stores you own or have written permission to test.

## Settings (environment variables only)

| Variable | Purpose |
| --- | --- |
| `CHECKOUT_CANARY_USER_AGENT` | Replaces the default User-Agent (`checkout-canary/<version> (+https://github.com/jigar48/checkout-canary)`). 1-300 printable ASCII characters. Example: `checkout-canary (Krisvik monitoring)`. |
| `CHECKOUT_CANARY_HEADER_NAME` | Name of one extra request header, for example `X-Monitor-Token`. Letters, digits and `-` only. Reserved names (`Host`, `Cookie`, `Authorization`, `User-Agent`, ...) are refused. |
| `CHECKOUT_CANARY_HEADER_VALUE` | Value of that header. **A secret**: keep it in an environment variable or in GitHub Actions secrets, never in a file in a repository. 1-512 printable ASCII characters. |

Set both header variables or neither. Invalid values make the run exit with code 2 before any request
is sent, and the error message never contains the value.

```bash
export CHECKOUT_CANARY_HEADER_NAME="X-Monitor-Token"
export CHECKOUT_CANARY_HEADER_VALUE="<long random string>"   # never commit this
checkout-canary run my-store.yml
```

## What the tool does with the secret header

- It is sent only to the journey's own origins: the origin of `base_url` plus the origin of any
  absolute `goto` URL. Third-party requests (analytics, fonts, ads) never receive it.
- It is not printed (the console only says that a header is enabled and shows its name), not written
  to `result.json`, not put in alerts or on the status page, and it is redacted from step error
  messages.
- It does not appear in the Playwright trace or the screenshots. This was checked by scanning a real
  `trace.zip` produced against a local server that demands the header (the trace records the browser's
  own request headers, and the header is added outside the browser), and a test repeats that scan on
  every CI run. This depends on how Playwright records traces, so if you upgrade Playwright and the
  test fails, do not publish traces until it is fixed.
- Service workers are blocked while the header is enabled, so every request goes through the same path.

### Limits you should know

- **Redirects.** Playwright's documented `route.continue_(headers=...)` also applies the header to
  redirects, and in testing a cross-origin redirect received the secret. The tool therefore sends
  matching requests with `route.fetch(max_redirects=0)` and hands the response to the browser. The
  consequence: when the server answers with a redirect, the browser follows it **without** the header.
  The console then prints a note. Use the final URL in your journey (for example `/checkout/cart/` with
  the trailing slash) so no redirect happens. If your protection rule needs the header on redirect
  targets too, this approach will not satisfy it.
- All requests to your own origin are fetched by Playwright's request client and then given to the
  browser, so this mode is slower and the TLS fingerprint of those requests is Playwright's, not
  Chromium's. An allow rule that matches the secret header does not care, but a rule that relies on
  browser fingerprints would.
- Not tested against a real Cloudflare site yet; only against local servers.

## Cloudflare: the matching allow rule

The site owner creates a custom rule with the **Skip** action that matches the secret header
([docs](https://developers.cloudflare.com/waf/custom-rules/skip/)). Typical expression, with your own
header name and value:

```text
(http.request.headers["x-monitor-token"][0] eq "<the same secret value>")
```

and skip the security features that block the monitor (rate limiting rules, Managed Rules, Super Bot
Fight Mode rules, and so on; see "Available skip options" in the same documentation page).

**Important limit from Cloudflare's documentation:** a Skip rule cannot skip **Bot Fight Mode**
(the one available on the Free plan). If the store uses Bot Fight Mode, a header rule will not help;
the owner would need to switch it off for the zone or use a plan with Super Bot Fight Mode. Which
feature produced a given block can be seen in the Cloudflare dashboard's security events for the
request's Ray ID.

The secret value in the rule is stored in Cloudflare, so treat it like a password: random, long, and
rotated if it leaks (change it in the rule and in your Actions secret).
