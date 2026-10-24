// The clinic's two time charts. One axis each, recessive grid, 2px lines, a crosshair and
// tooltip on hover, and only the weeks that have happened so far.
import { scaleLinear } from "d3-scale";
import { area, line } from "d3-shape";
import { useLayoutEffect, useRef, useState, type ReactNode } from "react";
import type { ClinicDecisions } from "../data/model";
import type { Clinic, Week } from "../data/types";
import { gbp, num, pad2, pct } from "../format";
import { useBundle } from "../store";

const M = { top: 14, right: 20, bottom: 26, left: 44 };

function useWidth<T extends HTMLElement>() {
  const ref = useRef<T>(null);
  const [width, setWidth] = useState(520);
  useLayoutEffect(() => {
    if (!ref.current) return;
    const ro = new ResizeObserver(([entry]) => setWidth(Math.max(260, Math.floor(entry.contentRect.width))));
    ro.observe(ref.current);
    return () => ro.disconnect();
  }, []);
  return [ref, width] as const;
}

interface ChartProps {
  clinic: Clinic;
  week: number;
  hindsight: boolean;
  decision: ClinicDecisions | undefined;
}

function Frame({
  width,
  height,
  n,
  week,
  y,
  yTicks,
  yFormat,
  children,
  onHover,
  hover,
}: {
  width: number;
  height: number;
  n: number;
  week: number;
  y: (v: number) => number;
  yTicks: number[];
  yFormat: (v: number) => string;
  children: (x: (w: number) => number) => ReactNode;
  onHover: (w: number | null) => void;
  hover: number | null;
}) {
  const x = scaleLinear().domain([1, n]).range([M.left, width - M.right]);
  const xTicks = [1, 5, 10, 15, n].filter((v, i, a) => v <= n && a.indexOf(v) === i);
  const onMove = (e: React.PointerEvent<SVGRectElement>) => {
    const box = e.currentTarget.getBoundingClientRect();
    const w = Math.round(x.invert(e.clientX - box.left + M.left));
    onHover(Math.max(1, Math.min(week, w)));
  };
  return (
    <svg width={width} height={height} className="chart__svg" role="img">
      {yTicks.map((t) => (
        <g key={t}>
          <line x1={M.left} x2={width - M.right} y1={y(t)} y2={y(t)} className="chart__grid" />
          <text x={M.left - 8} y={y(t)} dy="0.32em" textAnchor="end" className="chart__tick">
            {yFormat(t)}
          </text>
        </g>
      ))}
      <line x1={M.left} x2={width - M.right} y1={height - M.bottom} y2={height - M.bottom} className="chart__axis" />
      {xTicks.map((t) => (
        <text key={t} x={x(t)} y={height - M.bottom + 16} textAnchor="middle" className="chart__tick">
          {pad2(t)}
        </text>
      ))}
      {children((w) => x(w))}
      <line x1={x(week)} x2={x(week)} y1={M.top - 6} y2={height - M.bottom} className="chart__now" />
      {hover !== null && <line x1={x(hover)} x2={x(hover)} y1={M.top} y2={height - M.bottom} className="chart__crosshair" />}
      <rect
        x={M.left}
        y={M.top}
        width={Math.max(0, x(week) - M.left + 8)}
        height={height - M.top - M.bottom}
        fill="transparent"
        onPointerMove={onMove}
        onPointerLeave={() => onHover(null)}
      />
    </svg>
  );
}

function Tooltip({ left, children }: { left: number; children: ReactNode }) {
  return (
    <div className="tooltip chart__tooltip" style={{ transform: `translateX(${left}px)` }} role="status">
      {children}
    </div>
  );
}

