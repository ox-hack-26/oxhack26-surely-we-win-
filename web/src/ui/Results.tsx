// The backtest across many draws of which scans were graded: ranges, not one lucky run.
import { scaleLinear, scalePoint } from "d3-scale";
import { line } from "d3-shape";
import { useLayoutEffect, useRef, useState } from "react";
import type { Policy, RobustPolicy, SweepRow } from "../data/types";
import { POLICIES } from "../data/types";
import { gbp, num, pct } from "../format";
import { setState, useBundle } from "../store";
import { POLICY_KEY } from "./Rail";

function Range({ p, lo, hi, mid, max, format }: { p: Policy; lo: number; hi: number; mid: number; max: number; format: (v: number) => string }) {
  const at = (v: number) => `${(v / max) * 100}%`;
  return (
    <div className="range" aria-label={`${format(mid)}, range ${format(lo)} to ${format(hi)}`}>
      <span className="range__track" aria-hidden="true">
        <span className={`range__bar fill--${POLICY_KEY[p]}`} style={{ left: at(lo), right: `calc(100% - ${at(hi)})` }} />
        <span className={`range__dot fill--${POLICY_KEY[p]}`} style={{ left: at(mid) }} />
      </span>
      <span className="num range__value">{format(mid)}</span>
      {format(lo) !== format(hi) && (
        <span className="num caption range__span">
          {format(lo)}–{format(hi)}
        </span>
      )}
    </div>
  );
}

