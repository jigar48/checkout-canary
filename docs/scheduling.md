# Scheduled monitoring and the status page

The workflow [`.github/workflows/monitor.yml`](../.github/workflows/monitor.yml) runs the journey
[`journeys/demo-shop.yml`](../journeys/demo-shop.yml) every 30 minutes, keeps the run history, builds a
static status page and publishes it to GitHub Pages together with the **demo shop**, a fake store that
lives in this repository (`tests/fixtures/shop/ok`). The demo shop is not a real store; nothing can be
bought there.

## What the workflow does

1. Runs `checkout-canary run journeys/demo-shop.yml` against the demo shop on GitHub Pages.
2. Appends the result to `history.json` on the **`status-data` branch** (created by the workflow on
   its first run; nothing is ever pushed to `main`). Failure screenshots are stored there too. The last
   90 runs are kept; the page shows the last 30.
3. Builds `index.html` with `checkout-canary status update` and publishes the site with the official
   Pages actions (`actions/upload-pages-artifact`, `actions/deploy-pages`).
4. Uploads the full evidence (screenshots, trace) as a workflow artifact for 14 days.
5. If the journey failed, the run is marked red after the page has been published, and a Telegram
   alert is sent when the two Telegram secrets exist (see below).

Site layout: `/` is the status page, `/demo-shop/` is the demo shop.

## One-time setup (manual steps)

1. **Merge the pull requests** so this workflow is on the default branch. Scheduled workflows only run
   from the default branch.
2. **Enable GitHub Pages:** repository **Settings -> Pages -> Build and deployment -> Source: GitHub
   Actions**. ([GitHub docs](https://docs.github.com/en/pages/getting-started-with-github-pages/configuring-a-publishing-source-for-your-github-pages-site#publishing-with-a-custom-github-actions-workflow))
3. **First run:** open **Actions -> Monitor demo shop -> Run workflow** and tick **deploy_only**. This
   publishes the demo shop before anything tries to monitor it. Without it the first journey run would
   fail because the demo shop does not exist yet.
4. After that, the schedule (or **Run workflow** without the tick) takes over. The page is at
   `https://<owner>.github.io/<repo>/` (for this repository: https://jigar48.github.io/checkout-canary/).
5. *(Optional)* **Telegram alerts:** add repository secrets `CHECKOUT_CANARY_TELEGRAM_TOKEN` and
   `CHECKOUT_CANARY_TELEGRAM_CHAT_ID` (Settings -> Secrets and variables -> Actions). Without them
   the workflow runs without alerts.

## Limits you should know about

- **Best effort timing.** GitHub documents that the `schedule` event "can be delayed during periods of
  high loads", that high load times include the start of every hour, and that "some queued jobs may be
  dropped". The cron here uses minutes 17 and 47 to reduce the chance of delay, but runs can still be
  late or missing. The status page shows a warning when the last check is over 3 hours old.
- **Automatic disabling.** GitHub documents that "in a public repository, scheduled workflows are
  automatically disabled when no repository activity has occurred in 60 days". Re-enable the workflow
  on the Actions tab. Whether the monitor's own pushes to `status-data` count as repository activity
  is **not verified**; do not rely on it to keep the schedule alive.
- Scheduled workflows run only on the default branch, so nothing runs until the work is merged.
- The workflow commits to `status-data` on every run (about 48 commits a day). History is never
  force-pushed or rewritten.
- If the journey cannot start at all (invalid journey, Chromium missing) no history entry is
  written; the run is red and the page keeps showing the previous result.

## Sources

- Schedule event, delays, 60-day rule and default-branch rule:
  https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule
- Pages publishing with a custom workflow (permissions, `environment`, `deploy-pages`):
  https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages
- Publishing source set to GitHub Actions:
  https://docs.github.com/en/pages/getting-started-with-github-pages/configuring-a-publishing-source-for-your-github-pages-site
- Re-enabling a disabled workflow:
  https://docs.github.com/en/actions/how-tos/manage-workflow-runs/disable-and-enable-workflows
