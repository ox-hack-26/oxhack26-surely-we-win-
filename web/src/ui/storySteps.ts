// The guided story. Every number in it is read from the data, so it stays true when the model
// changes; a step whose clinic is missing is left out.
import { decideAll, realCatchRate } from "../data/model";
import type { Bundle } from "../data/types";
import { gbp, pct } from "../format";
import type { View } from "../store";

export interface StoryStep {
  title: string;
  body: string;
  week: number;
  shot: "home" | "back" | string;
  hindsight: boolean;
  view: View;
}

const WEAR = "US-WEAR-01";
const UPDATE = "US-UPD-01";

const cache = new WeakMap<Bundle, StoryStep[]>();

export function storySteps(bundle: Bundle): StoryStep[] {
  const hit = cache.get(bundle);
  if (hit) return hit;
  const costs = bundle.settings.costs;
  const decisions = decideAll(bundle, costs);
  const n = bundle.settings.n_weeks;
  const standard = pct(bundle.settings.min_catch_rate);
  const steps: StoryStep[] = [];
  const at = (id: string, week: number) => bundle.clinics.find((c) => c.clinic_id === id)?.weeks[week - 1];

  steps.push({
    title: `${bundle.clinics.length} clinics, one eye-screening AI`,
    body: `Each column is a clinic. Its height is the share of people with referable diabetic retinopathy that ClinicDrift believes the AI is catching this week, and the sleeve around it is how unsure it is. The flat plane is the UK screening standard: ${standard}.`,
    week: 1,
    shot: "home",
    hindsight: false,
    view: "monitor",
  });
  steps.push({
    title: "The truth arrives five to seven weeks late",
    body: "Experts grade one scan in ten, and each grade takes 35 to 49 days to come back. Until then nobody knows the real catch rate, so a clinic can fail for weeks before anyone sees it.",
    week: 6,
    shot: "home",
    hindsight: false,
    view: "monitor",
  });

  const dayOne = bundle.clinics.filter((c) => c.changed_week === 1);
  if (dayOne.length) {
    const sites = [...new Set(dayOne.map((c) => c.site))];
    const caught = dayOne.filter((c) => decisions[c.clinic_id].firstAlarm === 1).length;
    const list = sites.length > 1 ? `${sites.slice(0, -1).join(", ")} and ${sites[sites.length - 1]}` : sites[0];
    steps.push({
      title: `${dayOne.length} clinics are different from day one`,
      body: `Their scans come from other cameras and other people (${list}). The aqua halo on the floor is drift: how easily a classifier tells this week's scans from the ones the AI was validated on. ClinicDrift raises a drift alarm at ${caught === dayOne.length ? "all" : caught} of them in week 1.`,
      week: 1,
      shot: "back",
      hindsight: false,
      view: "monitor",
    });
  }

  const wear = bundle.clinics.find((c) => c.clinic_id === WEAR);
  const wearAlarm = decisions[WEAR]?.firstAlarm;
  if (wear?.wear_from_week && wearAlarm) {
    const start = at(WEAR, wear.wear_from_week)!;
    const alarm = at(WEAR, wearAlarm)!;
    steps.push({
      title: `Week ${wear.wear_from_week}: the camera at ${WEAR} starts to wear`,
      body: `Each week its scans get a little blurrier and darker. The AI's own estimate (the amber ring) does not notice: it still says ${pct(start.est_sensitivity)}.`,
      week: wear.wear_from_week,
      shot: WEAR,
      hindsight: false,
      view: "monitor",
    });
    steps.push({
      title: `Week ${wearAlarm}: ClinicDrift pulls the AI for review`,
      body: `Drift reaches ${alarm.drift_auc.toFixed(2)}: these scans look like nothing the AI was validated on, so its catch rate can't be verified. Carrying on for ${costs.horizon_weeks} more weeks has an expected cost of ${gbp(decisions[WEAR].weeks[wearAlarm - 1].harm)}, more than a ${gbp(costs.review)} review.`,
      week: wearAlarm,
      shot: WEAR,
      hindsight: false,
      view: "monitor",
    });
    const last = at(WEAR, n)!;
    const real = realCatchRate(wear, n);
    const waited = wear.alarm_weeks["wait for grades"][0];
    const arrives = last.grades_complete_week;
    steps.push({
      title: "Hindsight: it really was failing",
      body: `By week ${n} the real catch rate at ${WEAR} is ${pct(real)} over the last three weeks (the orange ring), while the AI's own estimate still says ${pct(last.est_sensitivity)}. ${arrives ? `The grades that show it arrive in week ${arrives}.` : ""} ${waited ? `Waiting for grades raises the alarm in week ${waited}.` : "Waiting for grades never raises the alarm in this replay."}`.replace(/\s+/g, " ").trim(),
      week: n,
      shot: WEAR,
      hindsight: true,
      view: "monitor",
    });
  }

  const update = bundle.clinics.find((c) => c.clinic_id === UPDATE);
  const updAlarm = decisions[UPDATE]?.firstAlarm;
  if (update?.update_from_week && updAlarm) {
    const start = at(UPDATE, update.update_from_week)!;
    const alarm = at(UPDATE, updAlarm)!;
    steps.push({
      title: `Week ${update.update_from_week}: a software update at ${UPDATE}`,
      body: `The update raises the referral cut-off, so the AI refers fewer people. The scans look exactly as before, so drift stays low (${start.drift_auc.toFixed(2)}): a drift monitor alone can't see this.`,
      week: update.update_from_week,
      shot: UPDATE,
      hindsight: false,
      view: "monitor",
    });
    steps.push({
      title: `Week ${updAlarm}: a harm alarm, on evidence`,
      body: `The expert grades that have arrived make ClinicDrift ${pct(alarm.p_below_standard)} sure the catch rate is below the ${standard} standard, and carrying on has an expected cost of ${gbp(decisions[UPDATE].weeks[updAlarm - 1].harm)}. That is enough to pull it.`,
      week: updAlarm,
      shot: UPDATE,
      hindsight: false,
      view: "monitor",
    });
  }

  const robust = bundle.robustness;
  const cd = robust?.policies.find((p) => p.policy === "ClinicDrift");
  const wait = robust?.policies.find((p) => p.policy === "wait for grades");
  if (robust && cd && wait) {
    steps.push({
      title: `Across ${robust.n_draws} redraws of which scans were graded`,
      body: `ClinicDrift caught ${cd.all_caught_share === 1 ? `all ${cd.changes}` : `a median of ${cd.caught_median} of ${cd.changes}`} changed clinics${cd.all_caught_share === 1 ? " in every draw" : ""}, with a false alarm in ${pct(cd.any_false_alarm_share)} of draws. Waiting for grades caught a median of ${wait.caught_median}.`,
      week: n,
      shot: "home",
      hindsight: false,
      view: "results",
    });
  }

  cache.set(bundle, steps);
  return steps;
}

export function storyCamera(index: number, bundle: Bundle | null): string | null {
  if (!bundle) return null;
  const step = storySteps(bundle)[index];
  return step && step.shot !== "home" ? step.shot : null;
}
