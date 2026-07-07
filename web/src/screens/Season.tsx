import { useMemo, useState } from "react";
import {
  Bar,
  BarChart,
  Cell,
  ComposedChart,
  Line,
  ReferenceArea,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { isUnavailable } from "../api/client";
import {
  useDeleteGoal,
  useGoals,
  useRegenerateGoal,
  useSeason,
} from "../api/queries";
import type {
  Goal,
  PlanWeekRow,
  RegenerateResult,
  SeasonView,
} from "../api/types";
import BottomSheet from "../components/BottomSheet";
import OfflineBanner, { useOnline } from "../components/OfflineBanner";
import Spinner from "../components/Spinner";
import GoalWizardSheet from "../features/GoalWizardSheet";
import { dayMonth, longDate, mondayOf, todayISO } from "../lib/dates";
import { GOAL_LABEL, fmtPhase, phaseColor } from "../lib/season";

export default function Season() {
  const { data, isLoading, isError, error, refetch } = useSeason();
  const goals = useGoals();
  const online = useOnline();
  const [wizardOpen, setWizardOpen] = useState(false);
  const [selectedWeek, setSelectedWeek] = useState<PlanWeekRow | null>(null);
  const [regenResult, setRegenResult] = useState<RegenerateResult | null>(null);
  const regenerate = useRegenerateGoal();
  const deleteGoal = useDeleteGoal();

  if (isLoading) return <Spinner label="Seizoen laden…" />;

  if (!data) {
    return (
      <div className="py-16 text-center">
        <p className="font-display text-xl font-semibold">Geen verbinding</p>
        <p className="mx-auto mt-2 max-w-[260px] text-sm leading-relaxed text-muted">
          Het macroplan is nu niet op te halen.
        </p>
        <button
          onClick={() => refetch()}
          className="mt-6 rounded-xl border border-line-strong px-5 py-2.5 text-sm font-medium hover:border-accent"
        >
          Opnieuw proberen
        </button>
      </div>
    );
  }

  const stale = !online || (isError && isUnavailable(error));
  // id 0 = fallback-plan (core.plan_provider.DEFAULT_GOAL): nog geen echt doel.
  const hasRealGoal = (data.goal?.id ?? 0) > 0;
  const subGoals = (goals.data?.goals ?? []).filter(
    (g) => g.priority !== "A" && g.status === "active",
  );
  const goalActionBusy = regenerate.isPending || deleteGoal.isPending;

  const confirmDeleteGoal = () => {
    if (!hasRealGoal) return;
    const label = GOAL_LABEL[data.goal.type] ?? data.goal.type;
    const ok = window.confirm(
      `Verwijder doel "${label}"? Het bijbehorende macroplan wordt ook verwijderd.`,
    );
    if (ok) deleteGoal.mutate(data.goal.id);
  };

  return (
    <div>
      <OfflineBanner show={stale} />

      <GoalHeader view={data} hasRealGoal={hasRealGoal} />

      {!hasRealGoal && (
        <EmptyGoalCard onOpenWizard={() => setWizardOpen(true)} />
      )}

      <PhaseTimeline
        weeks={data.plan_weeks}
        goal={data.goal}
        subGoals={subGoals}
        onSelect={setSelectedWeek}
      />

      <CtlChart view={data} />

      <VolumeBars weeks={data.plan_weeks} />

      <div className="rise-in-late mt-7 flex gap-2.5">
        {hasRealGoal && (
          <button
            data-testid="regenerate-plan"
            onClick={() =>
              regenerate.mutate(data.goal.id, {
                onSuccess: (res) => setRegenResult(res),
              })
            }
            disabled={goalActionBusy}
            className="flex-1 rounded-xl border border-line-strong py-3 text-sm font-semibold transition-colors hover:border-accent disabled:opacity-50"
          >
            {regenerate.isPending ? "Herberekenen…" : "Herbereken plan"}
          </button>
        )}
        {hasRealGoal && (
          <button
            data-testid="delete-goal"
            onClick={confirmDeleteGoal}
            disabled={goalActionBusy}
            className="flex-1 rounded-xl border border-alert/50 py-3 text-sm font-semibold text-alert transition-colors hover:bg-alert/10 disabled:opacity-50"
          >
            {deleteGoal.isPending ? "Verwijderen..." : "Verwijder doel"}
          </button>
        )}
        <button
          data-testid="open-goal-wizard"
          onClick={() => setWizardOpen(true)}
          disabled={goalActionBusy}
          className={`flex-1 rounded-xl py-3 text-sm font-semibold transition-colors ${
            hasRealGoal
              ? "border border-line-strong hover:border-accent"
              : "bg-accent text-white hover:bg-accent-hover"
          }`}
        >
          Nieuw doel
        </button>
      </div>
      {regenerate.isError && (
        <p className="mt-2.5 text-[0.78rem] text-alert">
          Herberekenen mislukt — probeer het later opnieuw.
        </p>
      )}

      {deleteGoal.isError && (
        <p className="mt-2.5 text-[0.78rem] text-alert">
          Doel verwijderen mislukt - probeer het later opnieuw.
        </p>
      )}

      <GoalWizardSheet open={wizardOpen} onClose={() => setWizardOpen(false)} />
      <WeekDetailSheet week={selectedWeek} onClose={() => setSelectedWeek(null)} />
      <RegenResultSheet result={regenResult} onClose={() => setRegenResult(null)} />
    </div>
  );
}

// ── Doel-header + haalbaarheid ────────────────────────────────────────────

function GoalHeader({
  view,
  hasRealGoal,
}: {
  view: SeasonView;
  hasRealGoal: boolean;
}) {
  const goal = view.goal;
  const advice = view.advice ?? "";
  const onTrack = advice.startsWith("Op schema");

  return (
    <header className="rise-in mb-6">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="font-mono text-[0.66rem] uppercase tracking-[0.2em] text-dim">
            macroplan{!hasRealGoal && " · standaardplan"}
          </p>
          <h1 className="font-display mt-1.5 text-2xl font-semibold">
            {GOAL_LABEL[goal.type] ?? goal.type}
            {goal.target_value && (
              <span className="ml-2.5 font-mono text-[1.05rem] font-medium text-accent">
                {goal.target_value}
              </span>
            )}
          </h1>
          <p className="mt-1.5 font-mono text-[0.74rem] text-muted">
            {longDate(goal.event_date)}
            {view.weeks_to_goal != null && (
              <>
                {" · "}
                <span className="text-ink">{view.weeks_to_goal} weken</span> te
                gaan
              </>
            )}
          </p>
        </div>
        <span
          data-testid="feasibility-badge"
          title={advice}
          className={`mt-1 inline-flex shrink-0 items-center gap-1.5 rounded-full border px-2.5 py-1 font-mono text-[0.62rem] font-medium uppercase tracking-[0.12em] ${
            onTrack
              ? "border-positive/40 bg-positive/10 text-positive"
              : "border-warning/40 bg-warning/10 text-warning"
          }`}
        >
          <span className="h-1.5 w-1.5 rounded-full bg-current" />
          {onTrack ? "op koers" : "let op"}
        </span>
      </div>

      {!onTrack && advice && (
        <p className="mt-3 rounded-xl border border-warning/40 bg-warning/10 px-3.5 py-2.5 text-[0.8rem] leading-relaxed text-warning">
          {advice}
        </p>
      )}
    </header>
  );
}

function EmptyGoalCard({ onOpenWizard }: { onOpenWizard: () => void }) {
  return (
    <section className="rise-in mb-6 rounded-2xl border border-line bg-raised px-5 py-7 text-center">
      <p className="font-display text-lg font-semibold">Nog geen eigen doel</p>
      <p className="mx-auto mt-1.5 max-w-[280px] text-sm leading-relaxed text-muted">
        Je traint nu op het standaardplan. Kies een race of FTP-doel en de
        coach genereert je blokperiodisering.
      </p>
      <button
        data-testid="open-goal-wizard-empty"
        onClick={onOpenWizard}
        className="mt-4 rounded-xl bg-accent px-6 py-2.5 text-sm font-semibold text-white hover:bg-accent-hover"
      >
        Stel een doel
      </button>
    </section>
  );
}

// ── Bloktijdlijn ──────────────────────────────────────────────────────────

function PhaseTimeline({
  weeks,
  goal,
  subGoals,
  onSelect,
}: {
  weeks: PlanWeekRow[];
  goal: Goal;
  subGoals: Goal[];
  onSelect: (w: PlanWeekRow) => void;
}) {
  const currentMonday = mondayOf(todayISO());

  // Fase-segmenten (aaneengesloten weken met dezelfde fase) voor de labels.
  const segments = useMemo(() => {
    const out: { phase: string; count: number }[] = [];
    for (const w of weeks) {
      const phase = w.phase ?? "";
      const last = out[out.length - 1];
      if (last && last.phase === phase) last.count += 1;
      else out.push({ phase, count: 1 });
    }
    return out;
  }, [weeks]);

  const raceWeekOf = (eventDate: string) => mondayOf(eventDate);

  if (weeks.length === 0) return null;

  return (
    <section className="rise-in mb-7">
      <h3 className="mb-3 font-mono text-[0.66rem] uppercase tracking-[0.2em] text-dim">
        bloktijdlijn
      </h3>
      <div className="-mx-5 overflow-x-auto px-5 pb-1">
        <div className="min-w-max">
          {/* Vlaggetjes (B/C-races + A-doel) boven de balk */}
          <div className="flex gap-[3px]">
            {weeks.map((w) => {
              const isARace = raceWeekOf(goal.event_date) === w.week_start;
              const sub = subGoals.find(
                (g) => raceWeekOf(g.event_date) === w.week_start,
              );
              return (
                <span key={w.week_start} className="flex h-5 w-[22px] items-end justify-center">
                  {(isARace || sub) && (
                    <FlagIcon
                      title={
                        isARace
                          ? `${GOAL_LABEL[goal.type] ?? goal.type} · ${dayMonth(goal.event_date)}`
                          : `${GOAL_LABEL[sub!.type] ?? sub!.type} (${sub!.priority}) · ${dayMonth(sub!.event_date)}`
                      }
                      accent={isARace}
                    />
                  )}
                </span>
              );
            })}
          </div>

          {/* Weekblokken */}
          <div className="flex gap-[3px]">
            {weeks.map((w) => {
              const isCurrent = w.week_start === currentMonday;
              const isPast = w.week_start < currentMonday;
              const deload = Boolean(w.is_deload);
              return (
                <button
                  key={w.week_start}
                  data-testid={`timeline-week-${w.week_start}`}
                  onClick={() => onSelect(w)}
                  title={`${dayMonth(w.week_start)} · ${fmtPhase(w.phase)}${deload ? " · deload" : ""}`}
                  className={`relative h-9 w-[22px] shrink-0 rounded-[5px] transition-transform active:scale-95 ${
                    isCurrent ? "ring-2 ring-ink ring-offset-2 ring-offset-bg" : ""
                  }`}
                  style={{
                    background: phaseColor(w.phase),
                    opacity: isPast ? 0.4 : 1,
                  }}
                >
                  {deload && (
                    <span
                      className="absolute inset-0 rounded-[5px]"
                      style={{
                        background:
                          "repeating-linear-gradient(135deg, transparent 0 3px, rgba(14,15,18,0.45) 3px 6px)",
                      }}
                    />
                  )}
                </button>
              );
            })}
          </div>

          {/* Deload-stippen + huidige week-marker */}
          <div className="mt-1 flex gap-[3px]">
            {weeks.map((w) => (
              <span
                key={w.week_start}
                className="flex h-2 w-[22px] items-center justify-center"
              >
                {w.week_start === currentMonday ? (
                  <span className="h-1.5 w-1.5 rounded-full bg-ink" />
                ) : Boolean(w.is_deload) ? (
                  <span className="h-1 w-1 rounded-full bg-dim" />
                ) : null}
              </span>
            ))}
          </div>

          {/* Fase-labels onder de segmenten */}
          <div className="mt-1.5 flex gap-[3px]">
            {segments.map((seg, i) => (
              <span
                key={i}
                className="overflow-hidden whitespace-nowrap font-mono text-[0.56rem] uppercase tracking-[0.1em] text-dim"
                style={{ width: `${seg.count * 22 + (seg.count - 1) * 3}px` }}
              >
                {seg.count >= 3 ? fmtPhase(seg.phase) : ""}
              </span>
            ))}
          </div>
        </div>
      </div>
      <p className="mt-2 font-mono text-[0.62rem] text-dim">
        arcering = deloadweek · stip = nu · tik op een week voor detail
      </p>
    </section>
  );
}

function FlagIcon({ title, accent }: { title: string; accent: boolean }) {
  return (
    <svg
      width="13"
      height="15"
      viewBox="0 0 24 24"
      fill="currentColor"
      className={accent ? "text-accent" : "text-warning"}
    >
      <title>{title}</title>
      <path d="M5 2.5a1 1 0 0 1 2 0V4h11.2c.9 0 1.3 1 .7 1.7L16 9.5l2.9 3.8c.6.7.2 1.7-.7 1.7H7v6.5a1 1 0 0 1-2 0V2.5Z" />
    </svg>
  );
}

// ── CTL: werkelijk vs doelpad ─────────────────────────────────────────────

const toTs = (iso: string) => new Date(`${iso}T00:00:00`).getTime();

function CtlChart({ view }: { view: SeasonView }) {
  const data = useMemo(() => {
    const points = new Map<number, { ts: number; actual?: number; target?: number }>();
    for (const p of view.ctl_actual ?? []) {
      const ts = toTs(p.date);
      points.set(ts, { ...(points.get(ts) ?? { ts }), actual: p.ctl });
    }
    for (const p of view.ctl_target_path ?? []) {
      const ts = toTs(p.week_start);
      points.set(ts, { ...(points.get(ts) ?? { ts }), target: p.ctl });
    }
    return [...points.values()].sort((a, b) => a.ts - b.ts);
  }, [view]);

  if (data.length < 2) return null;

  const race = toTs(view.goal.event_date);
  const lastTarget = view.ctl_target_path?.[view.ctl_target_path.length - 1];

  return (
    <section className="rise-in mb-7">
      <h3 className="mb-3 font-mono text-[0.66rem] uppercase tracking-[0.2em] text-dim">
        ctl — werkelijk vs doelpad
      </h3>
      <div className="rounded-2xl border border-line bg-raised px-2 pb-1 pt-4">
        <ResponsiveContainer width="100%" height={190}>
          <ComposedChart data={data} margin={{ left: -22, right: 8, top: 4 }}>
            <XAxis
              dataKey="ts"
              type="number"
              scale="time"
              domain={["dataMin", "dataMax"]}
              tickFormatter={(ts: number) =>
                dayMonth(new Date(ts).toISOString().slice(0, 10))
              }
              tick={{ fill: "var(--text-dim)", fontSize: 10, fontFamily: "JetBrains Mono Variable" }}
              tickLine={false}
              axisLine={{ stroke: "var(--border)" }}
              tickCount={5}
            />
            <YAxis
              tick={{ fill: "var(--text-dim)", fontSize: 10, fontFamily: "JetBrains Mono Variable" }}
              tickLine={false}
              axisLine={false}
              width={46}
            />
            <Tooltip content={<ChartTip />} />
            {lastTarget && (
              <ReferenceArea
                x1={Math.min(toTs(lastTarget.week_start), race)}
                x2={race}
                y1={lastTarget.ctl - 4}
                y2={lastTarget.ctl + 4}
                fill="var(--accent)"
                fillOpacity={0.14}
                stroke="var(--accent-border)"
              />
            )}
            <ReferenceLine x={race} stroke="var(--accent)" strokeDasharray="4 3" />
            <Line
              dataKey="actual"
              name="werkelijk"
              type="monotone"
              stroke="var(--text)"
              strokeWidth={2}
              dot={false}
              connectNulls
            />
            <Line
              dataKey="target"
              name="doelpad"
              type="monotone"
              stroke="var(--accent)"
              strokeWidth={1.6}
              strokeDasharray="5 4"
              dot={false}
              connectNulls
            />
          </ComposedChart>
        </ResponsiveContainer>
        <div className="flex justify-center gap-5 pb-2.5 font-mono text-[0.62rem] text-muted">
          <span className="inline-flex items-center gap-1.5">
            <span className="h-[2px] w-4 bg-ink" /> werkelijk
          </span>
          <span className="inline-flex items-center gap-1.5">
            <span className="h-[2px] w-4 border-t-2 border-dashed border-accent" />
            doelpad · band = racedag
          </span>
        </div>
      </div>
    </section>
  );
}

// ── Weekvolume-staafjes ───────────────────────────────────────────────────

function VolumeBars({ weeks }: { weeks: PlanWeekRow[] }) {
  const currentMonday = mondayOf(todayISO());
  const data = useMemo(
    () =>
      weeks.map((w) => ({
        week_start: w.week_start,
        tss: Math.round(((w.tss_target_min ?? 0) + (w.tss_target_max ?? 0)) / 2),
        done: w.week_start < currentMonday,
        current: w.week_start === currentMonday,
        deload: Boolean(w.is_deload),
      })),
    [weeks, currentMonday],
  );

  if (data.length === 0) return null;

  return (
    <section className="rise-in-late">
      <h3 className="mb-3 font-mono text-[0.66rem] uppercase tracking-[0.2em] text-dim">
        gepland weekvolume (tss)
      </h3>
      <div className="rounded-2xl border border-line bg-raised px-2 pb-2 pt-4">
        <ResponsiveContainer width="100%" height={130}>
          <BarChart data={data} margin={{ left: -22, right: 8 }}>
            <XAxis
              dataKey="week_start"
              tickFormatter={dayMonth}
              tick={{ fill: "var(--text-dim)", fontSize: 10, fontFamily: "JetBrains Mono Variable" }}
              tickLine={false}
              axisLine={{ stroke: "var(--border)" }}
              interval={Math.max(0, Math.ceil(data.length / 6) - 1)}
            />
            <YAxis
              tick={{ fill: "var(--text-dim)", fontSize: 10, fontFamily: "JetBrains Mono Variable" }}
              tickLine={false}
              axisLine={false}
              width={46}
            />
            <Tooltip content={<ChartTip />} cursor={{ fill: "rgba(255,255,255,0.04)" }} />
            <Bar dataKey="tss" name="tss" radius={[3, 3, 0, 0]}>
              {data.map((d) => (
                <Cell
                  key={d.week_start}
                  fill={
                    d.current
                      ? "var(--accent)"
                      : d.done
                        ? "var(--zone-z2)"
                        : "var(--border-strong)"
                  }
                  fillOpacity={d.deload ? 0.55 : 1}
                />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
        <p className="pb-1.5 text-center font-mono text-[0.62rem] text-muted">
          <span className="text-z2">groen</span> = gedaan ·{" "}
          <span className="text-accent">terracotta</span> = deze week
        </p>
      </div>
    </section>
  );
}

// ── Tooltip (gedeeld) ─────────────────────────────────────────────────────

function ChartTip({
  active,
  payload,
  label,
}: {
  active?: boolean;
  payload?: { name?: string; value?: number | string }[];
  label?: number | string;
}) {
  if (!active || !payload?.length) return null;
  const iso =
    typeof label === "number"
      ? new Date(label).toISOString().slice(0, 10)
      : String(label ?? "");
  return (
    <div className="rounded-lg border border-line-strong bg-elevated px-3 py-2 font-mono text-[0.7rem]">
      <p className="text-dim">{iso ? dayMonth(iso) : ""}</p>
      {payload.map((p, i) => (
        <p key={i} className="text-ink">
          {p.name}: {typeof p.value === "number" ? Math.round(p.value) : p.value}
        </p>
      ))}
    </div>
  );
}

// ── Week-detail ───────────────────────────────────────────────────────────

function WeekDetailSheet({
  week,
  onClose,
}: {
  week: PlanWeekRow | null;
  onClose: () => void;
}) {
  if (!week) return null;
  const rows: [string, string][] = [
    ["fase", fmtPhase(week.phase)],
    ["tss-band", `${week.tss_target_min ?? "—"}–${week.tss_target_max ?? "—"}`],
    ["run", `${week.run_km ?? "—"} km · ${week.run_sessions ?? "—"} sessies`],
    ["long run", `${week.long_run_km ?? "—"} km`],
    ["fiets", `${week.bike_sessions ?? "—"} sessies`],
    ["intensiteit", String(week.intensity_gate ?? "—")],
  ];
  return (
    <BottomSheet open onClose={onClose} title={`Week van ${dayMonth(week.week_start)}`}>
      <div className="pb-2">
        {Boolean(week.is_deload) && (
          <p className="mb-4 inline-flex rounded-full border border-positive/40 bg-positive/10 px-3 py-1 font-mono text-[0.62rem] uppercase tracking-[0.14em] text-positive">
            deloadweek
          </p>
        )}
        <dl className="space-y-2.5">
          {rows.map(([k, v]) => (
            <div key={k} className="flex items-baseline justify-between gap-4">
              <dt className="font-mono text-[0.66rem] uppercase tracking-[0.16em] text-dim">
                {k}
              </dt>
              <dd className="font-mono text-[0.85rem] capitalize text-ink">{v}</dd>
            </div>
          ))}
        </dl>
        <span
          className="mt-5 block h-1.5 w-full rounded-full"
          style={{ background: phaseColor(week.phase) }}
        />
      </div>
    </BottomSheet>
  );
}

// ── Herbereken-resultaat ──────────────────────────────────────────────────

const REGEN_LABEL: Record<RegenerateResult["status"], string> = {
  within_band: "Binnen de band — plan ongewijzigd",
  replanned: "Plan herberekend vanaf volgende week",
  injury_adjusted: "Plan gedempt door blessurestatus",
  no_goal: "Geen actief doel met macroplan",
};

function RegenResultSheet({
  result,
  onClose,
}: {
  result: RegenerateResult | null;
  onClose: () => void;
}) {
  if (!result) return null;
  const changed = result.status === "replanned" || result.status === "injury_adjusted";
  return (
    <BottomSheet open onClose={onClose} title="Herberekening">
      <div className="space-y-4 pb-2">
        <div
          className={`rounded-xl border px-4 py-3 text-sm ${
            changed
              ? "border-accent/40 bg-[var(--accent-bg)] text-ink"
              : "border-positive/40 bg-positive/10 text-positive"
          }`}
        >
          {REGEN_LABEL[result.status]}
          {result.deviation_pct != null && (
            <span className="ml-1.5 font-mono text-[0.78rem]">
              (afwijking {result.deviation_pct}%)
            </span>
          )}
        </div>

        {result.advice && (
          <p className="text-sm leading-relaxed text-muted">{result.advice}</p>
        )}

        {(result.notes ?? []).length > 0 && (
          <ul className="space-y-1.5">
            {result.notes!.map((n, i) => (
              <li key={i} className="flex gap-2 text-[0.8rem] leading-relaxed text-muted">
                <span className="text-dim">·</span>
                {n}
              </li>
            ))}
          </ul>
        )}

        {(result.warnings ?? []).length > 0 && (
          <ul className="space-y-1.5">
            {result.warnings!.map((w, i) => (
              <li key={i} className="text-[0.8rem] leading-relaxed text-warning">
                {w}
              </li>
            ))}
          </ul>
        )}

        <button
          onClick={onClose}
          className="w-full rounded-xl bg-accent py-3 text-sm font-semibold text-white hover:bg-accent-hover"
        >
          Klaar
        </button>
      </div>
    </BottomSheet>
  );
}
