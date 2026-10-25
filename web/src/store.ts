// One small store shared by the DOM and the 3D scene (R3F's canvas is a separate React root,
// so plain context would not reach it). Components subscribe to the slice they read.
import { useSyncExternalStore } from "react";
import { decideAll, type Decisions } from "./data/model";
import type { Bundle, Costs } from "./data/types";

export type View = "monitor" | "results";
/** The 3D view: the clinics on a globe, this week's columns, or every week as ribbons. */
export type Mode = "world" | "now" | "history";

export interface State {
  bundle: Bundle | null;
  week: number;
  playing: boolean;
  selected: string | null;
  hovered: string | null;
  costs: Costs;
  view: View;
  story: number | null;
  hindsight: boolean;
  mode: Mode;
  /** Bumped by "Reset view": the camera flies back to its shot. */
  cameraNonce: number;
  /** Whether the person has dragged the camera yet (the hint hides once they have). */
  orbited: boolean;
}

const DEFAULT_COSTS: Costs = { missed_case: 10_000, false_referral: 150, review: 25_000, horizon_weeks: 6 };

let state: State = {
  bundle: null,
  week: 1,
  playing: false,
  selected: null,
  hovered: null,
  costs: DEFAULT_COSTS,
  view: "monitor",
  story: null,
  hindsight: false,
  mode: "world",
  cameraNonce: 0,
  orbited: false,
};
const listeners = new Set<() => void>();

export function getState(): State {
  return state;
}

export function setState(patch: Partial<State> | ((s: State) => Partial<State>)): void {
  const next = typeof patch === "function" ? patch(state) : patch;
  state = { ...state, ...next };
  listeners.forEach((l) => l());
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function useStore<T>(select: (s: State) => T): T {
  return useSyncExternalStore(subscribe, () => select(state));
}

export function defaultCosts(bundle: Bundle | null): Costs {
  return bundle ? { ...bundle.settings.costs } : DEFAULT_COSTS;
}

let cached: { bundle: Bundle; costs: Costs; decisions: Decisions } | null = null;

/** ClinicDrift's decisions under the current costs, recomputed only when the costs change. */
export function useDecisions(): Decisions {
  const bundle = useStore((s) => s.bundle);
  const costs = useStore((s) => s.costs);
  if (!bundle) return {};
  if (!cached || cached.bundle !== bundle || cached.costs !== costs) {
    cached = { bundle, costs, decisions: decideAll(bundle, costs) };
  }
  return cached.decisions;
}

export function useBundle(): Bundle {
  const bundle = useStore((s) => s.bundle);
  if (!bundle) throw new Error("The data bundle is not loaded yet");
  return bundle;
}

/** ?motion=full plays every animation even when the OS asks for reduced motion (for demos). */
export const fullMotion = (): boolean =>
  typeof window !== "undefined" && new URLSearchParams(window.location.search).get("motion") === "full";

export const reducedMotion = (): boolean =>
  typeof window !== "undefined" && !fullMotion() && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
