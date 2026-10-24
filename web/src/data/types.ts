// The shape of public/data/clinicdrift.json, written by scripts/export_web.py.

export type AlarmReason = "drift" | "harm";
export type Policy = "ClinicDrift" | "wait for grades" | "watch drift" | "watch estimate";
export const POLICIES: Policy[] = ["ClinicDrift", "wait for grades", "watch drift", "watch estimate"];

export interface Week {
  week: number;
  week_start: string;
  n_scans: number;
  est_sensitivity: number;
  est_low: number;
  est_high: number;
  catch_rate: number;
  catch_low: number;
  catch_high: number;
  true_sensitivity: number | null;
  true_cases: number;
  true_missed: number;
  true_false_referrals: number;
  drift_auc: number;
  quality_mean: number;
  referral_rate: number;
  referral_threshold: number;
  expected_cases: number;
  belief_cases: number;
  belief_missed: number;
  expected_harm: number;
  p_below_standard: number;
  trust: number;
  graded_cases: number;
  graded_caught: number;
  alarm: boolean;
  alarm_this_week: boolean;
  alarm_reason: AlarmReason | null;
  grades_complete_week: number | null;
}

export interface Clinic {
  clinic_id: string;
  site: string;
  country: string;
  note: string;
  segments: { source: string; first_week: number }[];
  scans_per_week: number;
  wear_from_week: number | null;
  update_from_week: number | null;
  switch_week: number | null;
  changed_week: number | null;
  alarm_weeks: Record<Exclude<Policy, "ClinicDrift">, number[]>;
  weeks: Week[];
}

export interface ScanStats {
  n_scans: number;
  mean_brightness: number;
  mean_contrast: number;
  mean_sharpness: number;
  mean_quality: number;
  mean_resolution_px: number;
  referral_score_mean: number;
  referral_rate: number;
}

export interface AlarmFile {
  clinic_id: string;
  week: number;
  alarm_reason: AlarmReason;
  drift_auc: number;
  flagged_scan_stats: ScanStats;
  training_scan_stats: ScanStats;
  flagged_scan_ids: string[];
  reference_scan_ids: string[];
}

export interface Costs {
  missed_case: number;
  false_referral: number;
  review: number;
  horizon_weeks: number;
}

export interface RobustPolicy {
  policy: Policy;
  changes: number;
  caught_median: number;
  caught_min: number;
  caught_max: number;
  all_caught_share: number;
  false_alarms_mean: number;
  any_false_alarm_share: number;
  median_weeks_to_alarm: number | null;
  missed_median: number;
  missed_p5: number;
  missed_p95: number;
  cost_median: number;
  cost_p5: number;
  cost_p95: number;
}

export interface RobustClinic {
  policy: Policy;
  clinic_id: string;
  changed_week: number;
  alarm_share: number;
  false_alarm_share: number;
  first_alarm_median: number | null;
  first_alarm_p5: number | null;
  first_alarm_p95: number | null;
}

export interface SweepRow {
  review_cost: number;
  policy: Policy;
  clinics_caught: number;
  clinics_changed: number;
  false_alarms: number;
  extra_missed_cases: number;
  total_cost_gbp: number;
}

export interface Bundle {
  generated: string;
  model: { model: string; referral_threshold: number; val_auc: number; val_sensitivity: number; val_specificity: number };
  settings: {
    costs: Costs;
    reference: { catch_rate: number; specificity: number; prevalence: number };
    drift_trusted: number;
    drift_untrusted: number;
    min_catch_rate: number;
    confidence: number;
    n_weeks: number;
    first_monday: string;
  };
  clinics: Clinic[];
  alarms: AlarmFile[];
  robustness: { n_draws: number; policies: RobustPolicy[]; clinics: RobustClinic[] } | null;
  sweep: SweepRow[];
  scans: string[];
}
