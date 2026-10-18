# Changelog

All notable changes are listed here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added
- `wait` step: pause for 100 to 10000 ms, for pages that need a moment after loading.
- `CHECKOUT_CANARY_USER_AGENT` to set the User-Agent.
- `CHECKOUT_CANARY_HEADER_NAME` / `CHECKOUT_CANARY_HEADER_VALUE`: one secret request header sent only
  to the journey's own origins, kept out of output, results, screenshots and traces. See
  `docs/bot-protection.md`.

## [0.1.0] - unreleased

First pre-alpha version. Tested against local fixtures only, not against any real store.

### Added
- `checkout-canary run <journey.yml>`: YAML journeys (`goto`, `click`, `fill`, `expect_text`,
  `expect_visible`, `screenshot`) validated with pydantic, run in headless Chromium via Playwright.
- JSON result with per-step status, timings and plain-language summary; failure screenshot and
  Playwright trace on failure; exit codes 0 (pass), 1 (fail), 2 (could not run).
- Telegram failure alerts (token and chat ID from environment variables only) behind a small
  `Notifier` interface.
- `checkout-canary status update`: run history and a static green/red status page (last 30 runs,
  failure screenshot).
- Scheduled GitHub Actions workflow that monitors a demo shop and deploys the status page to GitHub
  Pages; scheduling documentation with limits.
- Experimental presets for Magento 2 (Luma) and WooCommerce (classic cart/checkout), each with a
  local fixture and tests.
- Local fixture shop (working and broken variants), example journey, journey guide.
- CI: ruff, Chromium install and pytest on every push.
