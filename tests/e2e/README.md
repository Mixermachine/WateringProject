# End-to-end suite

Runs the real integration and the real card in a real Home Assistant container.

```bash
cd tests/e2e
npm ci
npx playwright install --with-deps chromium   # once
docker compose up -d
npx playwright test
```

`docker compose down -v` afterwards. The container keeps `/config` on disk
(`tests/e2e/config/`), so the second run reuses the onboarded instance; delete
`tests/e2e/config/.storage/` for a clean slate (and to rotate the local token).

## How it works

- `harness/global-setup.ts` waits for HA (`/auth/providers`), onboards the owner,
  creates the `fake_plants` and `watering_project` entries through the config flow,
  writes the options once, and stores tokens + device ids in `.auth/state.json`
  (gitignored).
- `harness/state.ts` exposes the baseline reset (plant values, options, aging) and
  the browser bootstrap: seeds `localStorage["hassTokens"]` before the first
  navigation.
- `specs/watering-card.spec.ts` holds the eight scenarios. They are **not** serial:
  each one resets what it touches first, so a failure does not skip the rest.

## Gotchas that cost time

- Never probe `/api/*` without a token: repeated 401s make Home Assistant ban the
  runner IP. Use `/auth/providers` for readiness.
- Onboarding steps need `client_id`; the `integration` step also needs
  `redirect_uri`. `/api/onboarding` answers 404 once onboarding is finished.
- `/api/config/device_registry/list` has no REST endpoint — use the websocket
  command `config/device_registry/list`.
- The options flow is created with `POST /api/config/config_entries/options/flow`
  and the **entry id** as `handler`.
- Notifications survive restarts in the store: start a scenario from a confirmed
  recovery (all plants watered) before asserting a push.
