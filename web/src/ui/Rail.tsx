import { useMemo } from "react";
import { realCatchRate, scorePolicies, weekDate } from "../data/model";
import type { Costs, Policy } from "../data/types";
import { gbp, num, pad2, pct, REASON_LABEL, shortDate } from "../format";
import { defaultCosts, setState, useBundle, useDecisions, useStore } from "../store";

export const POLICY_KEY: Record<Policy, string> = {
  ClinicDrift: "belief",
  "wait for grades": "grades",
  "watch drift": "drift",
  "watch estimate": "estimate",
};

export function Status({ reason }: { reason: "drift" | "harm" | null }) {
  return reason ? (
    <span className="status">
      <i className="status-dot status-dot--alarm" aria-hidden="true" />
      {REASON_LABEL[reason]}
    </span>
  ) : (
    <span className="status status--ok">
      <i className="status-dot status-dot--ok" aria-hidden="true" />
      OK
    </span>
  );
}

export function Rail() {
  const bundle = useBundle();
  const week = useStore((s) => s.week);
  const selected = useStore((s) => s.selected);
  const hovered = useStore((s) => s.hovered);
  const hindsight = useStore((s) => s.hindsight);
  const decisions = useDecisions();

  const rows = bundle.clinics.map((c) => ({ clinic: c, w: c.weeks[week - 1], d: decisions[c.clinic_id]?.weeks[week - 1] }));
  const alarms = rows.filter((r) => r.d?.alarm).length;
  const expectedMissed = rows.reduce((s, r) => s + r.w.belief_missed, 0);
  const realMissed = rows.reduce((s, r) => s + r.w.true_missed, 0);
  const scans = rows.reduce((s, r) => s + r.w.n_scans, 0);

  return (
    <aside className="rail" aria-label="Clinics this week">
      <section className="rail__section rail__now">
        <div>
          <div className="label">Week</div>
          <div className="num readout-xl">
            {pad2(week)}
            <span className="readout-xl__of">/{bundle.settings.n_weeks}</span>
          </div>
          <div className="muted">
            {shortDate(weekDate(bundle, week))}, <span className="num">{scans.toLocaleString("en-GB")}</span> scans
          </div>
        </div>
        <div className="rail__readouts">
          <div className="readout">
            <div className="readout__value num">
              {alarms}
              <span className="readout__of">/{bundle.clinics.length}</span>
            </div>
            <div className="readout__label">{alarms > 0 && <i className="status-dot status-dot--alarm status-dot--still" aria-hidden="true" />}Clinics on alarm</div>
          </div>
          <div className="readout">
            <div className="readout__value num">{num(expectedMissed, 1)}</div>
            <div className="readout__label">Missed cases expected this week</div>
          </div>
          {hindsight && (
            <div className="readout">
              <div className="readout__value num">{realMissed}</div>
              <div className="readout__label">
                <i className="key key--grades" aria-hidden="true" />
                Really missed this week
              </div>
            </div>
          )}
        </div>
      </section>

      <section className="rail__section" aria-labelledby="clinics-h">
        <div className="rail__head">
          <h2 id="clinics-h" className="title">Clinics</h2>
          <span className="rail__cols label" aria-hidden="true">
            <span>Catch rate</span>
            <span>Drift</span>
          </span>
        </div>
        <ul className="clinic-list">
          {rows.map(({ clinic, w, d }) => {
            const real = hindsight ? realCatchRate(clinic, week) : null;
            return (
              <li key={clinic.clinic_id}>
                <button
                  type="button"
                  className={`clinic-row${selected === clinic.clinic_id ? " is-selected" : ""}${hovered === clinic.clinic_id ? " is-hovered" : ""}`}
                  aria-pressed={selected === clinic.clinic_id}
                  onClick={() => setState({ selected: selected === clinic.clinic_id ? null : clinic.clinic_id, story: null })}
                  onMouseEnter={() => setState({ hovered: clinic.clinic_id })}
                  onMouseLeave={() => setState((s) => (s.hovered === clinic.clinic_id ? { hovered: null } : {}))}
                >
                  <span className="clinic-row__name">
                    <span className="clinic-row__id">{clinic.clinic_id}</span>
                    <span className="clinic-row__site">
                      {clinic.site}, {clinic.country}
                    </span>
                  </span>
                  <span className="clinic-row__status">
                    <Status reason={d?.alarm ? d.reason : null} />
                  </span>
                  <span className="clinic-row__value num">
                    {pct(w.catch_rate)}
                    {real !== null && <span className="clinic-row__real">{pct(real)}</span>}
                  </span>
                  <span className="clinic-row__value num">{num(w.drift_auc)}</span>
                </button>
              </li>
            );
          })}
        </ul>
        <p className="caption">
          Catch rate is ClinicDrift's belief{hindsight ? ", with the real rate over the last three weeks beneath it" : ""}. Drift above{" "}
          <span className="num">{bundle.settings.drift_untrusted}</span> means the scans look like nothing the AI was validated on.
        </p>
      </section>

      <CostPanel />
    </aside>
  );
}

