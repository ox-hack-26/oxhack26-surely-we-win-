# ClinicDrift web: design system

The single source of truth for the web app. Every colour, size, space, radius and duration in `src/` comes from `src/styles/tokens.css`, which mirrors this file. Change it here first.

## Theses (validated 24 October 2026)

**Visual thesis.** A dark ophthalmic-instrument console: a warm near-black darkroom ground with flat panels, where colour is reserved for data alone (blue for ClinicDrift, orange for expert grades, aqua for drift, amber for the AI's own estimate, red only for alarms) and the only image is the retina photograph. Instrument Sans for words, from 13px labels to 32px headings, and IBM Plex Mono for every number so readouts line up like a device display. Dense 4px-based spacing in the control panels around one open 3D stage. Flat panels, 6px radii, 1px hairline borders, no shadows, no glass.

**Interaction thesis.** Measured and physical, never bouncy: interface changes in 200ms ease-out, week-to-week data in 600ms ease-in-out with no overshoot, story-mode camera moves in 1.2s ease-in-out, the detail drawer in 320ms. Hover brightens a column or row and shows its exact value, with no scaling or lifting. No scroll effects: the app is one fixed instrument. An active alarm sends one slow red pulse every 2.4s. Forbidden: bounce, elastic or overshoot on data, parallax, glass, gradient text, confetti, a camera that drifts while someone reads, scale on hover. Reduced motion cuts camera moves to instant and freezes the pulse.

**Allowed patterns:** mono numerals for every readout (numbers only, never labels or navigation), 1px hairline rules, the retina photograph as the only image, a looping alarm pulse (it reports a live alarm), a soft glow on alarm beacons in the 3D view only, a live week counter.

**3D rendering notes:** the beacon glow is a soft sprite, not a bloom pass, and the floor is satin, not a mirror: both alternatives roughly halved the frame rate on the integrated Intel GPU this demo laptop runs Chrome on. Pointing at or opening a clinic dims the others in 200ms.

**Assumptions** (made at the user's request, open to correction): the audience is hackathon judges watching a live demo and then exploring; the mood is clinical and serious; it must not read as a generic white medical dashboard or a neon "AI" site.

## Dials

| Dial | Value | From the thesis |
|---|---|---|
| Variance | 5 | "flat panels around one open 3D stage": a balanced layout with one bold area |
| Motion | 4 | "measured", one slow alarm pulse, "no scroll effects" |
| Density | 7 | "dense 4px-based spacing in the control panels" |

Design-system lookup (ui-ux-pro-max): took its anti-patterns (no neon, no motion-heavy animation, no AI gradients) and its checklist (visible focus, reduced motion, 44px targets, 375/768/1024/1440 widths). Dropped its navy palette and green accent (colour means data only), Figtree and Noto Sans (the thesis names Instrument Sans and IBM Plex Mono), its `back.out` stagger (overshoot is forbidden) and its blinking status indicators (the only loop allowed is the alarm pulse).

## Colour

Single dark theme, by decision: the app is an instrument in a darkroom.

| Token | Value | Role | Contrast on panel |
|---|---|---|---|
| `--ground` | `#0d0d0d` | page and 3D stage background | |
| `--panel` | `#1a1a19` | panels, drawer | |
| `--panel-2` | `#232321` | raised controls, hovered rows | |
| `--panel-3` | `#2c2c2a` | pressed controls, chart grid | |
| `--hairline` | `rgba(255,255,255,0.10)` | all borders and rules | |
| `--hairline-strong` | `rgba(255,255,255,0.28)` | hovered borders | |
| `--axis` | `#383835` | chart baselines and axes | |
| `--ink` | `#f0efec` | primary text, focus ring | 15.1:1 |
| `--ink-bright` | `#ffffff` | primary button hover only | |
| `--ink-2` | `#c3c2b7` | secondary text | 9.7:1 |
| `--muted` | `#898781` | labels, axis text | 4.8:1 |
| `--belief` | `#3987e5` | ClinicDrift's belief | 4.8:1 |
| `--grades` | `#d95926` | expert grades, the real catch rate | 4.5:1 |
| `--drift` | `#199e70` | drift score | 5.1:1 |
| `--estimate` | `#c98500` | the AI's own estimate | 5.7:1 |
| `--alarm` | `#d03b3b` | alarms only, always with a label | 3.6:1 |

The four data colours pass the colour-blind validator on `#1a1a19` (worst adjacent CVD ΔE 8.4, normal-vision ΔE 19.8). Data colours never colour text: a coloured key sits beside ink text. There is no green "OK" status: a clinic that is fine is shown in neutral ink.

## Type

- `--font-sans`: "Instrument Sans", "Segoe UI", system-ui, sans-serif. Weights 400, 500, 600. Approved Google Fonts face, loaded with `display=swap`.
- `--font-mono`: "IBM Plex Mono", "Cascadia Mono", Consolas, ui-monospace, monospace. Weights 400, 500. Numbers only, with tabular figures.

| Token | Size / line | Use |
|---|---|---|
| `--text-caption` | 12 / 16 | axis ticks, footnotes |
| `--text-label` | 13 / 17, 500, uppercase, 0.06em | field labels |
| `--text-body` | 15 / 23 | running text |
| `--text-title` | 17 / 22, 600 | panel titles |
| `--text-heading` | 20 / 25, 600 | section headings |
| `--text-display` | 32 / 37, 600 | page heading |
| `--text-readout` | 56 / 56, mono 500 | the one hero number per view |
| `--text-readout-sm` | 24 / 24, mono 500 | panel readouts |

## Space, radius, depth

- Spacing, base 4: `--s-1` 4, `--s-2` 8, `--s-3` 12, `--s-4` 16, `--s-5` 20, `--s-6` 24, `--s-8` 32, `--s-12` 48, `--s-16` 64.
- Radius: `--r-sm` 4 (chips, inputs, chart bars), `--r` 6 (panels, buttons). Nothing fully round except dots and the retina lens.
- Shadows: none. Depth comes from surface steps (`--ground` < `--panel` < `--panel-2` < `--panel-3`).
- Layers: `--z-stage` 1, `--z-hud` 10, `--z-drawer` 20, `--z-tooltip` 30, `--z-modal` 40.
- Touch targets at least 44px tall on touch screens.

## Motion

| Token | Value | Use |
|---|---|---|
| `--ease-ui` | `cubic-bezier(0.22, 1, 0.36, 1)` | interface changes, drawer |
| `--ease-data` | `cubic-bezier(0.65, 0, 0.35, 1)` | data moves, camera moves; no overshoot |
| `--ease-exit` | `cubic-bezier(0.55, 0, 1, 0.45)` | things leaving (drawer closing), with `--dur-ui` |
| `--dur-ui` | 200ms | hover, press, toggles |
| `--dur-drawer` | 320ms | detail drawer |
| `--dur-data` | 600ms | week-to-week data |
| `--dur-camera` | 1200ms | story-mode camera moves |
| `--dur-pulse` | 2400ms | alarm pulse period |

No stagger (the thesis names none). Under `prefers-reduced-motion: reduce`, durations drop to 0 except colour changes, camera moves cut, and the pulse is a still ring.

## Components

Every interactive component has five states: default, hover, focus (2px `--ink` outline, 2px offset), active, disabled (40% opacity, no pointer).

- **Button, primary:** `--ink` fill, `--ground` text. Hover: white fill. Active: `--ink-2` fill.
- **Button, ghost:** transparent, hairline border, `--ink` text. Hover: `--panel-2` fill, strong hairline. Active: `--panel-3`.
- **Segmented control:** ghost buttons joined; the selected one is `--panel-3` with `--ink` text.
- **Status:** a dot and a label. Alarm: red dot, label "Drift alarm" or "Harm alarm". Fine: hollow ink ring, label "OK".
- **Readout:** `--text-readout-sm` number above a label with its colour key.
- **Slider:** 4px `--panel-3` track, `--ink` thumb, value printed in mono beside it.
- **Tooltip:** `--panel-2`, hairline border, `--r-sm`, mono numbers.
- **Panel:** `--panel`, hairline border, `--r`, padding `--s-5`.
