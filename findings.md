# Findings

- TMSF community detail and tendency pages return HTTP 405 to the existing urllib client, while a real browser returns 200.
- Browser inspection showed no independent public JSON price endpoint; the relevant content is rendered in the HTML page.
- The prior global `<text>元/㎡</text>` extraction read recommendation cards, not a community price sample, and is retired.
- The approved transport is curl_cffi Chrome impersonation: no Chromium/Playwright runtime.