export function CatchChart({ clinic, week, hindsight, decision }: ChartProps) {
  const bundle = useBundle();
  const [ref, width] = useWidth<HTMLDivElement>();
  const [hover, setHover] = useState<number | null>(null);
  const height = 236;
  const n = bundle.settings.n_weeks;
  const y = scaleLinear().domain([0, 1]).range([height - M.bottom, M.top]);
  const known = clinic.weeks.filter((w) => w.week <= week);
  const standard = bundle.settings.min_catch_rate;
  const alarmWeek = decision?.firstAlarm && decision.firstAlarm <= week ? decision.firstAlarm : null;
  const xOf = scaleLinear().domain([1, n]).range([M.left, width - M.right]);
  const h = hover !== null ? clinic.weeks[hover - 1] : null;

  return (
    <figure className="chart">
      <figcaption className="chart__head">
        <span className="title">Catch rate</span>
        <span className="chart__legend">
          <span><i className="key key--belief" />ClinicDrift, 90% band</span>
          <span><i className="key key--estimate" />AI's own estimate</span>
          {hindsight && <span><i className="key key--grades key--dot" />Real, per week</span>}
        </span>
      </figcaption>
      <div className="chart__body" ref={ref}>
        <Frame width={width} height={height} n={n} week={week} y={y} yTicks={[0, 0.2, 0.4, 0.6, 0.8, 1]} yFormat={(v) => pct(v)} onHover={setHover} hover={hover}>
          {(x) => (
            <>
              {hindsight && clinic.changed_week && clinic.changed_week <= n && (
                <g>
                  <rect x={x(clinic.changed_week) - 6} y={M.top} width={Math.max(0, x(n) - x(clinic.changed_week) + 6)} height={height - M.top - M.bottom} className="chart__changed" />
                  <text x={x(clinic.changed_week) - 2} y={M.top + 12} className="chart__note">
                    Conditions changed
                  </text>
                </g>
              )}
              <line x1={M.left} x2={width - M.right} y1={y(standard)} y2={y(standard)} className="chart__standard" />
              <text x={width - M.right} y={y(standard) - 6} textAnchor="end" className="chart__note">
                {pct(standard)} standard
              </text>
              <path
                d={area<Week>().x((w) => x(w.week)).y0((w) => y(w.catch_low)).y1((w) => y(w.catch_high))(known) ?? ""}
                className="chart__band"
              />
              <path d={line<Week>().x((w) => x(w.week)).y((w) => y(w.est_sensitivity))(known) ?? ""} className="chart__line chart__line--estimate" />
              <path d={line<Week>().x((w) => x(w.week)).y((w) => y(w.catch_rate))(known) ?? ""} className="chart__line chart__line--belief" />
              {hindsight &&
                known
                  .filter((w) => w.true_sensitivity !== null)
                  .map((w) => <circle key={w.week} cx={x(w.week)} cy={y(w.true_sensitivity!)} r={4} className="chart__dot chart__dot--grades" />)}
              {alarmWeek && (
                <g>
                  <line x1={x(alarmWeek)} x2={x(alarmWeek)} y1={height - M.bottom} y2={height - M.bottom - 12} className="chart__alarm" />
                  <circle cx={x(alarmWeek)} cy={height - M.bottom - 14} r={4} className="chart__alarm-dot" />
                </g>
              )}
              {h && (
                <>
                  <circle cx={x(h.week)} cy={y(h.catch_rate)} r={4.5} className="chart__dot chart__dot--belief" />
                  <circle cx={x(h.week)} cy={y(h.est_sensitivity)} r={4.5} className="chart__dot chart__dot--estimate" />
                </>
              )}
            </>
          )}
        </Frame>
        {h && (
          <Tooltip left={Math.min(Math.max(0, xOf(h.week) + 12), width - 210)}>
            <div className="tooltip__title">
              Week <span className="num">{pad2(h.week)}</span>
            </div>
            <dl className="tooltip__rows">
              <div><dt><i className="key key--belief" />ClinicDrift</dt><dd className="num">{pct(h.catch_rate)} <span className="tooltip__sub">{pct(h.catch_low)}–{pct(h.catch_high)}</span></dd></div>
              <div><dt><i className="key key--estimate" />AI's own estimate</dt><dd className="num">{pct(h.est_sensitivity)}</dd></div>
              {hindsight && <div><dt><i className="key key--grades" />Real</dt><dd className="num">{pct(h.true_sensitivity)} <span className="tooltip__sub">of {h.true_cases}</span></dd></div>}
              <div><dt>Grades in</dt><dd className="num">{h.graded_caught}/{h.graded_cases} caught</dd></div>
              <div><dt>Expected harm</dt><dd className="num">{gbp(decision?.weeks[h.week - 1].harm ?? h.expected_harm)}</dd></div>
            </dl>
          </Tooltip>
        )}
      </div>
    </figure>
  );
}

