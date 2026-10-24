// What each mark in the 3D view means. Drawn as small glyphs of the marks themselves.
import { useStore } from "../store";

export function Legend() {
  const hindsight = useStore((s) => s.hindsight);
  const mode = useStore((s) => s.mode);
  const real = hindsight ? "(hindsight)" : "(turn on Hindsight)";
  return (
    <details className="legend panel" open>
      <summary className="label">How to read it</summary>
      {mode === "now" ? (
        <ul>
          <li>
            <svg width="18" height="18" viewBox="0 0 18 18" aria-hidden="true">
              <rect x="4" y="2" width="10" height="14" rx="2" className="fill--belief" opacity="0.25" />
              <rect x="7" y="5" width="4" height="11" rx="1" className="fill--belief" />
            </svg>
            Height: catch rate ClinicDrift believes, with its 90% band
          </li>
          <li>
            <svg width="18" height="18" viewBox="0 0 18 18" aria-hidden="true">
              <ellipse cx="9" cy="9" rx="7" ry="2.6" fill="none" className="stroke--estimate" strokeWidth="2" />
            </svg>
            Amber ring: the AI's own estimate
          </li>
          <li className={hindsight ? undefined : "is-off"}>
            <svg width="18" height="18" viewBox="0 0 18 18" aria-hidden="true">
              <ellipse cx="9" cy="9" rx="7.5" ry="2.8" fill="none" className="stroke--grades" strokeWidth="2.4" />
            </svg>
            Orange ring: real catch rate {real}
          </li>
          <li>
            <svg width="18" height="18" viewBox="0 0 18 18" aria-hidden="true">
              <ellipse cx="9" cy="12" rx="8" ry="3.2" fill="none" className="stroke--drift" strokeWidth="2" />
            </svg>
            Aqua halo: drift, wider when scans look unfamiliar
          </li>
          <li>
            <svg width="18" height="18" viewBox="0 0 18 18" aria-hidden="true">
              <circle cx="9" cy="9" r="4" className="fill--alarm" />
            </svg>
            Red beacon: alarm, pull the AI for review
          </li>
        </ul>
      ) : (
        <ul>
          <li>
            <svg width="18" height="18" viewBox="0 0 18 18" aria-hidden="true">
              <path d="M1 12 L6 6 L11 8 L17 3 L17 9 L11 13 L6 11 L1 16 Z" className="fill--belief" opacity="0.3" />
              <path d="M1 14 L6 8.5 L11 10.5 L17 6" fill="none" className="stroke--belief" strokeWidth="2" />
            </svg>
            Ribbon: a clinic's catch rate, week by week, with its 90% band
          </li>
          <li>
            <svg width="18" height="18" viewBox="0 0 18 18" aria-hidden="true">
              <path d="M1 7 L6 6 L11 6.5 L17 5" fill="none" className="stroke--estimate" strokeWidth="2" />
            </svg>
            Amber line: the AI's own estimate
          </li>
          <li className={hindsight ? undefined : "is-off"}>
            <svg width="18" height="18" viewBox="0 0 18 18" aria-hidden="true">
              <path d="M1 8 L6 9 L11 12 L17 15" fill="none" className="stroke--grades" strokeWidth="2.4" />
            </svg>
            Orange line: real catch rate {real}
          </li>
          <li>
            <svg width="18" height="18" viewBox="0 0 18 18" aria-hidden="true">
              <rect x="1" y="11" width="5" height="5" className="fill--drift" opacity="0.25" />
              <rect x="6.5" y="11" width="5" height="5" className="fill--drift" opacity="0.55" />
              <rect x="12" y="11" width="5" height="5" className="fill--drift" />
            </svg>
            Floor: drift, brighter when scans look unfamiliar
          </li>
          <li>
            <svg width="18" height="18" viewBox="0 0 18 18" aria-hidden="true">
              <circle cx="6" cy="7" r="3.5" className="fill--alarm" />
              <rect x="6" y="14" width="11" height="2" className="fill--alarm" />
            </svg>
            Red light and line: the alarm and the weeks after it
          </li>
          <li>
            <svg width="18" height="18" viewBox="0 0 18 18" aria-hidden="true">
              <rect x="7" y="2" width="4" height="14" fill="none" className="stroke--ink" strokeWidth="1.2" />
            </svg>
            Upright sheet: now; weeks run away from you
          </li>
        </ul>
      )}
    </details>
  );
}
