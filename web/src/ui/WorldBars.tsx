// The numbers behind the globe: this week's catch rate at every clinic as a bar with its 90% band,
// against the 80% standard. Bars move with the replay; pointing at one highlights it on the globe.
import { realCatchRate } from "../data/model";
import { pad2, pct, REASON_LABEL } from "../format";
import { rowOrder } from "../stage/layout";
import { setState, useBundle, useDecisions, useStore } from "../store";

export function WorldBars() {
  const bundle = useBundle();
  const week = useStore((s) => s.week);
  const hindsight = useStore((s) => s.hindsight);
  const focus = useStore((s) => s.hovered ?? s.selected);
  const decisions = useDecisions();
  const standard = bundle.settings.min_catch_rate;

  return (
    <section className="world-bars panel" aria-label={`Catch rate at each clinic, week ${week}`}>
      <header className="world-bars__head">
        <span className="title">
          Catch rate, week <span className="num">{pad2(week)}</span>
        </span>
        <span className="chart__legend">
          <span><i className="key key--belief" />ClinicDrift, 90% band</span>
          {hindsight && <span><i className="key key--grades key--dot" />Real</span>}
        </span>
      </header>
      <div className="world-bars__plot">
        <div className="world-bars__axis" aria-hidden="true">
          <span className="num" style={{ bottom: "100%" }}>100%</span>
          <span className="num" style={{ bottom: `${standard * 100}%` }}>{pct(standard)}</span>
          <span className="num" style={{ bottom: "0%" }}>0%</span>
        </div>
        <div className="world-bars__bars">
          <span className="world-bars__standard" style={{ top: `calc(var(--bar-track) * ${1 - standard})` }} aria-hidden="true" />
          {rowOrder(bundle.clinics).map((clinic) => {
            const w = clinic.weeks[week - 1];
            const d = decisions[clinic.clinic_id]?.weeks[week - 1];
            const real = hindsight ? realCatchRate(clinic, week) : null;
            const id = clinic.clinic_id;
            const [country, name, number] = id.split("-");
            const tone = focus === id ? " is-focus" : focus ? " is-dim" : "";
            return (
              <button
                key={id}
                type="button"
                className={`world-bar${tone}`}
                aria-label={`${id}: ${pct(w.catch_rate)}, ${d?.alarm && d.reason ? REASON_LABEL[d.reason] : "OK"}`}
                onMouseEnter={() => setState({ hovered: id })}
                onMouseLeave={() => setState((s) => (s.hovered === id ? { hovered: null } : {}))}
                onClick={() => setState({ selected: id, story: null })}
              >
                <span className="world-bar__track">
                  <span className="world-bar__band" style={{ transform: `translateY(${-w.catch_low * 100}%) scaleY(${w.catch_high - w.catch_low})` }} />
                  <span className="world-bar__fill" style={{ transform: `scaleY(${w.catch_rate})` }} />
                  {real !== null && (
                    <span className="world-bar__real" style={{ transform: `translateY(${-real * 100}%)` }}>
                      <i />
                    </span>
                  )}
                </span>
                <span className="world-bar__value num">{pct(w.catch_rate)}</span>
                <span className="world-bar__label">
                  <span className="world-bar__country">
                    {d?.alarm && <i className="status-dot status-dot--alarm status-dot--still" aria-hidden="true" />}
                    {country}
                  </span>
                  <span>{name}</span>
                  <span className="num">{number}</span>
                </span>
              </button>
            );
          })}
        </div>
      </div>
    </section>
  );
}
