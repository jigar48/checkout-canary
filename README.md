# checkout-canary

A free, open-source, config-driven synthetic monitor for online stores. It uses Playwright to walk a
store's key journey (home, product, cart, checkout), stops before payment, and reports pass or fail
with evidence.

> **Status: early development (pre-alpha).** The sections below describe only what works today.

## Responsible use

Only run checkout-canary against sites you own or have written permission to test. It never places an
order and never submits payment details, and a journey should stop before the payment step. The tool
identifies itself in its User-Agent header and runs steps one after another at a low request rate.

## License

MIT, see [LICENSE](LICENSE).
