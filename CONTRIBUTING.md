# Contributing

Thanks for helping. This is a small project; keep changes small and focused.

## Ground rules

- Only test against stores you own or have written permission to test. Never add tests that call a
  real store or a real Telegram/Slack API; use the local fixtures and fake servers in `tests/`.
- Never commit secrets (tokens, passwords, store credentials). Use environment variables.
- Never add steps that place an order or submit payment details.
- Describe in the README only what actually works and how it was tested.

## Setup

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
python -m playwright install chromium
```

## Before you open a pull request

```bash
ruff check . && ruff format --check .
pytest
```

CI runs the same commands. Add or update tests for what you change, and add a line to
[CHANGELOG.md](CHANGELOG.md).

## Adding or fixing a preset

1. Put the journey in `presets/<name>.yml` with `EXPERIMENTAL` in the header and `experimental` in
   its `name`, and a placeholder `base_url` containing `example`.
2. Add a working and a broken local fixture under `tests/fixtures/<name>/{ok,broken}` that imitates the
   platform's markup, and a case in `tests/test_presets.py`.
3. Say where each selector comes from (link to the platform's source or docs). If you verified the
   preset against a live store you own, say which platform version and theme.
