// The engine's cost-loss decision and backtest, mirrored from clinicdrift/engine/decide.py and
// backtest.py so the cost sliders can recompute alarms in the browser. Only the costs change
// here: the beliefs (catch rate, trust, P(below standard)) come from the engine as they are.
import type { AlarmReason, Bundle, Clinic, Costs, Policy, Week } from "./types";
import { POLICIES } from "./types";

export interface Decision {
  harm: number;
  alarmThisWeek: boolean;
  alarm: boolean;
  reason: AlarmReason | null;
}

export interface ClinicDecisions {
  weeks: Decision[];
  firstAlarm: number | null;
}

/** decide.decide_clinic's alarm rule for one clinic, alarms latched until reviewed. */
export function decideClinic(clinic: Clinic, costs: Costs, settings: Bundle["settings"]): ClinicDecisions {
  const ref = settings.reference;
  let latched = false;
  let reason: AlarmReason | null = null;
  let firstAlarm: number | null = null;
  const weeks = clinic.weeks.map((w) => {
    const referred = w.referral_rate * w.n_scans;
    const usualFalse = w.n_scans * (1 - ref.prevalence) * (1 - ref.specificity);
    const weekly =
      costs.missed_case * w.belief_cases * (ref.catch_rate - w.catch_rate) +
      costs.false_referral * (referred - w.catch_rate * w.belief_cases - usualFalse);
    const harm = costs.horizon_weeks * weekly;
    const drifted = w.trust < 0.5;
    const now = harm > costs.review && (drifted || w.p_below_standard >= settings.confidence);
    if (now) {
      reason = drifted ? "drift" : "harm";
      if (!latched) firstAlarm = w.week;
      latched = true;
    }
    return { harm, alarmThisWeek: now, alarm: latched, reason: latched ? reason : null };
  });
  return { weeks, firstAlarm };
}

export type Decisions = Record<string, ClinicDecisions>;

export function decideAll(bundle: Bundle, costs: Costs): Decisions {
  return Object.fromEntries(bundle.clinics.map((c) => [c.clinic_id, decideClinic(c, costs, bundle.settings)]));
}

/** backtest.true_weekly_harm: hindsight harm per week beyond what the validated AI would cause. */
function trueHarm(w: Week, ref: Bundle["settings"]["reference"], costs: Costs) {
  const usualMissed = w.true_cases * (1 - ref.catch_rate);
  const usualFalse = (w.n_scans - w.true_cases) * (1 - ref.specificity);
  const extraMissed = Math.max(0, w.true_missed - usualMissed);
  const extraFalse = Math.max(0, w.true_false_referrals - usualFalse);
  return { harm: costs.missed_case * extraMissed + costs.false_referral * extraFalse, extraMissed };
}

export interface PolicyScore {
  policy: Policy;
  caught: number;
  changed: number;
  falseAlarms: number;
  extraMissed: number;
  cost: number;
  firstAlarms: Record<string, number | null>;
}

/** backtest.score + summary for this replay's grades, under the given costs. */
export function scorePolicies(bundle: Bundle, decisions: Decisions, costs: Costs): PolicyScore[] {
  const ref = bundle.settings.reference;
  return POLICIES.map((policy) => {
    const score: PolicyScore = { policy, caught: 0, changed: 0, falseAlarms: 0, extraMissed: 0, cost: 0, firstAlarms: {} };
    for (const clinic of bundle.clinics) {
      const alarm =
        policy === "ClinicDrift" ? decisions[clinic.clinic_id].firstAlarm : (clinic.alarm_weeks[policy][0] ?? null);
      score.firstAlarms[clinic.clinic_id] = alarm;
      const changed = clinic.changed_week;
      const falseAlarm = alarm !== null && (changed === null || alarm < changed);
      if (changed !== null) score.changed += 1;
      if (falseAlarm) score.falseAlarms += 1;
      if (changed !== null && alarm !== null && !falseAlarm) score.caught += 1;
      if (alarm !== null) score.cost += costs.review;
      if (changed === null || falseAlarm) continue;
      const last = alarm !== null ? alarm - 1 : bundle.settings.n_weeks;
      for (const w of clinic.weeks) {
        if (w.week < changed || w.week > last) continue;
        const h = trueHarm(w, ref, costs);
        score.cost += h.harm;
        score.extraMissed += h.extraMissed;
      }
    }
    return score;
  });
}

/** Real catch rate pooled over the weeks up to `week` (hindsight: from every scan's true grade). */
export function realCatchRate(clinic: Clinic, week: number, pool = 3): number | null {
  let cases = 0;
  let missed = 0;
  for (const w of clinic.weeks) {
    if (w.week > week - pool && w.week <= week) {
      cases += w.true_cases;
      missed += w.true_missed;
    }
  }
  return cases > 0 ? (cases - missed) / cases : null;
}

export function weekDate(bundle: Bundle, week: number): Date {
  const d = new Date(`${bundle.settings.first_monday}T00:00:00`);
  d.setDate(d.getDate() + (week - 1) * 7);
  return d;
}
