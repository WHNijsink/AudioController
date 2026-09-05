# AudioController — working notes for Claude

Tornado + python-socketio server for a church audio system, running on a Raspberry Pi.
The frontend is a Transcrypt-compiled single-page app (source in `transcrypt/python/`,
compiled into `audio_controller/audio_controller/static/js/main*.js`) plus a `/psalmbord`
kiosk page (`views/psalmbord.html`).

Two listeners: **5000** internal (LAN kiosk screens reach `/psalmbord` without login;
loopback clients are the trusted local-operator UI) and **8080** external (login
required for everything). Trust is decided in `BaseHandler.is_localhost` (loopback peer
AND loopback Host header).

## ALWAYS verify on a running local instance before claiming done

Unit tests are necessary but NOT sufficient. Any change that touches auth, the login
flow, settings/admin, routing, the SPA (`transcrypt/python/`), or the kiosk page MUST
also be verified against a live local instance, including the **login and settings
flows**, because much of that logic lives in the compiled frontend that pytest does not
exercise.

Do this every time such a change is made:

1. **Run the unit tests** (from `audio_controller/`):
   ```
   ../pyenv/bin/python -m pytest -q
   ```
2. **Rebuild the frontend** if you changed anything under `transcrypt/python/`
   (the compiled `main.js` is git-ignored and regenerated on deploy):
   ```
   cd transcrypt/python && ../../pyenv/bin/transcrypt --build --nomin --map main
   cd .. && npx webpack --config webpack.local.js     # tracked webpack.config.js fails on Transcrypt ESM
   cp python/__target__/bundle/main.js ../audio_controller/audio_controller/static/js/main.js
   ```
   (remove any old `static/js/main-*.js` first so the server serves the fresh one).
3. **Start an isolated local instance** on loopback with a throwaway HOME, so the real
   `~/.audio_controller_*` files and the Pis are never touched:
   ```
   HOME=/tmp/ac_test ./pyenv/bin/python -c "import sys; sys.path.insert(0,'audio_controller'); \
     from audio_controller.__main__ import make_app; import tornado.ioloop; \
     [make_app(i).listen(p, address='127.0.0.1') for p,i in [(5003,True),(8083,False)]]; \
     tornado.ioloop.IOLoop.current().start()"
   ```
   (run from the repo root; verified: `/psalmbord` on 5003 → 200, a POST without the
   `_xsrf` token → 403.)
   (5003 = internal/trusted, 8083 = external/login-required.)
4. **Drive it in a browser** (Playwright MCP is available) and confirm the real flows,
   at minimum:
   - internal port: the operator tabs (Geluid/Psalmbord/Camera) work without login;
   - clicking **Instellingen** shows the **login dialog** (never a 405 or a crash),
     an admin login opens the settings, and cancelling returns to the previous tab;
   - external port: login is required and works.
   Also curl-check the endpoints you changed (with the `_xsrf` cookie + `X-Xsrftoken`
   header for POSTs).

Only report the work as done after this live check passes.

## Deployment / the Pis

- Never ssh to or HTTP-call a church Pi (west, noord, …) on a day with a service, and
  only with explicit permission otherwise — they run live services.
- `update_pi.sh` manages the Pi installs. The service runs as **root**, so the live
  config is in `/root/`. Restore settings via the admin-page JSON upload, not by
  copying files over ssh.

## Conventions

- Commits: match the existing style; **no Claude co-author trailers** (repo owner's
  preference).
- Contribute via the `WHNijsink` fork + PR to `ArjenGuis` (upstream, no direct push).
  Arjen Guis also pushes to shared feature branches — pull/merge before pushing.
