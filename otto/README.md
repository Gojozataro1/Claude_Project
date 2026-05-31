# Otto — Software for the Web

A two-page SaaS marketing mockup for a fictional web software company. Single self-contained file — `index.html` — with no build step, no dependencies, and no framework.

---

## What's in it

**Pages:**
- **Home** — hero section with a particle canvas animation, feature grid (Custom Design / Performance First / Always On), and a call-to-action
- **Services** — service cards (Website Design, E-Commerce, Web Apps, Maintenance), a 4-step process section, and a CTA

**Technical highlights:**
- Pure HTML + CSS + vanilla JS — zero dependencies
- Particle engine with a 4-state machine (`FLOAT → FORM → HOLD → DISSOLVE`) that assembles a software dashboard UI shape
- CSS design tokens on `:root` for consistent colour and spacing across the whole site
- `IntersectionObserver`-based scroll reveal on all content sections
- Accessible: `inert` attribute on inactive pages, `aria-current` on active nav items, smooth focus management

---

## Running it

```bash
# Open directly in the browser (macOS)
open index.html

# Or serve locally if you need a real HTTP origin
python3 -m http.server
# → http://localhost:8000
```

---

## Architecture

Everything lives in `index.html` in three layers:

**CSS** — `:root` design tokens define all colour, spacing, and typography values. Touch tokens before editing individual component styles.

**HTML** — Both pages (`#pg-home`, `#pg-services`) are always in the DOM. Only the `.active` page is visible. The nav, both pages, and the shared footer are siblings under `<body>`.

**JavaScript** — Three independent concerns:
1. `go(name)` — page router with fade transition and `inert` management
2. `attachReveal()` — `IntersectionObserver` wired onto `.reveal` elements; called after every page switch
3. Particle engine — canvas animation, `buildTargets()` defines the dashboard shape as `{ x, y, d }` points where `d` is per-particle formation delay in frames

### Design tokens

| Token | Value | Used for |
|---|---|---|
| `--bg` | `#000` | Page background |
| `--surface` | `#0a0a0a` | Card backgrounds |
| `--text` | `#f5f5f7` | Primary text |
| `--text-secondary` | `#86868b` | Body copy, captions |
| `--accent` | `#2997ff` | Buttons, labels, tags, SVG icons |
| `--border` | `rgba(255,255,255,0.08)` | Dividers, card outlines |

---

## Extending it

- **Add a page:** create `<div class="page" id="pg-NAME">`, add a nav button that calls `go('NAME')`, add `id="ln-NAME"` to the button
- **Change the particle formation shape:** edit only `buildTargets()` — the rest of the engine is shape-agnostic
- **Add scroll-reveal to an element:** add class `reveal` — it transitions in via `.reveal.in`
