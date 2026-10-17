# checkout-canary v0.1.0 (pre-alpha)

First public version. A free, open-source synthetic monitor that walks an online store's checkout
journey in a real browser (Playwright), stops before payment, and reports pass or fail with evidence.

**Please read:** this release has only been tested against local fake shops. It has not been tested
against a real store, a real Telegram bot or a live GitHub Pages deployment. Use it only on stores
you own or have written permission to test.

## Highlights

- `checkout-canary run journey.yml`: six step types, readable validation errors, JSON result,
  failure screenshot and Playwright trace, exit codes 0 / 1 / 2.
- Telegram alert on failure (token and chat ID from environment variables only).
- Static status page and a scheduled GitHub Actions workflow with a demo shop on GitHub Pages.
- Experimental presets: Magento 2 (Luma) and WooCommerce (classic checkout).
- Journey guide, CONTRIBUTING, issue templates, CI (ruff and pytest).

## Known limits

- Chromium only; one journey per file; no retries.
- Presets are experimental and not verified against live stores; the WooCommerce preset does not
  support the block-based Cart/Checkout.
- GitHub scheduled workflows are best effort and are disabled after 60 days of no repository
  activity in public repositories.
- Not published to PyPI. Install from a clone: `pip install -e .`.

## Upgrade notes

None (first release).

## Checklist for the maintainer (not done by the tooling)

1. Merge the pull requests in order (parts 1 to 4) and confirm CI is green on `main`.
2. Enable GitHub Pages (Settings -> Pages -> Source: GitHub Actions) and run the **Monitor demo shop**
   workflow once with `deploy_only` ticked (see `docs/scheduling.md`).
3. Optional: add the Telegram secrets for live alerts.
4. Change `[0.1.0] - unreleased` in `CHANGELOG.md` to the release date.
5. Create the tag and GitHub release `v0.1.0` and paste this file as the release notes.
