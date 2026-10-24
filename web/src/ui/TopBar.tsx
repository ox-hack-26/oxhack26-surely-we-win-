import { setState, useStore } from "../store";
import { startStory } from "./Story";

export function TopBar() {
  const view = useStore((s) => s.view);
  const hindsight = useStore((s) => s.hindsight);
  return (
    <header className="topbar">
      <div className="brand">
        <svg className="brand__mark" width="22" height="22" viewBox="0 0 22 22" aria-hidden="true">
          <circle cx="11" cy="11" r="9" fill="none" stroke="currentColor" strokeWidth="1.6" />
          <circle cx="11" cy="11" r="3.2" fill="currentColor" />
        </svg>
        <span className="brand__name">ClinicDrift</span>
        <span className="brand__line">Is the eye-screening AI still safe at each clinic?</span>
      </div>
      <nav className="seg" aria-label="View">
        <button type="button" aria-pressed={view === "monitor"} onClick={() => setState({ view: "monitor", story: null })}>
          Clinics
        </button>
        <button type="button" aria-pressed={view === "results"} onClick={() => setState({ view: "results", story: null, playing: false })}>
          Results
        </button>
      </nav>
      <label className="switch">
        <input type="checkbox" role="switch" checked={hindsight} onChange={(e) => setState({ hindsight: e.target.checked })} />
        <span className="switch__track" aria-hidden="true" />
        <span>Hindsight</span>
      </label>
      <button type="button" className="btn btn--primary" onClick={startStory}>
        Play the story
      </button>
    </header>
  );
}
