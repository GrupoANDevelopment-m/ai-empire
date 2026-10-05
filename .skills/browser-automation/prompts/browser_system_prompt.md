# Browser Automation

Drive real Chromium via Playwright with persistent user sessions.

1. browser_open_session - persistent profile (cookies survive)
2. browser_navigate to URL
3. browser_wait + extract/fill/click
4. browser_screenshot to confirm
5. browser_close_session (profile persists)

Why: services without public APIs (WhatsApp Web, Instagram, LinkedIn, X, FB) accessible via user's logged-in browser. No API keys, no rate limits.
