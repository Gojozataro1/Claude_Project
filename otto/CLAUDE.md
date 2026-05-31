# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Otto is a two-page SaaS marketing mockup for a web software company. It is a single self-contained file — `index.html` — with no build step, no dependencies, and no framework.

## Running the site

```bash
open index.html          # macOS — opens directly in the default browser
python3 -m http.server   # optional: serve at http://localhost:8000 if you need a real HTTP origin
```

## Architecture

Everything lives in `index.html` in three layers:

**CSS (`:root` design tokens → component styles)**
All colour, spacing, and typography values are defined as CSS custom properties on `:root`. Touch tokens first before editing individual component styles. The accent colour (`--accent: #2997ff`) is used site-wide for interactive elements; particle animation colours are kept separate in JS.

**HTML (two pages, one DOM)**
Both pages (`#pg-home`, `#pg-services`) are always in the DOM. Only the `.active` page is visible. The nav, both pages, and both footers are siblings under `<body>`.

**JavaScript (three independent concerns)**
1. `go(name)` — page router. Fades out all pages, swaps `.active`, fades in the target, resets scroll, updates nav state, then calls `attachReveal()`.
2. `attachReveal()` — wires `IntersectionObserver` onto `.reveal` elements. Must be called after every page switch because newly revealed pages contain unobserved elements.
3. Particle engine — canvas animation with a 4-state machine (`FLOAT → FORM → HOLD → DISSOLVE → FLOAT`). Key globals: `particles[]`, `targets[]`, `state`, `timer`.

## Particle engine internals

`buildTargets()` defines the formation shape as an array of `{ x, y, d }` points where `d` is the per-particle formation delay in frames. The shape is a software dashboard UI assembled in four layers:

| Delay | What forms |
|-------|-----------|
| `d=0` | Nav bar (top line, divider, dots, search, buttons) |
| `d=22` | Outer shell border + sidebar divider + sidebar menu items |
| `d=46+` | Card borders — one card every 10 frames |
| `d=76+` | Card content lines + table rows |

`setTargets('form')` sorts `targets` by `d` and assigns them to particles in order, so earlier-delay targets go to the first particles — preserving the layered build-up. `settled()` only counts particles past their `d + 20` grace period so the state machine doesn't advance before delayed particles have had a chance to move.

Particle colour is cool grey: `hsla(212–228, 5–14%, 60–82%)`. Do not use the site's `--accent` blue inside the canvas — the grey palette is intentional contrast with the page UI.

## Design system

| Token | Value | Used for |
|-------|-------|---------|
| `--bg` | `#000` | Page background |
| `--surface` | `#0a0a0a` | Card / feature backgrounds |
| `--text` | `#f5f5f7` | Primary text |
| `--text-secondary` | `#86868b` | Body copy, captions |
| `--accent` | `#2997ff` | Buttons, labels, tags, SVG icons |
| `--border` | `rgba(255,255,255,0.08)` | Dividers, card outlines |

Typography uses the system font stack (`-apple-system, SF Pro Display, Inter, Segoe UI`). Font sizes are set with `clamp()` for fluid scaling — prefer `clamp()` over fixed `px` for headings.

## Extending the site

- **Add a page:** create `<div class="page" id="pg-NAME">`, add a nav button that calls `go('NAME')`, and add `id="ln-NAME"` to the button.
- **Change the formation shape:** edit only `buildTargets()`. The rest of the engine is shape-agnostic.
- **Add scroll-reveal to an element:** add class `reveal`. It transitions in via `.reveal.in` (opacity + translateY). Elements on inactive pages are observed lazily after `go()` is called.
