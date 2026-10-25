import { useEffect, useRef, useState } from "react";
import type { AlarmFile, Clinic, ScanStats } from "../data/types";
import { gbp, num, pad2, pct, REASON_LABEL } from "../format";
import { setState, useBundle, useDecisions, useStore } from "../store";
import { CatchChart, DriftChart } from "./charts";
import { Status } from "./Rail";

/** A scan, or, when its file isn't there (only IDRiD images are in the public repo, for dataset
 *  licences), a placeholder that says why rather than a broken image. */
function ScanImage({ id, alt }: { id: string; alt: string }) {
  const [missing, setMissing] = useState(false);
  if (missing)
    return (
      <span className="scan-missing" role="img" aria-label={`${alt}: image not included`}>
        Licensed image, not in the public repo
      </span>
    );
  return <img src={scanUrl(id)} alt={alt} loading="lazy" onError={() => setMissing(true)} />;
}

// Same rule as web_name() in scripts/export_web.py.
const scanUrl = (id: string) => `${import.meta.env.BASE_URL}scans/${id.replace("@", "_w")}.jpg`;

export function Drawer() {
  const bundle = useBundle();
  const selected = useStore((s) => s.selected);
  const last = useRef<string | null>(null);
  if (selected) last.current = selected;
  const clinic = bundle.clinics.find((c) => c.clinic_id === (selected ?? last.current));
  const closeRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!selected) return;
    closeRef.current?.focus({ preventScroll: true });
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setState({ selected: null });
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [selected]);

  return (
    <aside className={`drawer${selected ? " is-open" : ""}`} aria-label={clinic ? `${clinic.clinic_id} detail` : "Clinic detail"} aria-hidden={!selected}>
      {clinic && <ClinicDetail clinic={clinic} closeRef={closeRef} />}
    </aside>
  );
}