export function DriftChart({ clinic, week }: ChartProps) {
  const bundle = useBundle();
  const [ref, width] = useWidth<HTMLDivElement>();
  const [hover, setHover] = useState<number | null>(null);
  const height = 150;
  const n = bundle.settings.n_weeks;
  const lo = Math.min(0.3, ...clinic.weeks.map((w) => w.drift_auc));
  const y = scaleLinear().domain([lo, 1]).range([height - M.bottom, M.top]);
  const known = clinic.weeks.filter((w) => w.week <= week);
  const xOf = scaleLinear().domain([1, n]).range([M.left, width - M.right]);
  const h = hover !== null ? clinic.weeks[hover - 1] : null;
  const { drift_trusted: trusted, drift_untrusted: untrusted } = bundle.settings;

  return (
    <figure className="chart">
      <figcaption className="chart__head">
        <span className="title">Drift</span>
        <span className="chart__legend">
          <span><i className="key key--drift" />How easily this week's scans are told from validated ones</span>
        </span>
      </figcaption>
      <div className="chart__body" ref={ref}>
        <Frame width={width} height={height} n={n} week={week} y={y} yTicks={[0.4, 0.6, 0.8, 1].filter((t) => t >= lo)} yFormat={(v) => num(v, 1)} onHover={setHover} hover={hover}>
          {(x) => (
            <>
              <rect x={M.left} y={y(1)} width={width - M.left - M.right} height={y(untrusted) - y(1)} className="chart__zone" />
              <line x1={M.left} x2={width - M.right} y1={y(trusted)} y2={y(trusted)} className="chart__standard" />
              <line x1={M.left} x2={width - M.right} y1={y(untrusted)} y2={y(untrusted)} className="chart__standard" />
              <text x={width - M.right} y={y(untrusted) + 14} textAnchor="end" className="chart__note">
                Estimate ignored above <tspan className="num">{untrusted}</tspan>
              </text>
              <text x={width - M.right} y={y(trusted) + 14} textAnchor="end" className="chart__note">
                Trusted below <tspan className="num">{trusted}</tspan>
              </text>
              <path d={line<Week>().x((w) => x(w.week)).y((w) => y(w.drift_auc))(known) ?? ""} className="chart__line chart__line--drift" />
              {h && <circle cx={x(h.week)} cy={y(h.drift_auc)} r={4.5} className="chart__dot chart__dot--drift" />}
            </>
          )}
        </Frame>
        {h && (
          <Tooltip left={Math.min(Math.max(0, xOf(h.week) + 12), width - 210)}>
            <div className="tooltip__title">
              Week <span className="num">{pad2(h.week)}</span>
            </div>
            <dl className="tooltip__rows">
              <div><dt><i className="key key--drift" />Drift</dt><dd className="num">{num(h.drift_auc)}</dd></div>
              <div><dt>Trust in the estimate</dt><dd className="num">{pct(h.trust)}</dd></div>
              <div><dt>Image quality</dt><dd className="num">{num(h.quality_mean)}</dd></div>
            </dl>
          </Tooltip>
        )}
      </div>
    </figure>
  );
}
