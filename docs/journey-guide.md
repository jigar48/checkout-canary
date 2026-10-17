# Writing a journey for any store

A journey is one YAML file that describes what a customer does, in order. checkout-canary performs the
steps in a real browser and stops at the first step that does not work.

**Only test stores you own or have written permission to test.** A journey must stop before payment:
never click "Place order" and never type card details.

## 1. Start from the shape

```yaml
name: My store checkout          # shown in results and alerts
base_url: https://shop.example   # your store (http or https)
timeout_ms: 10000                # per step, optional (100 to 120000, default 10000)
steps:
  - goto: /
  - ...
```

Each step has exactly one action:

| Action | Value | Passes when |
| --- | --- | --- |
| `goto` | path or full URL | the page loads and the server does not answer with HTTP 400 or higher |
| `click` | selector | the element exists, is visible and can be clicked |
| `fill` | `selector` and `value` | the input exists and accepts text |
| `expect_text` | `selector` and `text` | the element contains the text |
| `expect_visible` | selector | the element is visible |
| `screenshot` | name | always; saves `screenshots/<name>.png` (letters, digits, `-`, `_`) |

Rules that trip people up:

- A relative `goto` (like `/cart/`) needs `base_url`. If `base_url` has a path (like
  `https://host/demo-shop/`), end it with `/` and use paths without a leading slash
  (`goto: index.html`), because `/cart/` always means the root of the host.
- Only `http` and `https` URLs are allowed.
- `click` and `fill` fail if the selector matches more than one element. Make the selector more
  specific, or pick one with `>> nth=0` (the first match).
- Values in `fill` are stored in plain text in the journey file. Use fake test data such as
  `test@example.com`, never real passwords or card numbers. Fill values are never written to results,
  alerts or the status page.

## 2. Find reliable selectors

Selectors are [Playwright selectors](https://playwright.dev/python/docs/locators). Prefer, in order:

1. An `id`: `#checkout-button`
2. A stable attribute: `button[data-role='proceed-to-checkout']`, `[data-testid='cart']`
3. Visible text: `text=Proceed to checkout` (breaks if you change the wording or translate the store)
4. A class: `.checkout-button` (breaks when the theme changes)

To find them, open your store in Chrome, right-click the element, choose **Inspect**, and look at the
`id`, `class` and `data-*` attributes. Playwright can also help:
`python -m playwright codegen https://your-store.example` opens a browser and prints selectors as you
click (only use it on stores you own).

## 3. Follow the customer, one check per page

A good journey alternates *do something* and *check it worked*. Checks are what make it a monitor: a
click that lands on an error page should fail at the next check, not pass silently.

```yaml
name: Shop checkout
base_url: https://shop.example
steps:
  - goto: /                                  # 1. open the shop
  - expect_visible: "#search"                #    the page really rendered
  - click: ".product-item a >> nth=0"        # 2. open a product (a simple one, no options)
  - expect_visible: "#add-to-cart"
  - click: "#add-to-cart"                    # 3. add to cart
  - expect_text:                             #    the shop confirmed it
      selector: ".notice"
      text: added to your cart
  - goto: /cart/                             # 4. open the cart
  - expect_visible: "#checkout-button"
  - screenshot: cart                         #    evidence for the owner
  - click: "#checkout-button"                # 5. start checkout
  - fill:
      selector: "#email"
      value: test@example.com
  - expect_visible: "#payment-section"       # 6. payment is visible; STOP HERE
  - screenshot: checkout
```

Tips:

- Use a **simple product** with a known URL if the home page products can change. A product with
  options (size, colour) needs extra `click` steps to choose them first.
- Add `expect_visible` right before important clicks so the failure message names the thing that is
  missing (`'#checkout-button' was not visible after 10s`).
- Keep `timeout_ms` generous for slow stores (10000 to 20000) but not so large that failures take
  minutes to report.
- One journey per file. Run several files from several commands or workflow jobs.

## 4. Run it and read the result

```bash
checkout-canary run my-store.yml
```

- Exit code `0`: passed. `1`: a step failed. `2`: the journey file is invalid or the browser could
  not start.
- `results/result.json` has every step's status, timing and error. On failure you also get
  `results/failure.png` and `results/trace.zip` (open with
  `python -m playwright show-trace results/trace.zip`).
- Validation errors name the step and the field, for example `step 3 > fill > value: Field required`.

## 5. Start from a preset

[`presets/`](../presets) has experimental journeys for Magento 2 and WooCommerce. Copy one, change
`base_url`, and fix any selector your theme changed. They are not verified against live stores.

## 6. Be a good guest

- Run at a low frequency (every 15 to 30 minutes is plenty).
- Do not point it at third-party stores, and do not try to get around bot protection or CAPTCHAs.
- The tool sends the User-Agent `checkout-canary/<version> (+https://github.com/jigar48/checkout-canary)`
  so your logs show where the traffic comes from; you can allow-list it in your own firewall.
- If your store sends order emails or creates carts in a database, remember each run may create an
  abandoned cart. That is expected; clean up carts the way you normally do.