function ClinicDetail({ clinic, closeRef }: { clinic: Clinic; closeRef: React.RefObject<HTMLButtonElement> }) {
  const bundle = useBundle();
  const week = useStore((s) => s.week);
  const hindsight = useStore((s) => s.hindsight);
  const costs = useStore((s) => s.costs);
  const decision = useDecisions()[clinic.clinic_id];
  const w = clinic.weeks[week - 1];
  const d = decision?.weeks[week - 1];
  const alarmFile = bundle.alarms.find((a) => a.clinic_id === clinic.clinic_id && a.week <= week);
  const wearStrip = bundle.scans.filter((id) => id.startsWith("eyepacs-15898"));

  return (
    <div className="detail">
      <header className="detail__head">
        <div>
          <h2 className="heading">{clinic.clinic_id}</h2>
          <p className="muted">
            {clinic.site}, {clinic.country}. Week <span className="num">{pad2(week)}</span>, <span className="num">{w.n_scans}</span> scans.
          </p>
        </div>
        <Status reason={d?.alarm ? d.reason : null} />
        <button ref={closeRef} type="button" className="btn btn--ghost btn--icon" onClick={() => setState({ selected: null })} aria-label="Close clinic detail">
          <svg width="14" height="14" viewBox="0 0 14 14" aria-hidden="true">
            <path d="M2 2l10 10M12 2L2 12" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
          </svg>
        </button>
      </header>

      {d?.alarm && d.reason && decision.firstAlarm && (
        <section className="alarm-card" aria-label="Alarm">
          <div className="alarm-card__title">
            <i className="status-dot status-dot--alarm" aria-hidden="true" />
            {REASON_LABEL[d.reason]} since week <span className="num">{pad2(decision.firstAlarm)}</span>
          </div>
          <p>
            {d.reason === "drift"
              ? "Outside validated conditions: the catch rate can't be verified."
              : `ClinicDrift is ${pct(clinic.weeks[decision.firstAlarm - 1].p_below_standard)} sure the catch rate is below the ${pct(bundle.settings.min_catch_rate)} standard.`}{" "}
            Recommend pausing the AI for review.
          </p>
          <div className="alarm-card__numbers">
            <div>
              <div className="num readout-sm">{gbp(decision.weeks[decision.firstAlarm - 1].harm)}</div>
              <div className="caption">Expected cost of carrying on {costs.horizon_weeks} weeks, at the alarm</div>
            </div>
            <div>
              <div className="num readout-sm">{gbp(costs.review)}</div>
              <div className="caption">Cost of a review</div>
            </div>
          </div>
        </section>
      )}

      <section className="detail__readouts" aria-label="This week">
        <div className="readout">
          <div className="readout__value num">{pct(w.catch_rate)}</div>
          <div className="readout__label"><i className="key key--belief" aria-hidden="true" />ClinicDrift</div>
          <div className="caption num">{pct(w.catch_low)}–{pct(w.catch_high)}</div>
        </div>
        <div className="readout">
          <div className="readout__value num">{pct(w.est_sensitivity)}</div>
          <div className="readout__label"><i className="key key--estimate" aria-hidden="true" />AI's own estimate</div>
        </div>
        <div className="readout">
          <div className="readout__value num">{num(w.drift_auc)}</div>
          <div className="readout__label"><i className="key key--drift" aria-hidden="true" />Drift</div>
        </div>
        <div className="readout">
          <div className="readout__value num">
            {w.graded_caught}/{w.graded_cases}
          </div>
          <div className="readout__label"><i className="key key--grades" aria-hidden="true" />Graded cases caught</div>
          <div className="caption">From the last 8 weeks</div>
        </div>
      </section>

      <p className="detail__note">{clinic.note}.</p>

      <CatchChart clinic={clinic} week={week} hindsight={hindsight} decision={decision} />
      <DriftChart clinic={clinic} week={week} hindsight={hindsight} decision={decision} />

      {alarmFile && <AlarmScans alarm={alarmFile} />}
      {clinic.wear_from_week && wearStrip.length > 1 && (
        <section className="scans">
          <h3 className="subtitle">What camera wear does to one eye</h3>
          <div className="scan-strip">
            {wearStrip.map((id) => (
              <figure key={id} className="scan">
                <ScanImage id={id} alt={`The same retina at camera wear level ${id.split("@")[1] ?? "0"}`} />
                <figcaption className="caption">
                  Wear <span className="num">{id.split("@")[1] ?? "0.00"}</span>
                </figcaption>
              </figure>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}

const STATS: { key: keyof ScanStats; label: string; format: (v: number) => string }[] = [
  { key: "mean_brightness", label: "Brightness", format: (v) => num(v) },
  { key: "mean_contrast", label: "Contrast", format: (v) => num(v, 3) },
  { key: "mean_quality", label: "Image quality", format: (v) => num(v) },
  { key: "mean_resolution_px", label: "Width, pixels", format: (v) => Math.round(v).toLocaleString("en-GB") },
  { key: "referral_rate", label: "Referred", format: (v) => pct(v) },
];

function AlarmScans({ alarm }: { alarm: AlarmFile }) {
  const bundle = useBundle();
  const have = (ids: string[]) => ids.filter((id) => bundle.scans.includes(id));
  const flagged = have(alarm.flagged_scan_ids);
  const typical = have(alarm.reference_scan_ids);
  return (
    <section className="scans">
      <h3 className="subtitle">
        Scans behind the alarm, week <span className="num">{pad2(alarm.week)}</span>
      </h3>
      <div className="scan-compare">
        <div>
          <div className="label">Least like the validated scans</div>
          <div className="scan-grid">
            {flagged.map((id) => (
              <ScanImage key={id} id={id} alt={`Flagged retina scan ${id}`} />
            ))}
          </div>
        </div>
        <div>
          <div className="label">Typical validated scans</div>
          <div className="scan-grid">
            {typical.map((id) => (
              <ScanImage key={id} id={id} alt={`Validated retina scan ${id}`} />
            ))}
          </div>
        </div>
      </div>
      <table className="stats-table">
        <thead>
          <tr>
            <th scope="col"><span className="visually-hidden">Measure</span></th>
            <th scope="col">This week</th>
            <th scope="col">Validated</th>
          </tr>
        </thead>
        <tbody>
          {STATS.map((s) => (
            <tr key={s.key}>
              <th scope="row">{s.label}</th>
              <td className="num">{s.format(alarm.flagged_scan_stats[s.key])}</td>
              <td className="num">{s.format(alarm.training_scan_stats[s.key])}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
