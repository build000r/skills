# Headless Browser Probes

When command-line probes (API/log/DB/test) cannot observe a behavior, run a
**headless browser probe** before opening DevTools. Done well, the probe
becomes a regression test in §7 of the main SKILL.md.

The default backend is [obscura](https://github.com/h4ckf0r0day/obscura) — a
Rust headless browser that speaks Chrome DevTools Protocol and works as a
drop-in for Puppeteer/Playwright. ~30 MB resident vs ~200 MB for full
Chromium, ~6× faster startup, Apache 2.0. Stealth mode (anti-fingerprinting +
tracker blocking) is on by default.

If obscura isn't installed, the same probes work against vanilla
Puppeteer/Playwright — point the CDP endpoint at any Chromium and the scripts
below run unchanged.

## Why obscura, specifically

The DevTools gate exists because firing up a browser is expensive. Obscura
makes the headless rung cheap enough to be a default, not a last resort:

- Small enough to keep in CI without slowing the suite
- Fast enough to run once per `/reproduce` invocation without thinking about it
- CDP-compatible, so existing Puppeteer/Playwright muscle memory transfers
- Stealth defaults reduce false-failures from anti-bot heuristics

Skip obscura when a JSON endpoint, log line, or DB query can already prove
the behavior. A browser is overhead unless the bug is browser-runtime-only.

## Setup

Start the CDP server once per session:

```bash
obscura serve --port 9222 &  # exposes ws://localhost:9222
```

Or use the one-shot CLI for stateless fetches:

```bash
obscura fetch <url>           # returns rendered HTML after JS execution
obscura scrape <url> --selector <css>  # extracts matching nodes
```

Puppeteer/Playwright scripts connect with:

```js
const browser = await puppeteer.connect({ browserWSEndpoint: 'ws://localhost:9222' });
```

## Template 1 — Assert a selector on a JS-rendered page

Use when curl returns an empty SPA shell and the real content hydrates client-side.

```bash
#!/usr/bin/env bash
set -euo pipefail
URL="${1:?usage: probe-selector.sh URL CSS_SELECTOR EXPECTED_TEXT}"
SEL="${2:?missing selector}"
EXPECT="${3:?missing expected text}"

HTML="$(obscura fetch "$URL")"
echo "$HTML" | rg -q "$EXPECT" || {
  echo "FAIL: selector '$SEL' did not contain '$EXPECT'"
  exit 1
}
echo "PASS: '$EXPECT' present in $URL"
```

Pair with a side-effect assertion (log line / DB row) to clear the §2
"strong evidence" bar.

## Template 2 — Login with overlay creds and capture state

Use when the bug is behind auth. Pulls credentials from the active
skillbox client overlay's `context.test_accounts` (see SKILL.md §5b) so
the user is never asked for a password.

```js
// scripts/probe-login-state.mjs
// usage: node probe-login-state.mjs <service-id> <target-url> <state-selector>
import puppeteer from 'puppeteer';
import { readFileSync } from 'node:fs';
import { execSync } from 'node:child_process';

const [serviceId, targetUrl, stateSel] = process.argv.slice(2);
const overlayPath = execSync('skillbox overlay path --json', { encoding: 'utf8' });
const overlay = JSON.parse(readFileSync(JSON.parse(overlayPath).path, 'utf8'));
const acct = overlay.context.test_accounts.find(a => a.service === serviceId);
if (!acct) { console.error(`no test_account for ${serviceId}`); process.exit(2); }

const browser = await puppeteer.connect({ browserWSEndpoint: 'ws://localhost:9222' });
const page = await browser.newPage();
await page.goto(`${new URL(targetUrl).origin}/login`);
await page.type('input[name=email]', acct.email);
await page.type('input[name=password]', acct.password);
await Promise.all([page.click('button[type=submit]'), page.waitForNavigation()]);
await page.goto(targetUrl);

const state = await page.$eval(stateSel, el => ({
  text: el.textContent,
  classes: el.className,
  computed: getComputedStyle(el).cssText,
}));
console.log(JSON.stringify(state, null, 2));
await browser.disconnect();
```

The JSON output is grep-able and diff-able — exactly what a regression
test needs as its assertion.

## Template 3 — Screenshot + visual diff

Use when the bug is purely visual (layout shift, missing icon, wrong color).

```bash
#!/usr/bin/env bash
set -euo pipefail
URL="${1:?usage: probe-visual.sh URL BASELINE_PNG}"
BASELINE="${2:?missing baseline png}"

CURRENT="$(mktemp -t probe-visual-XXXXXX.png)"
obscura screenshot "$URL" --out "$CURRENT" --width 1280 --height 800

# Pixel diff via ImageMagick (any diff tool works)
DIFF_PIXELS="$(magick compare -metric AE "$BASELINE" "$CURRENT" /tmp/diff.png 2>&1 || true)"
echo "diff pixels: $DIFF_PIXELS"
[ "$DIFF_PIXELS" -lt 500 ] || {
  echo "FAIL: visual diff exceeds threshold (see /tmp/diff.png)"
  exit 1
}
echo "PASS"
```

For repeatable baselines, commit the reference PNG next to the test and
treat its update as a code review item.

## When obscura is still not enough

Escalate to DevTools (per SKILL.md §6) only after a headless probe fails to
observe the behavior. Genuine reasons to escalate:

- Bug only fires under real user input cadence (long-press, drag, IME)
- Browser extension is implicated and cannot be loaded headlessly
- Network waterfall analysis is the actual question

In every other case, prefer to extend the headless probe.
