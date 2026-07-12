/** Types gebaseerd op de echte response-shapes van core/views.py (Fase 3). */

export interface IcuEvent {
  id: string | number;
  category?: string;
  start_date_local?: string;
  name?: string;
  type?: string;
  description?: string | null;
  load_target?: number | null;
  workout_doc?: { duration?: number } | null;
  moving_time?: number | null;
}

export interface IcuActivity {
  id: string | number;
  start_date_local?: string;
  name?: string;
  type?: string;
  icu_training_load?: number | null;
  moving_time?: number | null;
  distance?: number | null;
  average_heartrate?: number | null;
}

export interface Placement {
  event_id: string;
  date?: string | null;
  slot_start?: string | null;
  session_kind?: string | null;
  locked?: number;
  solver_score?: number | null;
  solver_notes?: string | null;
  goal_id?: number | null;
}

export interface WorkoutProfileStep {
  sec: number;
  pct: number;
}

/** core.views._event_summary() */
export interface EventSummary {
  event: IcuEvent;
  activity: IcuActivity | null;
  done: boolean;
  is_note: boolean;
  unplanned: boolean;
  placement: Placement | null;
  placement_reason?: string | null;
  profile?: WorkoutProfileStep[];
}

export interface Recovery {
  score: number;
  level: "go" | "easy" | "rust";
  message: string;
}

export interface CheckinRecord {
  sleep_score?: number | null;
  energy?: number | null;
  soreness?: number | null;
  motivation?: number | null;
  notes?: string | null;
  [key: string]: unknown;
}

export interface InjuryGuard {
  status: "groen" | "geel" | "rood";
  message?: string;
  active_signals: string[];
  days_symptom_free?: number | null;
}

/** GET /api/today */
export interface TodayView {
  date: string;
  workout: (EventSummary & { coach_note: string | null }) | null;
  checkin: {
    done: boolean;
    score: number | null;
    record: CheckinRecord | null;
    recovery: Recovery;
  };
  injury_guard: InjuryGuard | null;
  tomorrow: EventSummary[];
}

export interface AvailabilitySlot {
  start: string;
  end: string;
  context: "any" | "indoor_only" | "outdoor_only";
}

/** GET /api/week/{week_start} */
export interface WeekView {
  week_start: string;
  items: EventSummary[];
  placements: Placement[];
  availability: Record<string, AvailabilitySlot[]>;
  warnings?: { code?: string; dag?: string | null; message: string }[];
}

export interface MoveDiffEntry {
  event_id: string;
  event_name: string;
  from: string;
  to: string;
  from_time: string;
  to_time: string;
}

export interface SolverPlacement {
  event_id: string;
  naam: string;
  date: string;
  slot_start: string;
  kind?: string;
  sport?: string;
  score?: number;
  moved_days?: number;
  notes?: string;
}

/** POST /api/placements/{id}/move (core.replan.move_event) */
export interface MoveResult {
  status: "OPTIMAL" | "FEASIBLE" | "INFEASIBLE";
  diff: MoveDiffEntry[];
  placements: SolverPlacement[];
  dropped: { event_id: string; naam: string; reason: string }[];
  applied: boolean;
  errors: string[];
}

export type SwapCategory = "makkelijker" | "vergelijkbaar" | "harder";

export interface SwapChosen {
  naam?: string;
  beschrijving?: string;
  tss_geschat?: number;
  sport?: string;
  duur_min?: number;
}

/** POST /api/placements/{id}/swap (core.swap_service.perform_swap) */
export interface SwapResult {
  ok: boolean;
  message: string;
  chosen: SwapChosen | null;
  new_tss: number | null;
  phase_warning: string;
  undo: Record<string, unknown> | null;
}

/** POST /api/checkin (core.views.process_checkin) */
export interface CheckinResult {
  date: string;
  checkin_score: number | null;
  recovery: Recovery;
  injury_guard: InjuryGuard & {
    volume_modifier?: number;
    flags?: string[];
  };
}

export interface PlanWeekRow {
  week_start: string;
  phase?: string;
  is_deload?: boolean | number;
  tss_target_min?: number;
  tss_target_max?: number;
  run_km?: number;
  run_sessions?: number;
  long_run_km?: number;
  bike_sessions?: number;
  intensity_gate?: string;
  [key: string]: unknown;
}

export type GoalType =
  | "marathon"
  | "half"
  | "10k"
  | "5k"
  | "gran_fondo"
  | "ftp"
  | "triathlon"
  | "custom";

export interface Goal {
  id: number;
  type: GoalType | string;
  sport: "run" | "ride" | "multi" | string;
  event_date: string;
  target_value?: string | null;
  priority: "A" | "B" | "C";
  status: string;
  created_at?: string | null;
}

export interface CtlActualPoint {
  date: string;
  ctl: number;
  tsb: number;
}

export interface CtlTargetPoint {
  week_start: string;
  ctl: number;
}

