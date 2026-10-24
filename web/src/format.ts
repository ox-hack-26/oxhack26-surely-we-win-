// Number and date formats used everywhere, so every readout reads alike.

export const pct = (x: number | null | undefined, digits = 0): string =>
  x === null || x === undefined || Number.isNaN(x) ? "–" : `${(x * 100).toFixed(digits)}%`;

export const gbp = (x: number): string => {
  const sign = x < 0 ? "−" : "";
  const v = Math.abs(x);
  if (v >= 1_000_000) return `${sign}£${(v / 1_000_000).toFixed(2)}m`;
  if (v >= 10_000) return `${sign}£${Math.round(v / 1000)}k`;
  if (v >= 1000) return `${sign}£${v % 1000 === 0 ? v / 1000 : (v / 1000).toFixed(1)}k`;
  return `${sign}£${Math.round(v)}`;
};

export const num = (x: number, digits = 2): string => x.toFixed(digits);

export const int = (x: number): string => Math.round(x).toLocaleString("en-GB");

export const pad2 = (n: number): string => String(n).padStart(2, "0");

export const shortDate = (d: Date): string =>
  d.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });

export const REASON_LABEL = { drift: "Drift alarm", harm: "Harm alarm" } as const;