export function Results() {
  const bundle = useBundle();
  const robust = bundle.robustness;
  if (!robust) {
    return (
      <section className="results">
        <p>Run the pipeline to produce the robustness check.</p>
      </section>
    );
  }
  const policies = POLICIES.map((p) => robust.policies.find((r) => r.policy === p)).filter(Boolean) as RobustPolicy[];
  const cd = policies.find((p) => p.policy === "ClinicDrift")!;
  const wait = policies.find((p) => p.policy === "wait for grades")!;
  const maxMissed = Math.max(...policies.map((p) => p.missed_p95)) * 1.05;
  const maxCost = Math.max(...policies.map((p) => p.cost_p95)) * 1.05;
  const allCaught = cd.all_caught_share === 1;

  return (
    <section className="results" aria-labelledby="results-h">
      <div className="results__inner">
        <header className="results__head">
          <h1 id="results-h" className="display">
            {allCaught
              ? `ClinicDrift caught all ${cd.changes} changed clinics in all ${robust.n_draws} replays`
              : `ClinicDrift caught a median of ${cd.caught_median} of ${cd.changes} changed clinics`}
          </h1>
          <p className="results__lede">
            Which scans get an expert grade is chance, so the backtest was replayed {robust.n_draws} times with fresh draws. ClinicDrift
            let through a median of <span className="num">{num(cd.missed_median, 1)}</span> extra missed cases, against{" "}
            <span className="num">{num(wait.missed_median, 1)}</span> for waiting for grades, and cost{" "}
            <span className="num">{gbp(wait.cost_median - cd.cost_median)}</span> less.
          </p>
        </header>

        <div className="panel results__table-wrap">
          <table className="results__table">
            <caption className="visually-hidden">Each monitoring policy over {robust.n_draws} draws of the expert grades</caption>
            <thead>
              <tr>
                <th scope="col">Policy</th>
                <th scope="col">Changed clinics caught</th>
                <th scope="col">Any false alarm</th>
                <th scope="col">Extra missed cases, median and 90% range</th>
                <th scope="col">Total cost, median and 90% range</th>
              </tr>
            </thead>
            <tbody>
              {policies.map((p) => (
                <tr key={p.policy} className={p.policy === "ClinicDrift" ? "is-ours" : undefined}>
                  <th scope="row">
                    <i className={`key key--${POLICY_KEY[p.policy]}`} aria-hidden="true" />
                    {p.policy}
                  </th>
                  <td>
                    <span className="num readout-sm">{p.caught_median}</span>
                    <span className="caption">
                      {" "}
                      of <span className="num">{p.changes}</span>
                      {p.caught_min !== p.caught_max && (
                        <>
                          , <span className="num">{p.caught_min}</span> to <span className="num">{p.caught_max}</span>
                        </>
                      )}
                    </span>
                  </td>
                  <td className="num">{pct(p.any_false_alarm_share)}</td>
                  <td>
                    <Range p={p.policy} lo={p.missed_p5} hi={p.missed_p95} mid={p.missed_median} max={maxMissed} format={(v) => num(v, 1)} />
                  </td>
                  <td>
                    <Range p={p.policy} lo={p.cost_p5} hi={p.cost_p95} mid={p.cost_median} max={maxCost} format={gbp} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="results__grid">
          <div className="panel">
            <SweepChart rows={bundle.sweep} />
          </div>
          <div className="panel results__notes">
            <h2 className="title">What each policy does</h2>
            <dl className="defs">
              <div><dt><i className="key key--belief" />ClinicDrift</dt><dd>Blends the AI's own estimate, drift and the grades that have arrived into one belief, then pulls the AI when carrying on costs more than a review.</dd></div>
              <div><dt><i className="key key--grades" />Wait for grades</dt><dd>Today's practice: alarm when the graded catch rate over 8 weeks is clearly below validated.</dd></div>
              <div><dt><i className="key key--drift" />Watch drift</dt><dd>Alarm when the scans stop looking validated for two weeks running.</dd></div>
              <div><dt><i className="key key--estimate" />Watch estimate</dt><dd>Alarm when the AI's own catch-rate estimate drops clearly below validated.</dd></div>
            </dl>
            <h2 className="title">Read with care</h2>
            <ul className="caveats">
              <li>Model: {bundle.model.model}, validation AUC <span className="num">{num(bundle.model.val_auc)}</span>.</li>
              <li>The clinics are a replay of public datasets (EyePACS, APTOS, Messidor-2, IDRiD), with camera wear and a software update added on purpose.</li>
              <li>Costs are illustrative. Change them on the Clinics page and every alarm is decided again.</li>
            </ul>
            <button type="button" className="btn btn--ghost" onClick={() => setState({ view: "monitor", story: null })}>
              Back to the clinics
            </button>
          </div>
        </div>
      </div>
    </section>
  );
}

function SweepChart({ rows }: { rows: SweepRow[] }) {
  const ref = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(560);
  const [hover, setHover] = useState<number | null>(null);
  useLayoutEffect(() => {
    if (!ref.current) return;
    const ro = new ResizeObserver(([e]) => setWidth(Math.max(280, Math.floor(e.contentRect.width))));
    ro.observe(ref.current);
    return () => ro.disconnect();
  }, []);
  const prices = [...new Set(rows.map((r) => r.review_cost))].sort((a, b) => a - b);
  const height = 260;
  const m = { top: 16, right: 132, bottom: 30, left: 52 };
  const x = scalePoint<number>().domain(prices).range([m.left, width - m.right]);
  const max = Math.max(...rows.map((r) => r.total_cost_gbp)) * 1.08;
  const y = scaleLinear().domain([0, max]).range([height - m.bottom, m.top]).nice();
  const ticks = y.ticks(4);
  const series = POLICIES.map((p) => ({ policy: p, rows: rows.filter((r) => r.policy === p).sort((a, b) => a.review_cost - b.review_cost) })).filter((s) => s.rows.length);

  // Direct labels at the line ends, nudged apart so they never overlap.
  const ends = series.map((s) => ({ policy: s.policy, y: y(s.rows[s.rows.length - 1].total_cost_gbp) })).sort((a, b) => a.y - b.y);
  for (let i = 1; i < ends.length; i++) ends[i].y = Math.max(ends[i].y, ends[i - 1].y + 16);

  return (
    <figure className="chart">
      <figcaption className="chart__head">
        <span className="title">Total cost as the price of a review changes</span>
        <span className="caption">Median over the draws, other costs fixed</span>
      </figcaption>
      <div className="chart__body" ref={ref}>
        <svg width={width} height={height} className="chart__svg" role="img" aria-label="Total cost of each policy at review prices from 5 to 100 thousand pounds">
          {ticks.map((t) => (
            <g key={t}>
              <line x1={m.left} x2={width - m.right} y1={y(t)} y2={y(t)} className="chart__grid" />
              <text x={m.left - 8} y={y(t)} dy="0.32em" textAnchor="end" className="chart__tick">
                {gbp(t)}
              </text>
            </g>
          ))}
          <line x1={m.left} x2={width - m.right} y1={height - m.bottom} y2={height - m.bottom} className="chart__axis" />
          {prices.map((p) => (
            <text key={p} x={x(p)} y={height - m.bottom + 18} textAnchor="middle" className="chart__tick">
              {gbp(p)}
            </text>
          ))}
          {hover !== null && <line x1={x(hover)} x2={x(hover)} y1={m.top} y2={height - m.bottom} className="chart__crosshair" />}
          {series.map((s) => (
            <g key={s.policy}>
              <path d={line<SweepRow>().x((r) => x(r.review_cost)!).y((r) => y(r.total_cost_gbp))(s.rows) ?? ""} className={`chart__line chart__line--${POLICY_KEY[s.policy]}`} />
              {s.rows.map((r) => (
                <circle key={r.review_cost} cx={x(r.review_cost)} cy={y(r.total_cost_gbp)} r={4} className={`chart__dot chart__dot--${POLICY_KEY[s.policy]}`} />
              ))}
            </g>
          ))}
          {ends.map((e) => (
            <g key={e.policy} transform={`translate(${width - m.right + 10}, ${e.y})`}>
              <rect x={0} y={-1.5} width={10} height={3} rx={1.5} className={`fill--${POLICY_KEY[e.policy]}`} />
              <text x={16} dy="0.32em" className="chart__label">
                {e.policy}
              </text>
            </g>
          ))}
          {prices.map((p) => (
            <rect
              key={p}
              x={(x(p) ?? 0) - x.step() / 2}
              y={m.top}
              width={x.step()}
              height={height - m.top - m.bottom}
              fill="transparent"
              onPointerEnter={() => setHover(p)}
              onPointerLeave={() => setHover(null)}
            />
          ))}
        </svg>
        {hover !== null && (
          <div className="tooltip chart__tooltip" style={{ transform: `translateX(${Math.min((x(hover) ?? 0) + 12, width - 220)}px)` }} role="status">
            <div className="tooltip__title">
              Review at <span className="num">{gbp(hover)}</span>
            </div>
            <dl className="tooltip__rows">
              {series.map((s) => {
                const r = s.rows.find((row) => row.review_cost === hover)!;
                return (
                  <div key={s.policy}>
                    <dt><i className={`key key--${POLICY_KEY[s.policy]}`} />{s.policy}</dt>
                    <dd className="num">{gbp(r.total_cost_gbp)}</dd>
                  </div>
                );
              })}
            </dl>
          </div>
        )}
      </div>
    </figure>
  );
}