/** GET /api/season — macroplan + CTL-paden + haalbaarheid. */
export interface SeasonView {
  goal: Goal;
  weeks_to_goal?: number;
  current_ctl?: number;
  plan_weeks: PlanWeekRow[];
  ctl_actual: CtlActualPoint[];
  ctl_target_path: CtlTargetPoint[];
  advice?: string;
}

export interface GoalCreate {
  type: GoalType;
  sport: "run" | "ride" | "multi";
  event_date: string;
  target_value?: string | null;
  priority: "A" | "B" | "C";
}

/** POST /api/goals (core.views.create_goal_with_plan) */
export interface GoalCreateResult {
  goal: Goal;
  generation: {
    plan_weeks: number;
    warnings: string[];
    peak_km: number;
  } | null;
}

/** POST /api/goals/{id}/regenerate (core.replan_goal.weekly_recalibration) */
export interface RegenerateResult {
  status: "no_goal" | "within_band" | "replanned" | "injury_adjusted";
  deviation_pct?: number;
  deviations?: Record<string, number>;
  advice?: string;
  notes?: string[];
  warnings?: string[];
  regenerated_from?: string | null;
}

/** GET /api/trends (core.views.trends_view) */
export interface TrendPoint {
  date: string;
  ctl: number;
  atl: number;
  tsb: number;
  tss?: number;
}

export interface WeeklyVolumeRow {
  week_start: string;
  tss: number;
  run_km: number;
  hours: number;
}

export interface HrvPoint {
  date: string;
  hrv: number;
  resting_hr?: number | null;
}

export interface ThresholdObservation {
  id: number;
  date: string;
  activity_id: string;
  pace_delta_sec?: number | null;
  hr_reps_avg?: number | null;
  hr_vs_band?: "onder" | "in" | "boven" | string | null;
  rpe?: number | null;
  completed: number | boolean;
  target_pace_sec?: number | null;
  observed_pace_sec?: number | null;
}

export interface ThresholdTrendContext {
  sentence: string;
  recent_observations: ThresholdObservation[];
  faster_count: number;
  slower_count: number;
  required_count: number;
  window_size: number;
  window_days: number;
}

export interface ThresholdDossier {
  threshold_pace_sec_per_km: number;
  default_sec_per_km: number;
  log: ThresholdPaceLog[];
  observations: ThresholdObservation[];
  suggestion: ThresholdSuggestion | null;
  context: ThresholdTrendContext;
}

export interface TrendsView {
  source: string;
  load: {
    ctl_estimate?: number;
    atl_estimate?: number;
    tsb_estimate?: number;
    weekly_tss_target?: number;
    [key: string]: unknown;
  };
  ctl_series: TrendPoint[];
  weekly_volume: WeeklyVolumeRow[];
  hrv: HrvPoint[];
  threshold: ThresholdDossier;
  athlete: { ftp: number; hrmax: number };
  tp_sync_enabled: boolean;
}

/** GET /api/checkin/history */
export interface CheckinHistoryView {
  days: number;
  records: (CheckinRecord & {
    date: string;
    checkin_score?: number | null;
  })[];
  signals: { date: string; signals?: string[] }[];
  injury_guard: InjuryGuard | null;
}

/** GET /api/availability/pattern — let op: andere veldnamen dan overrides. */
export interface PatternSlot {
  slot_start: string;
  slot_end: string;
  context: "any" | "indoor_only" | "outdoor_only";
}

export interface PatternView {
  pattern: Record<string, PatternSlot[]>;
}

export interface FixedSession {
  weekday: number;
  name: string;
  sport: "Run" | "Ride" | "VirtualRide" | string;
  duration_min: number;
  if_estimate: number;
  enabled: boolean | number;
}

export interface FixedSessionsView {
  fixed_sessions: FixedSession[];
}

export interface ThresholdSuggestion {
  id: number;
  date: string;
  old_sec: number;
  proposed_sec: number;
  reason: string;
  source: string;
  status: "pending" | "accepted" | "dismissed" | string;
}

export interface ThresholdPaceLog {
  id: number;
  date: string;
  old_sec: number;
  new_sec: number;
  reason: string;
  source: string;
}

export interface ThresholdPaceView {
  threshold_pace_sec_per_km: number;
  default_sec_per_km: number;
  log: ThresholdPaceLog[];
  suggestion: ThresholdSuggestion | null;
}

/** Antwoord na een drempelmutatie: het weekplan draagt absolute paces, dus
 *  een gewijzigde drempel vraagt om een herplan. */
export interface ThresholdMutationResult {
  threshold_pace_sec_per_km: number;
  replan_needed: boolean;
  replan_week_start: string | null;
}

/** POST /api/week/{week_start}/plan */
export interface PlanWeekResult {
  week_start: string;
  planned_sessions: number;
  events: unknown[];
  warnings?: { code?: string; message: string }[];
}

export interface OverrideResult {
  date: string;
  slots: AvailabilitySlot[];
}
