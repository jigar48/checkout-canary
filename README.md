# checkout-canary

A free, open-source, config-driven synthetic monitor for online stores. It uses Playwright to walk a
store's key journey (home, product, cart, checkout), stops before payment, and reports pass or fail
with evidence you can read without being a developer.

**Why this exists.** An uptime ping tells you a server answered, not that a customer can still reach
checkout. Hosted monitoring services exist, and so do blog posts on wiring Playwright into cron
yourself. checkout-canary aims to be a free, self-hosted, packaged option that needs no server of its
own and produces owner-readable output. I have not proven that nothing similar exists.

> **Status: early development (pre-alpha, version 0.1.0).** This README describes only what works
> today. Not built yet: alerts, scheduled runs, a status page, Magento/WooCommerce presets, retries.

## Responsible use

Only run checkout-canary against sites you own or have written permission to test. It never places an
order and never submits payment details; write your journeys so they stop before the payment step.
It identifies itself with this User-Agent: `checkout-canary/<version> (+https://github.com/jigar48/checkout-canary)`.
Steps run one after another, never in parallel. Do not put real passwords or secrets in journey files.

## Quickstart (about 5 minutes, no internet shop needed)

Requires Python 3.12 or newer. This runs a journey against a small fake shop that ships in this repo.

```bash
git clone https://github.com/jigar48/checkout-canary.git
cd checkout-canary
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e .
python -m playwright install chromium
```

Terminal 1: serve the **working** fake shop.

```bash
python -m http.server 8000 --bind 127.0.0.1 --directory tests/fixtures/shop/ok
```

Terminal 2: run the example journey.

```bash
checkout-canary run examples/demo-shop.yml
```

Expected: every step shows `[PASS]`, the last line says `PASS: 'Demo shop checkout' completed all 12 steps.`
and the exit code is 0.

Now stop the server (Ctrl+C) and serve the **broken** shop, where the cart page has no checkout button:

```bash
python -m http.server 8000 --bind 127.0.0.1 --directory tests/fixtures/shop/broken
checkout-canary run examples/demo-shop.yml
```

Expected: step 8 shows `[FAIL]`, the remaining steps are `[SKIP]`, and the exit code is 1. Evidence is
written to `results/`:

| File | What it is |
| --- | --- |
| `results/result.json` | Machine-readable result: per-step status, timings and error message |
| `results/failure.png` | Screenshot of the page at the moment of failure (failures only) |
| `results/trace.zip` | Playwright trace (failures only). Open with `python -m playwright show-trace results/trace.zip` |
| `results/screenshots/` | Screenshots taken by `screenshot` steps |

`results/` is git-ignored. Files from an earlier run are overwritten, not deleted, so trust `result.json`
for the latest run.

## Command line

```text
checkout-canary run JOURNEY.yml [--output-dir DIR] [--base-url URL]
```

| Exit code | Meaning |
| --- | --- |
| 0 | Journey passed |
| 1 | Journey failed (a step failed) |
| 2 | Could not run: invalid journey file, missing file, or the browser could not start |

## Journey file format

One journey per file. A step is a mapping with exactly one action:

| Action | Value | What it does |
| --- | --- | --- |
| `goto` | URL or path | Opens a page. A path like `/cart` needs `base_url`. Fails on HTTP 400 and above. |
| `click` | selector | Clicks an element |
| `fill` | `selector` and `value` | Types into an input |
| `expect_text` | `selector` and `text` | Passes if the element contains the text |
| `expect_visible` | selector | Passes if the element is visible |
| `screenshot` | name | Saves `screenshots/<name>.png` (letters, digits, `-`, `_` only) |

Top-level fields: `name` (required), `steps` (required, at least one), `base_url` (optional, http or
https), `timeout_ms` (optional, default 10000, applies to every step). Selectors are
[Playwright selectors](https://playwright.dev/python/docs/locators), for example `#id`, `.class` or
`text=Add to cart`. A selector that matches several elements makes `click` and `fill` fail; make it
more specific.

Example 1: check that a product page loads.

```yaml
name: Product page loads
base_url: https://shop.example.com
steps:
  - goto: /products/blue-mug
  - expect_visible: "#add-to-cart"
  - screenshot: product
```

Example 2: add to cart and reach the checkout form, stopping before payment.

```yaml
name: Reach checkout
base_url: https://shop.example.com
timeout_ms: 8000
steps:
  - goto: /products/blue-mug
  - click: "#add-to-cart"
  - expect_text:
      selector: h1
      text: Your cart
  - click: "#checkout-button"
  - fill:
      selector: "#email"
      value: test@example.com
  - expect_visible: "#payment-step"
```

(`shop.example.com` is a placeholder. The only journey tested so far is `examples/demo-shop.yml`
against the bundled fake shop.) Mistakes are reported with the step number and field, for example
`step 2 > fill > value: Field required`.

## Development

```bash
pip install -e ".[dev]"
python -m playwright install chromium
ruff check . && ruff format --check .
pytest
```

Tests start the fake shop on a local port and need no internet. CI runs the same steps on every push.

## Known limits

- Chromium only, headless, one viewport (1280x800).
- One journey per file; no retries; no alerts; no scheduling.
- Tested on Python 3.12 only (Linux in CI, Windows locally).
- Failure messages are plain-language for the common cases (element not found, text not shown, HTTP
  error). Other Playwright errors are shown shortened.
- Only the bundled fake shop has been tested. No real store has been tested.

## License

MIT, see [LICENSE](LICENSE).
