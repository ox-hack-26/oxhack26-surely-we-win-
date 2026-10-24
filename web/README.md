# ClinicDrift web app

A 3D view of the replay: ten clinics, twenty weeks, and when ClinicDrift would pull the AI at each one. It is a static site that reads one file, `public/data/clinicdrift.json`, so it runs anywhere without Python.

## Run it

```bash
cd web
npm install
npm run dev
```

Then open the address it prints. `npm run build` writes a static copy to `web/dist/` for hosting.

The data comes from the engine. The pipeline refreshes it at the end (`python -m clinicdrift.engine.pipeline`), or on its own:

```bash
python scripts/export_web.py
```

## What is on screen

- **Clinics.** Each column is a clinic. Height is the catch rate ClinicDrift believes this week, the sleeve its 90% band, the amber ring the AI's own estimate, the aqua halo on the floor drift, and a red beacon an alarm. The flat plane is the 80% screening standard.
- **All weeks** (top right of the 3D view) lays every clinic's whole replay out as a ribbon: week 1 nearest you, an upright sheet for "now" that moves away as the replay plays. Point at any week for its numbers; click to open the clinic at that week. **Reset view** flies the camera home after you have turned it.
- **Hindsight** shows the real catch rate (orange), which in real life nobody sees until the expert grades arrive weeks later.
- **Costs** in the side panel decide every alarm again in the browser, with the same rule as `clinicdrift/engine/decide.py`, and show what each policy would cost in this replay.
- **Play the story** walks through the camera-wear and software-update clinics. **Results** has the backtest over 100 draws of which scans got graded.

## Links for the demo

- `?week=9&clinic=US-WEAR-01` opens a clinic at a week; add `&hindsight=1` for the real catch rate.
- `?view=results` opens the results; `?mode=history` opens the All weeks view.
- `?motion=full` plays every animation even when the computer asks for reduced motion.

Keyboard: space plays and pauses, the arrow keys step through weeks (or story steps), Escape closes the clinic panel or the story.

## Design

`MASTER.md` is the design system: every colour, size and duration in `src/` comes from `src/styles/tokens.css`, which mirrors it.
