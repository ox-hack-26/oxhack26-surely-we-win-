import { useEffect } from "react";
import { weekDate } from "../data/model";
import { pad2, shortDate } from "../format";
import { getState, setState, useBundle, useDecisions, useStore } from "../store";

const STEP_MS = 1100; // a week every 1.1s: the 600ms data move, then a beat to read it

function step(by: number) {
  setState((s) => {
    const n = s.bundle?.settings.n_weeks ?? 20;
    return { week: Math.max(1, Math.min(n, s.week + by)), story: null };
  });
}

export function togglePlay() {
  const { playing, week, bundle } = getState();
  const n = bundle?.settings.n_weeks ?? 20;
  if (playing) setState({ playing: false });
  else setState({ playing: true, story: null, week: week >= n ? 1 : week });
}

export function Timeline() {
  const bundle = useBundle();
  const week = useStore((s) => s.week);
  const playing = useStore((s) => s.playing);
  const selected = useStore((s) => s.selected);
  const decisions = useDecisions();
  const n = bundle.settings.n_weeks;

  useEffect(() => {
    if (!playing) return;
    const id = window.setInterval(() => {
      setState((s) => (s.week >= n ? { playing: false } : { week: s.week + 1 }));
    }, STEP_MS);
    return () => window.clearInterval(id);
  }, [playing, n]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement;
      if (t.closest("input, textarea, select, button, [role=slider]")) return;
      if (e.key === " ") togglePlay();
      else if (e.key === "ArrowRight") step(1);
      else if (e.key === "ArrowLeft") step(-1);
      else return;
      e.preventDefault();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  // Weeks where an alarm starts somewhere (or at the selected clinic only).
  const starts = new Map<number, number>();
  for (const [id, d] of Object.entries(decisions)) {
    if (selected && id !== selected) continue;
    if (d.firstAlarm) starts.set(d.firstAlarm, (starts.get(d.firstAlarm) ?? 0) + 1);
  }
  const date = weekDate(bundle, week);

  return (
    <footer className="timeline">
      <button type="button" className="btn btn--primary timeline__play" onClick={togglePlay} aria-label={playing ? "Pause the replay" : "Play the replay"}>
        <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true">
          {playing ? <path d="M2 1h3v10H2zM7 1h3v10H7z" fill="currentColor" /> : <path d="M2 1l9 5-9 5z" fill="currentColor" />}
        </svg>
        {playing ? "Pause" : "Play"}
      </button>
      <div className="timeline__week">
        <span className="label">Week</span>
        <span className="num timeline__weeknum">
          {pad2(week)}
          <span className="timeline__of">/{n}</span>
        </span>
      </div>
      <div className="timeline__track">
        <div className="timeline__marks" aria-hidden="true">
          {Array.from({ length: n }, (_, i) => i + 1).map((w) => (
            <span key={w} className={`timeline__mark${w <= week ? " is-past" : ""}${w === week ? " is-now" : ""}`}>
              {starts.has(w) && (
                <span className="timeline__alarm">
                  <i className="status-dot status-dot--alarm status-dot--still" />
                  <span className="num">{starts.get(w)}</span>
                </span>
              )}
            </span>
          ))}
        </div>
        <input
          type="range"
          className="timeline__range"
          min={1}
          max={n}
          step={1}
          value={week}
          aria-label="Week of the replay"
          aria-valuetext={`Week ${week}, ${shortDate(date)}`}
          onChange={(e) => setState({ week: Number(e.target.value), playing: false, story: null })}
        />
      </div>
      <div className="timeline__date">
        <span className="label">Week of</span>
        <span className="num">{shortDate(date)}</span>
      </div>
    </footer>
  );
}
