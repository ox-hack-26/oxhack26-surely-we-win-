import { useEffect, useState } from "react";
import { pad2, pct } from "../format";
import { useStore } from "../store";

type GeminiRecord = {
  clinic_id: string;
  week: number;
  model: string;
  likely_cause: string;
  category: string;
  confidence: number;
  evidence: string[];
  recommended_checks: string[];
  report_md: string;
};

/** The report as plain text: markdown headings, quotes, bold and table rules dropped. */
const plain = (md: string) =>
  md
    .replace(/^(#+|>)\s*/gm, "")
    .replace(/\*\*(.+?)\*\*/g, "$1")
    .replace(/^\s*\|?[-:| ]+\|?\s*$/gm, "")
    .replace(/\n{3,}/g, "\n\n")
    .trim();

const base = `${import.meta.env.BASE_URL}data/gemini/`;

/** Gemini's suggested cause and draft incident report, from scripts/export_gemini_web.py, in the
 *  corner of the stage. Shows the selected clinic's report, else the first one already raised by
 *  this week; only alarms that were rerun on Gemini have one. */
export function AiReport() {
  const week = useStore((s) => s.week);
  const selected = useStore((s) => s.selected);
  const story = useStore((s) => s.story);
  const [records, setRecords] = useState<GeminiRecord[]>([]);
  const [closed, setClosed] = useState<string | null>(null);
  // Starts as a compact bar, so it never covers the opening globe; opens when that clinic is opened.
  const [min, setMin] = useState(true);

  useEffect(() => {
    fetch(`${base}index.json`)
      .then((r) => (r.ok ? r.json() : []))
      .then((index: { clinic_id: string }[]) =>
        Promise.all(index.map((i) => fetch(`${base}${i.clinic_id}.json`).then((r) => r.json()))),
      )
      .then(setRecords)
      .catch(() => {});
  }, []);

  useEffect(() => {
    if (selected && records.some((r) => r.clinic_id === selected)) setMin(false);
  }, [selected, records]);

  const raised = records.filter((r) => r.week <= week);
  const record = raised.find((r) => r.clinic_id === selected) ?? (selected ? undefined : raised[0]);
  const key = record && `${record.clinic_id}-${record.week}`;
  if (!record || closed === key || story !== null) return null; // the story card has this corner

  return (
    <section className={`ai-report${min ? " is-min" : ""}`} aria-label="AI report">
      <header className="ai-report__head">
        <h2 className="ai-report__title">Your AI report is here</h2>
        <button type="button" className="btn btn--ghost btn--icon" onClick={() => setMin(!min)} aria-label={min ? "Expand AI report" : "Minimise AI report"} aria-expanded={!min}>
          <svg width="14" height="14" viewBox="0 0 14 14" aria-hidden="true">
            <path d={min ? "M3 9l4-4 4 4" : "M3 5l4 4 4-4"} stroke="currentColor" strokeWidth="1.6" fill="none" strokeLinecap="round" />
          </svg>
        </button>
        <button type="button" className="btn btn--ghost btn--icon" onClick={() => setClosed(key!)} aria-label="Close AI report">
          <svg width="14" height="14" viewBox="0 0 14 14" aria-hidden="true">
            <path d="M2 2l10 10M12 2L2 12" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
          </svg>
        </button>
      </header>
      {!min && (
        <div className="ai-report__body">
          <div>
            <strong>{record.clinic_id}</strong>, alarm in week <span className="num">{pad2(record.week)}</span>
          </div>
          <div>
            <strong>Likely cause:</strong> {record.category} (<span className="num">{pct(record.confidence)}</span> confidence)
          </div>
          <div>{record.likely_cause}</div>
          <div>
            <strong>First checks</strong>
            <ol>
              {record.recommended_checks.map((c) => (
                <li key={c}>{c}</li>
              ))}
            </ol>
          </div>
          <div className="ai-report__text">{plain(record.report_md)}</div>
          <div className="caption">Drafted by Gemini ({record.model}) · draft for human review</div>
        </div>
      )}
    </section>
  );
}