const SLIDERS: { key: keyof Costs; label: string; hint: string; min: number; max: number; step: number; format: (v: number) => string }[] = [
  { key: "missed_case", label: "Missed case", hint: "Delayed treatment, risk to sight", min: 1000, max: 50000, step: 1000, format: gbp },
  { key: "false_referral", label: "False referral", hint: "A healthy patient sent to an eye clinic", min: 0, max: 1000, step: 10, format: gbp },
  { key: "review", label: "Review", hint: "Pull the AI and grade by hand while it is checked", min: 5000, max: 100000, step: 5000, format: gbp },
  { key: "horizon_weeks", label: "Horizon", hint: "How long a problem runs before grades show it", min: 2, max: 12, step: 1, format: (v) => `${v} weeks` },
];

function CostPanel() {
  const bundle = useBundle();
  const costs = useStore((s) => s.costs);
  const decisions = useDecisions();
  const scores = useMemo(() => scorePolicies(bundle, decisions, costs), [bundle, decisions, costs]);
  const base = defaultCosts(bundle);
  const changed = (Object.keys(base) as (keyof Costs)[]).some((k) => base[k] !== costs[k]);
  const max = Math.max(...scores.map((s) => s.cost), 1);
  const cd = scores.find((s) => s.policy === "ClinicDrift")!;
  const wait = scores.find((s) => s.policy === "wait for grades")!;
  const saving = wait.cost - cd.cost;

  return (
    <section className="rail__section" aria-labelledby="costs-h">
      <div className="rail__head">
        <h2 id="costs-h" className="title">Costs</h2>
        <button type="button" className="btn btn--ghost btn--small" disabled={!changed} onClick={() => setState({ costs: base })}>
          Reset
        </button>
      </div>
      <p className="caption">Illustrative prices. Move them and every alarm is decided again.</p>
      <div className="sliders">
        {SLIDERS.map((s) => (
          <label key={s.key} className="slider">
            <span className="slider__top">
              <span className="slider__label">{s.label}</span>
              <span className="num slider__value">{s.format(costs[s.key])}</span>
            </span>
            <input
              type="range"
              min={s.min}
              max={s.max}
              step={s.step}
              value={costs[s.key]}
              aria-valuetext={s.format(costs[s.key])}
              onChange={(e) => setState((st) => ({ costs: { ...st.costs, [s.key]: Number(e.target.value) }, story: null }))}
            />
            <span className="caption">{s.hint}</span>
          </label>
        ))}
      </div>

      <h3 className="subtitle">What each policy costs in this replay</h3>
      <ul className="policy-bars">
        {scores.map((s) => (
          <li key={s.policy} className="policy-bar">
            <span className="policy-bar__name">
              <i className={`key key--${POLICY_KEY[s.policy]}`} aria-hidden="true" />
              {s.policy}
            </span>
            <span className="num policy-bar__value">{gbp(s.cost)}</span>
            <span className="policy-bar__track" aria-hidden="true">
              <span className={`policy-bar__fill fill--${POLICY_KEY[s.policy]}`} style={{ transform: `scaleX(${s.cost / max})` }} />
            </span>
            <span className="caption policy-bar__meta">
              Caught <span className="num">{s.caught}</span> of <span className="num">{s.changed}</span>
              {s.falseAlarms > 0 && (
                <>
                  , <span className="num">{s.falseAlarms}</span> false alarm{s.falseAlarms > 1 ? "s" : ""}
                </>
              )}
              , <span className="num">{num(s.extraMissed, 1)}</span> extra missed cases
            </span>
          </li>
        ))}
      </ul>
      <p className="caption">
        {saving >= 0 ? (
          <>
            ClinicDrift costs <span className="num">{gbp(saving)}</span> less than waiting for grades at these prices.
          </>
        ) : (
          <>
            At these prices waiting for grades costs <span className="num">{gbp(-saving)}</span> less than ClinicDrift.
          </>
        )}{" "}
        One draw of which scans were graded; the Results page has <span className="num">{bundle.robustness?.n_draws ?? 100}</span>.
      </p>
    </section>
  );
}
