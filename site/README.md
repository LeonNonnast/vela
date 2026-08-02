# Vela site

Static marketing page for `vela.nonnast.dev`. No build step — edit `index.html`
directly, assets live in `assets/`.

## Deploying

This directory replaces the previous SaaS-era landing page, which lived
untracked in `.bin/src/api/static/landing.html` (served by an old FastAPI app
that is no longer part of this repo). Pointing `vela.nonnast.dev` at
`site/index.html` instead is a manual hosting change and hasn't been done yet.

## Note

`vela-sdk` is already taken on PyPI by an unrelated project. The footer
intentionally links to GitHub only, not package registries — update it once
the real publish name/target is settled.
