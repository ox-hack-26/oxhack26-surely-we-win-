// Controls that sit on the 3D view: which view, and a way back after turning the camera.
import { setState, useStore } from "../store";

export function StageTools() {
  const mode = useStore((s) => s.mode);
  const orbited = useStore((s) => s.orbited);
  const story = useStore((s) => s.story);
  return (
    <>
      <div className="stage-tools">
        <div className="seg" role="group" aria-label="3D view">
          <button type="button" aria-pressed={mode === "globe"} onClick={() => setState({ mode: "globe", story: null })}>
            Globe
          </button>
          <button type="button" aria-pressed={mode === "now"} onClick={() => setState({ mode: "now", story: null })}>
            This week
          </button>
          <button type="button" aria-pressed={mode === "history"} onClick={() => setState({ mode: "history", story: null })}>
            All weeks
          </button>
        </div>
        <button type="button" className="btn btn--ghost btn--small" onClick={() => setState((s) => ({ cameraNonce: s.cameraNonce + 1 }))}>
          Reset view
        </button>
      </div>
      {!orbited && story === null && (
        <p className="stage-hint" aria-hidden="true">
          {mode === "globe" ? "Drag to turn, click a clinic" : mode === "now" ? "Drag to turn, scroll to zoom, click a clinic" : "Point at any week; click to open the clinic there"}
        </p>
      )}
    </>
  );
}
