import { useEffect } from "react";
import { defaultCosts, getState, setState, useBundle, useStore } from "../store";
import { storySteps } from "./storySteps";

export function goToStep(index: number | null): void {
  const bundle = getState().bundle;
  if (!bundle || index === null) {
    setState({ story: null, view: "monitor" });
    return;
  }
  const steps = storySteps(bundle);
  const step = steps[Math.max(0, Math.min(index, steps.length - 1))];
  setState({
    story: steps.indexOf(step),
    week: step.week,
    hindsight: step.hindsight,
    view: step.view,
    mode: "now",
    selected: null,
    hovered: null,
    playing: false,
  });
}

/** The story is told with the engine's own costs, so its numbers match the write-up. */
export function startStory(): void {
  setState((s) => ({ costs: defaultCosts(s.bundle) }));
  goToStep(0);
}

export function StoryCard() {
  const bundle = useBundle();
  const story = useStore((s) => s.story);
  const steps = storySteps(bundle);

  useEffect(() => {
    if (story === null) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement) return;
      if (e.key === "ArrowRight") goToStep(story + 1);
      else if (e.key === "ArrowLeft") goToStep(story - 1);
      else if (e.key === "Escape") goToStep(null);
      else return;
      e.preventDefault();
      e.stopImmediatePropagation();
    };
    window.addEventListener("keydown", onKey, true);
    return () => window.removeEventListener("keydown", onKey, true);
  }, [story]);

  if (story === null) return null;
  const step = steps[story];
  const last = story === steps.length - 1;
  return (
    <section className="story panel" aria-live="polite" aria-label="Story" key={story}>
      <div className="story__meta">
        <span className="label">Story</span>
        <span className="num story__count">
          {story + 1}/{steps.length}
        </span>
      </div>
      <h2 className="story__title">{step.title}</h2>
      <p className="story__body">{step.body}</p>
      <div className="story__actions">
        <button type="button" className="btn btn--ghost" onClick={() => goToStep(story - 1)} disabled={story === 0}>
          Back
        </button>
        {last ? (
          <button type="button" className="btn btn--primary" onClick={() => goToStep(null)}>
            Explore on your own
          </button>
        ) : (
          <button type="button" className="btn btn--primary" onClick={() => goToStep(story + 1)}>
            Next
          </button>
        )}
        <button type="button" className="btn btn--quiet story__exit" onClick={() => goToStep(null)}>
          Exit story
        </button>
      </div>
    </section>
  );
}
