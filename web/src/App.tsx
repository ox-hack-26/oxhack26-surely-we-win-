import { useEffect, useState } from "react";
import type { Bundle } from "./data/types";
import { defaultCosts, setState, useStore, type State } from "./store";
import { Stage } from "./stage/Stage";
import { Drawer } from "./ui/Drawer";
import { Legend } from "./ui/Legend";
import { Rail } from "./ui/Rail";
import { Results } from "./ui/Results";
import { StageTools } from "./ui/StageTools";
import { StoryCard } from "./ui/Story";
import { Timeline } from "./ui/Timeline";
import { TopBar } from "./ui/TopBar";

/** Deep links for demos: ?week=9&clinic=US-WEAR-01&hindsight=1, or ?view=results. */
function fromUrl(bundle: Bundle): Partial<State> {
  const q = new URLSearchParams(window.location.search);
  const week = Number(q.get("week"));
  const clinic = q.get("clinic");
  return {
    ...(week >= 1 && week <= bundle.settings.n_weeks ? { week } : {}),
    ...(clinic && bundle.clinics.some((c) => c.clinic_id === clinic) ? { selected: clinic } : {}),
    ...(q.get("hindsight") === "1" ? { hindsight: true } : {}),
    ...(q.get("view") === "results" ? { view: "results" as const } : {}),
    ...(q.get("mode") === "history" ? { mode: "history" as const } : {}),
  };
}

export function App() {
  const bundle = useStore((s) => s.bundle);
  const view = useStore((s) => s.view);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch(`${import.meta.env.BASE_URL}data/clinicdrift.json`)
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json() as Promise<Bundle>;
      })
      .then((b) => setState({ bundle: b, costs: defaultCosts(b), ...fromUrl(b) }))
      .catch((e: Error) => setError(`Could not load the data (${e.message}). Run scripts/export_web.py, then reload.`));
  }, []);

  if (!bundle) {
    return (
      <div className="boot" role="status">
        {error ?? "Loading the clinics"}
      </div>
    );
  }

  return (
    <div className={`app view-${view}`}>
      <TopBar />
      <main className="main">
        <div className="stage-wrap">
          <Stage />
          <Legend />
          <StageTools />
          <StoryCard />
        </div>
        <Rail />
        <Drawer />
        {view === "results" && <Results />}
      </main>
      {view === "monitor" && <Timeline />}
    </div>
  );
}
