import { useEffect, useMemo, useState } from "react";
import {
  Bar,
  BarChart,
  Cell,
  ComposedChart,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Scatter,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { isUnavailable } from "../api/client";
import {
  useCheckinHistory,
  useDeleteFixedSession,
  useFixedSessions,
  usePattern,
  usePlanWeek,
  usePostRaceResult,
  usePutFixedSession,
  usePutThresholdPace,
  useResolveThresholdSuggestion,
  useThresholdPace,
  useTrends,
} from "../api/queries";
import type {
  AvailabilitySlot,
  CheckinHistoryView,
  FixedSession,
  InjuryGuard,
  PatternSlot,
  ThresholdDossier,
  ThresholdMutationResult,
  ThresholdObservation,
  ThresholdPaceView,
  TrendsView,
} from "../api/types";
import OfflineBanner, { useOnline } from "../components/OfflineBanner";
import Spinner from "../components/Spinner";
import PatternDaySheet from "../features/PatternDaySheet";
import { dayMonth, hoursLabel, toMinutes } from "../lib/dates";

const APP_VERSION = "v2.0 · fase 5";

export default function You() {
  const trends = useTrends();
  const history = useCheckinHistory(14);
  const online = useOnline();

  if (trends.isLoading) return <Spinner label="Trends laden…" />;

  const stale =
    !online || (trends.isError && isUnavailable(trends.error));

  return (
    <div>
      <OfflineBanner show={stale} />

      <header className="rise-in mb-6">
        <p className="font-mono text-[0.66rem] uppercase tracking-[0.2em] text-dim">
          atleet
        </p>
        <h1 className="font-display mt-1.5 text-2xl font-semibold">Jij</h1>
      </header>

      {trends.data ? (
        <>
          <FormCard view={trends.data} />
          <FitnessChart view={trends.data} />
          <VolumeChart view={trends.data} />
          <HrvChart view={trends.data} />
          <ThresholdDossierChart view={trends.data} />
        </>
      ) : (
        <p className="rise-in mb-7 rounded-2xl border border-line bg-raised px-5 py-6 text-sm text-muted">
          Trends zijn nu niet op te halen.
        </p>
      )}

      <InjurySection history={history.data} loading={history.isLoading} />

      <SettingsSection trends={trends.data} />

      <footer className="rise-in-late mt-10 flex items-center justify-between border-t border-line pt-4 font-mono text-[0.66rem] text-dim">
        <span>Sport Coach · {APP_VERSION}</span>
        <a
          href="https://intervals.icu"
          target="_blank"
          rel="noreferrer"
          className="text-muted underline-offset-2 hover:text-accent hover:underline"
        >
          intervals.icu ↗
        </a>
      </footer>
    </div>
  );
}

// ── Vorm (TSB) ────────────────────────────────────────────────────────────

function formZone(tsb: number): { label: string; cls: string } {
  if (tsb >= 5) return { label: "fris", cls: "text-positive" };
  if (tsb >= -10) return { label: "neutraal", cls: "text-ink" };
  return { label: "vermoeid", cls: "text-warning" };
}

function FormCard({ view }: { view: TrendsView }) {
  const last = view.ctl_series[view.ctl_series.length - 1];
  const tsb = last?.tsb ?? view.load.tsb_estimate ?? 0;
  const ctl = last?.ctl ?? view.load.ctl_estimate ?? 0;
  const atl = last?.atl ?? view.load.atl_estimate ?? 0;
  const zone = formZone(tsb);

  return (
    <section
      data-testid="form-card"
      className="rise-in mb-7 rounded-2xl border border-line bg-raised px-5 py-5"
    >
      <div className="flex items-end justify-between">
        <div>
          <p className="font-mono text-[0.6rem] uppercase tracking-[0.18em] text-dim">
            vorm (tsb)
          </p>
          <p className={`font-mono mt-1 text-[2.2rem] font-medium leading-none ${zone.cls}`}>
            {tsb > 0 ? "+" : ""}
            {Math.round(tsb)}
          </p>
          <p className={`mt-1.5 font-mono text-[0.66rem] uppercase tracking-[0.16em] ${zone.cls}`}>
            {zone.label}
          </p>
        </div>
        <div className="flex gap-6 pb-1">
          <Metric label="ctl · fitheid" value={String(Math.round(ctl))} />
          <Metric label="atl · vermoeid" value={String(Math.round(atl))} />
        </div>
      </div>
      {/* TSB-kleurzones als mini-schaal */}
      <div className="relative mt-4 h-[5px] overflow-hidden rounded-full">
        <div className="absolute inset-y-0 left-0 w-[40%] bg-warning/50" />
        <div className="absolute inset-y-0 left-[40%] w-[35%] bg-line-strong" />
        <div className="absolute inset-y-0 left-[75%] w-[25%] bg-positive/60" />
        <span
          className="absolute top-0 h-full w-[3px] rounded-full bg-ink"
          style={{
            left: `${Math.min(97, Math.max(1, ((Math.max(-30, Math.min(20, tsb)) + 30) / 50) * 100))}%`,
          }}
        />
      </div>
      <div className="mt-1.5 flex justify-between font-mono text-[0.58rem] uppercase tracking-[0.12em] text-dim">
        <span>vermoeid</span>
        <span>neutraal</span>
        <span>fris</span>
      </div>
    </section>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="text-right">
      <div className="font-mono text-[1.05rem] font-medium">{value}</div>
      <div className="font-mono text-[0.58rem] uppercase tracking-[0.14em] text-dim">
        {label}
      </div>
    </div>
  );
}

// ── Charts ────────────────────────────────────────────────────────────────

const AXIS_TICK = {
  fill: "var(--text-dim)",
  fontSize: 10,
  fontFamily: "JetBrains Mono Variable",
} as const;

function ChartCard({
  title,
  children,
  legend,
}: {
  title: string;
  children: React.ReactElement;
  legend?: React.ReactNode;
}) {
  return (
    <section className="rise-in mb-7">
      <h3 className="mb-3 font-mono text-[0.66rem] uppercase tracking-[0.2em] text-dim">
        {title}
      </h3>
      <div className="rounded-2xl border border-line bg-raised px-2 pb-1 pt-4">
        {children}
        {legend && (
          <div className="flex justify-center gap-5 pb-2.5 font-mono text-[0.62rem] text-muted">
            {legend}
          </div>
        )}
      </div>
    </section>
  );
}

function ChartTip({
  active,
  payload,
  label,
}: {
  active?: boolean;
  payload?: { name?: string; value?: number | string }[];
  label?: string | number;
}) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-lg border border-line-strong bg-elevated px-3 py-2 font-mono text-[0.7rem]">
      <p className="text-dim">{label ? dayMonth(String(label)) : ""}</p>
      {payload.map((p, i) => (
        <p key={i} className="text-ink">
          {p.name}: {typeof p.value === "number" ? Math.round(p.value) : p.value}
        </p>
      ))}
    </div>
  );
}

function FitnessChart({ view }: { view: TrendsView }) {
  if (view.ctl_series.length < 2) return null;
  const data = view.ctl_series;
  return (
    <ChartCard
      title="ctl · atl · tsb"
      legend={
        <>
          <LegendSwatch color="var(--text)" label="ctl" />
          <LegendSwatch color="var(--zone-tempo)" label="atl" />
          <LegendSwatch color="var(--zone-z1)" label="tsb" />
        </>
      }
    >
      <ResponsiveContainer width="100%" height={180}>
        <LineChart data={data} margin={{ left: -22, right: 8, top: 4 }}>
          <XAxis
            dataKey="date"
            tickFormatter={dayMonth}
            tick={AXIS_TICK}
            tickLine={false}
            axisLine={{ stroke: "var(--border)" }}
            interval={Math.max(0, Math.ceil(data.length / 5) - 1)}
          />
          <YAxis tick={AXIS_TICK} tickLine={false} axisLine={false} width={46} />
          <Tooltip content={<ChartTip />} />
          <ReferenceLine y={0} stroke="var(--border-strong)" />
          <Line dataKey="ctl" name="ctl" type="monotone" stroke="var(--text)" strokeWidth={2} dot={false} />
          <Line dataKey="atl" name="atl" type="monotone" stroke="var(--zone-tempo)" strokeWidth={1.4} dot={false} />
          <Line dataKey="tsb" name="tsb" type="monotone" stroke="var(--zone-z1)" strokeWidth={1.4} dot={false} />
        </LineChart>
      </ResponsiveContainer>
    </ChartCard>
  );
}

function LegendSwatch({ color, label }: { color: string; label: string }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className="h-[2px] w-4" style={{ background: color }} />
      {label}
    </span>
  );
}

function VolumeChart({ view }: { view: TrendsView }) {
  const data = useMemo(() => view.weekly_volume.slice(-12), [view]);
  if (data.length === 0) return null;
  return (
    <ChartCard title="weekvolume (tss, gedaan)">
      <ResponsiveContainer width="100%" height={130}>
        <BarChart data={data} margin={{ left: -22, right: 8 }}>
          <XAxis
            dataKey="week_start"
            tickFormatter={dayMonth}
            tick={AXIS_TICK}
            tickLine={false}
            axisLine={{ stroke: "var(--border)" }}
            interval={Math.max(0, Math.ceil(data.length / 5) - 1)}
          />
          <YAxis tick={AXIS_TICK} tickLine={false} axisLine={false} width={46} />
          <Tooltip content={<ChartTip />} cursor={{ fill: "rgba(255,255,255,0.04)" }} />
          <Bar dataKey="tss" name="tss" radius={[3, 3, 0, 0]}>
            {data.map((d, i) => (
              <Cell
                key={d.week_start}
                fill={i === data.length - 1 ? "var(--accent)" : "var(--border-strong)"}
              />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </ChartCard>
  );
}

function HrvChart({ view }: { view: TrendsView }) {
  if (view.hrv.length < 2) return null;
  return (
    <ChartCard title="hrv (ochtend)">
      <ResponsiveContainer width="100%" height={120}>
        <LineChart data={view.hrv} margin={{ left: -22, right: 8, top: 4 }}>
          <XAxis
            dataKey="date"
            tickFormatter={dayMonth}
            tick={AXIS_TICK}
            tickLine={false}
            axisLine={{ stroke: "var(--border)" }}
            interval={Math.max(0, Math.ceil(view.hrv.length / 5) - 1)}
          />
          <YAxis
            tick={AXIS_TICK}
            tickLine={false}
            axisLine={false}
            width={46}
            domain={["dataMin - 5", "dataMax + 5"]}
          />
          <Tooltip content={<ChartTip />} />
          <Line dataKey="hrv" name="hrv" type="monotone" stroke="var(--zone-z2)" strokeWidth={2} dot={false} />
        </LineChart>
      </ResponsiveContainer>
    </ChartCard>
  );
}

// ── Injury-guard ──────────────────────────────────────────────────────────

const GUARD_BIG: Record<
  InjuryGuard["status"],
  { label: string; cls: string; bar: string }
> = {
  groen: { label: "GREEN", cls: "text-positive", bar: "bg-positive" },
  geel: { label: "YELLOW", cls: "text-warning", bar: "bg-warning" },
  rood: { label: "RED", cls: "text-alert", bar: "bg-alert" },
};

function ThresholdDossierChart({ view }: { view: TrendsView }) {
  const dossier = view.threshold;
  const data = useMemo(() => thresholdChartData(dossier), [dossier]);
  const recent = dossier.observations.slice(-4).reverse();
  const current = dossier.threshold_pace_sec_per_km;

  return (
    <section className="rise-in mb-7">
      <h3 className="mb-3 font-mono text-[0.66rem] uppercase tracking-[0.2em] text-dim">
        drempeldossier
      </h3>
      <div className="overflow-hidden rounded-2xl border border-line bg-raised">
        <div className="px-5 pb-2 pt-4">
          <div className="flex items-baseline justify-between gap-4">
            <p className="font-mono text-[1.55rem] font-medium">
              {paceLabel(current)}/km
            </p>
            <p className="font-mono text-[0.62rem] uppercase tracking-[0.16em] text-dim">
              {dossier.context.window_days}d venster
            </p>
          </div>
          <p className="mt-1.5 text-[0.8rem] leading-relaxed text-muted">
            {dossier.context.sentence}
          </p>
        </div>

        {data.length > 0 && (
          <div className="px-2 pb-1 pt-1">
            <ResponsiveContainer width="100%" height={165}>
              <ComposedChart data={data} margin={{ left: -18, right: 12, top: 8 }}>
                <XAxis
                  dataKey="date"
                  tickFormatter={dayMonth}
                  tick={AXIS_TICK}
                  tickLine={false}
                  axisLine={{ stroke: "var(--border)" }}
                  interval={Math.max(0, Math.ceil(data.length / 5) - 1)}
                />
                <YAxis
                  tick={AXIS_TICK}
                  tickLine={false}
                  axisLine={false}
                  width={50}
                  tickFormatter={(sec) => paceLabel(Number(sec))}
                  domain={["dataMin - 4", "dataMax + 4"]}
                />
                <Tooltip content={<ThresholdTip />} />
                <ReferenceLine y={current} stroke="var(--border-strong)" strokeDasharray="4 4" />
                <Line
                  dataKey="threshold_sec"
                  name="drempel"
                  type="monotone"
                  stroke="var(--text)"
                  strokeWidth={2}
                  connectNulls
                  dot={{ r: 3, fill: "var(--text)" }}
                />
                <Scatter
                  dataKey="observed_sec"
                  name="sessie"
                  fill="var(--zone-drempel)"
                  line={false}
                />
              </ComposedChart>
            </ResponsiveContainer>
            <div className="flex justify-center gap-5 pb-3 font-mono text-[0.62rem] text-muted">
              <LegendSwatch color="var(--text)" label="drempel" />
              <LegendSwatch color="var(--zone-drempel)" label="sessie" />
            </div>
          </div>
        )}

        <div className="border-t border-line px-5 py-4">
          <p className="mb-2.5 font-mono text-[0.6rem] uppercase tracking-[0.18em] text-dim">
            laatste observaties
          </p>
          {recent.length === 0 ? (
            <p className="text-sm text-muted">Nog geen drempelsessies gelogd.</p>
          ) : (
            <ul className="space-y-2">
              {recent.map((obs) => (
                <li key={obs.id} className="grid grid-cols-[3.5rem_1fr_auto] items-center gap-3">
                  <span className="font-mono text-[0.7rem] text-dim">{dayMonth(obs.date)}</span>
                  <span className="text-[0.8rem] text-muted">
                    {obs.hr_vs_band ? `HR ${obs.hr_vs_band}` : "HR onbekend"}
                    {obs.rpe != null ? ` · RPE ${obs.rpe}` : ""}
                  </span>
                  <span className={deltaClass(obs.pace_delta_sec)}>
                    {deltaLabel(obs.pace_delta_sec)}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </section>
  );
}

function thresholdChartData(dossier: ThresholdDossier) {
  const rows = new Map<string, { date: string; threshold_sec?: number; observed_sec?: number }>();
  for (const row of dossier.log) {
    rows.set(row.date, {
      ...(rows.get(row.date) ?? { date: row.date }),
      threshold_sec: row.new_sec,
    });
  }
  if (dossier.log.length === 0) {
    const first = dossier.observations[0]?.date ?? new Date().toISOString().slice(0, 10);
    rows.set(first, {
      ...(rows.get(first) ?? { date: first }),
      threshold_sec: dossier.threshold_pace_sec_per_km,
    });
  }
  for (const obs of dossier.observations) {
    const observed = observedPaceSec(obs, dossier.threshold_pace_sec_per_km);
    if (observed == null) continue;
    rows.set(obs.date, {
      ...(rows.get(obs.date) ?? { date: obs.date }),
      observed_sec: observed,
    });
  }
  return [...rows.values()].sort((a, b) => a.date.localeCompare(b.date));
}

/** De gelopen pace zoals hij toen was. De delta is gemeten t.o.v. de target van
 *  díé sessie (95–103% drempel), niet t.o.v. de drempel van vandaag — hem bij de
 *  huidige drempel optellen zou de punten verschuiven. */
function observedPaceSec(obs: ThresholdObservation, currentSec: number) {
  if (obs.observed_pace_sec != null) return obs.observed_pace_sec;
  if (obs.pace_delta_sec == null) return null;
  return (obs.target_pace_sec ?? currentSec) + obs.pace_delta_sec;
}

function ThresholdTip({
  active,
  payload,
  label,
}: {
  active?: boolean;
  payload?: { name?: string; value?: number | string }[];
  label?: string | number;
}) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-lg border border-line-strong bg-elevated px-3 py-2 font-mono text-[0.7rem]">
      <p className="text-dim">{label ? dayMonth(String(label)) : ""}</p>
      {payload.map((p, i) => (
        <p key={i} className="text-ink">
          {p.name}: {typeof p.value === "number" ? `${paceLabel(p.value)}/km` : p.value}
        </p>
      ))}
    </div>
  );
}

function deltaLabel(delta?: number | null): string {
  if (delta == null) return "n/a";
  const rounded = Math.round(delta);
  if (rounded === 0) return "target";
  return `${rounded > 0 ? "+" : ""}${rounded}s/km`;
}

function deltaClass(delta?: number | null): string {
  const base = "font-mono text-[0.72rem]";
  if (delta == null) return `${base} text-dim`;
  if (delta <= -3) return `${base} text-positive`;
  if (delta >= 5) return `${base} text-warning`;
  return `${base} text-muted`;
}

function InjurySection({
  history,
  loading,
}: {
  history: CheckinHistoryView | undefined;
  loading: boolean;
}) {
  const guard = history?.injury_guard ?? null;
  const style = guard ? (GUARD_BIG[guard.status] ?? GUARD_BIG.groen) : null;

  // Signalen + checkin-scores samenvoegen tot één historie per dag (nieuwste eerst).
  const days = useMemo(() => {
    const map = new Map<string, { score: number | null; signals: string[] }>();
    for (const rec of history?.records ?? []) {
      map.set(rec.date, {
        score: (rec.checkin_score as number | null) ?? null,
        signals: [],
      });
    }
    for (const sig of history?.signals ?? []) {
      const entry = map.get(sig.date) ?? { score: null, signals: [] };
      entry.signals = [...entry.signals, ...(sig.signals ?? [])];
      map.set(sig.date, entry);
    }
    return [...map.entries()].sort((a, b) => (a[0] < b[0] ? 1 : -1));
  }, [history]);

  return (
    <section data-testid="injury-section" className="rise-in mb-7">
      <h3 className="mb-3 font-mono text-[0.66rem] uppercase tracking-[0.2em] text-dim">
        injury guard
      </h3>
      <div className="overflow-hidden rounded-2xl border border-line bg-raised">
        {loading && !history ? (
          <p className="px-5 py-6 text-sm text-muted">Laden…</p>
        ) : guard && style ? (
          <>
            <div className="relative px-5 pb-4 pt-5">
              <div className={`absolute inset-x-0 top-0 h-[3px] ${style.bar}`} />
              <div className="flex items-baseline gap-3">
                <span className={`font-display text-3xl font-semibold ${style.cls}`}>
                  {style.label}
                </span>
                {guard.days_symptom_free != null && (
                  <span className="font-mono text-[0.72rem] text-muted">
                    {guard.days_symptom_free} dagen symptoomvrij
                  </span>
                )}
              </div>
              {guard.message && (
                <p className="mt-2 text-[0.82rem] leading-relaxed text-muted">
                  {guard.message}
                </p>
              )}
              {guard.active_signals.length > 0 && (
                <div className="mt-3 flex flex-wrap gap-1.5">
                  {guard.active_signals.map((s) => (
                    <SignalChip key={s} signal={s} />
                  ))}
                </div>
              )}
            </div>

            <div className="border-t border-line px-5 py-4">
              <p className="mb-2.5 font-mono text-[0.6rem] uppercase tracking-[0.18em] text-dim">
                laatste {history?.days ?? 14} dagen
              </p>
              {days.length === 0 ? (
                <p className="text-sm text-muted">
                  Nog geen checkins of signalen gelogd.
                </p>
              ) : (
                <ul className="space-y-2">
                  {days.map(([date, d]) => (
                    <li key={date} className="flex items-center gap-3">
                      <span className="w-14 shrink-0 font-mono text-[0.7rem] text-dim">
                        {dayMonth(date)}
                      </span>
                      <span className="font-mono text-[0.74rem] text-muted">
                        {d.score != null ? `checkin ${d.score.toFixed(1)}` : "—"}
                      </span>
                      <span className="flex flex-wrap gap-1.5">
                        {d.signals.map((s) => (
                          <SignalChip key={s} signal={s} />
                        ))}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </>
        ) : (
          <p className="px-5 py-6 text-sm text-muted">
            Injury-status is nu niet op te halen.
          </p>
        )}
      </div>
    </section>
  );
}

function SignalChip({ signal }: { signal: string }) {
  return (
    <span className="rounded-full border border-alert/40 bg-alert/10 px-2 py-0.5 font-mono text-[0.62rem] text-alert">
      {signal.replace(/_/g, " ")}
    </span>
  );
}

// ── Instellingen ──────────────────────────────────────────────────────────

const WEEKDAYS = ["maandag", "dinsdag", "woensdag", "donderdag", "vrijdag", "zaterdag", "zondag"];

function toSlots(slots: PatternSlot[] | undefined): AvailabilitySlot[] {
  return (slots ?? []).map((s) => ({
    start: s.slot_start,
    end: s.slot_end,
    context: s.context,
  }));
}

function SettingsSection({ trends }: { trends: TrendsView | undefined }) {
  const pattern = usePattern();
  const fixed = useFixedSessions();
  const [editDay, setEditDay] = useState<number | null>(null);

  return (
    <section className="rise-in-late">
      <h3 className="mb-3 font-mono text-[0.66rem] uppercase tracking-[0.2em] text-dim">
        instellingen
      </h3>

      <ThresholdPaceCard />

      {/* Weekpatroon-editor */}
      <div className="mt-3 overflow-hidden rounded-2xl border border-line bg-raised">
        <p className="border-b border-line px-5 pb-3 pt-4 text-sm font-medium">
          Weekpatroon
          <span className="ml-2 font-mono text-[0.64rem] font-normal text-dim">
            terugkerende beschikbaarheid
          </span>
        </p>
        {pattern.isLoading ? (
          <p className="px-5 py-4 text-sm text-muted">Laden…</p>
        ) : (
          <ul>
            {WEEKDAYS.map((label, weekday) => {
              const slots = pattern.data?.pattern?.[String(weekday)] ?? [];
              return (
                <li key={weekday} className="border-b border-line last:border-b-0">
                  <button
                    data-testid={`pattern-day-${weekday}`}
                    onClick={() => setEditDay(weekday)}
                    className="flex w-full items-center justify-between gap-3 px-5 py-3 text-left transition-colors hover:bg-elevated"
                  >
                    <span className="text-[0.84rem] capitalize">{label}</span>
                    <span className="font-mono text-[0.66rem] text-muted">
                      {slots.length === 0
                        ? "rustdag"
                        : hoursLabel(
                            slots.reduce(
                              (sum, s) => sum + (toMinutes(s.slot_end) - toMinutes(s.slot_start)),
                              0,
                            ),
                          )}
                    </span>
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </div>

      <div className="mt-3 overflow-hidden rounded-2xl border border-line bg-raised">
        <p className="border-b border-line px-5 pb-3 pt-4 text-sm font-medium">
          Vaste sessies
          <span className="ml-2 font-mono text-[0.64rem] font-normal text-dim">
            onverplaatsbaar
          </span>
        </p>
        {fixed.isLoading ? (
          <p className="px-5 py-4 text-sm text-muted">Ladenâ€¦</p>
        ) : (
          <ul>
            {WEEKDAYS.map((label, weekday) => (
              <FixedSessionRow
                key={weekday}
                weekday={weekday}
                label={label}
                session={fixed.data?.fixed_sessions.find((s) => s.weekday === weekday)}
              />
            ))}
          </ul>
        )}
      </div>

      {/* Atleetdata + TP-sync */}
      <div className="mt-3 grid grid-cols-3 gap-3">
        <ReadonlyTile label="ftp" value={trends ? `${trends.athlete.ftp}W` : "—"} />
        <ReadonlyTile label="hrmax" value={trends ? String(trends.athlete.hrmax) : "—"} />
        <ReadonlyTile
          label="tp-sync"
          value={trends ? (trends.tp_sync_enabled ? "actief" : "uit") : "—"}
          tone={trends?.tp_sync_enabled ? "positive" : "dim"}
        />
      </div>

      {editDay != null && (
        <PatternDaySheet
          weekday={editDay}
          dayLabel={WEEKDAYS[editDay]}
          initial={toSlots(pattern.data?.pattern?.[String(editDay)])}
          onClose={() => setEditDay(null)}
        />
      )}
    </section>
  );
}

function ThresholdPaceCard() {
  const threshold = useThresholdPace();
  const save = usePutThresholdPace();
  const resolve = useResolveThresholdSuggestion();
  const view = threshold.data;
  const [value, setValue] = useState("");
  const [replanWeek, setReplanWeek] = useState<string | null>(null);

  useEffect(() => {
    if (view?.threshold_pace_sec_per_km)
      setValue(paceLabel(view.threshold_pace_sec_per_km));
  }, [view?.threshold_pace_sec_per_km]);

  const latest = view?.log?.[view.log.length - 1];
  const busy = save.isPending || resolve.isPending;

  const onMutated = (res: ThresholdMutationResult) => {
    if (res.replan_needed && res.replan_week_start)
      setReplanWeek(res.replan_week_start);
  };

  const onSave = () => {
    const sec = parsePace(value);
    if (!sec) return;
    save.mutate({ sec_per_km: sec, reason: "handmatig" }, { onSuccess: onMutated });
  };

  return (
    <div className="overflow-hidden rounded-2xl border border-line bg-raised px-5 py-4">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="font-mono text-[0.6rem] uppercase tracking-[0.18em] text-dim">
            drempelpace
          </p>
          <p className="mt-1 font-mono text-[1.7rem] font-medium">
            {view ? `${paceLabel(view.threshold_pace_sec_per_km)}/km` : "—"}
          </p>
          <p className="mt-1 text-[0.76rem] text-muted">
            {latest
              ? `${latest.reason} · ${latest.date}`
              : "Nog geen wijzigingslog."}
          </p>
        </div>
        <div className="grid w-28 gap-2">
          <input
            value={value}
            onChange={(e) => setValue(e.target.value)}
            className="rounded-lg border border-line bg-elevated px-3 py-2 text-center font-mono text-[0.82rem] outline-none focus:border-accent"
          />
          <button
            onClick={onSave}
            disabled={busy || !parsePace(value)}
            className="rounded-lg bg-accent px-3 py-2 text-[0.76rem] font-semibold text-white disabled:opacity-50"
          >
            OK
          </button>
        </div>
      </div>

      {view?.suggestion && (
        <ThresholdSuggestionCard
          view={view}
          busy={busy}
          onResolve={(accepted) =>
            resolve.mutate(
              { id: view.suggestion!.id, accepted },
              { onSuccess: onMutated },
            )
          }
        />
      )}

      {replanWeek && (
        <ReplanPrompt weekStart={replanWeek} onDone={() => setReplanWeek(null)} />
      )}

      <RaceAnchorForm busy={busy} />
    </div>
  );
}

/** De workouts in het plan dragen absolute paces van het plan-moment. Na een
 *  drempelwijziging staan ze dus op de oude waarde tot je opnieuw plant. */
function ReplanPrompt({
  weekStart,
  onDone,
}: {
  weekStart: string;
  onDone: () => void;
}) {
  const plan = usePlanWeek(weekStart);

  if (plan.isSuccess) {
    return (
      <div className="mt-4 rounded-xl border border-positive/40 bg-positive/10 px-3.5 py-3">
        <p className="text-[0.78rem] text-muted">
          Week opnieuw gepland op de nieuwe drempelpace ({plan.data.planned_sessions}{" "}
          sessies).
        </p>
        <button
          onClick={onDone}
          className="mt-2 text-[0.76rem] font-semibold text-accent"
        >
          Sluiten
        </button>
      </div>
    );
  }

  return (
    <div className="mt-4 rounded-xl border border-line-strong bg-elevated px-3.5 py-3">
      <p className="text-[0.78rem] leading-relaxed text-muted">
        Je ingeplande workouts staan nog op de oude drempelpace. Herplan deze week
        om de nieuwe paces door te voeren.
      </p>
      <div className="mt-3 flex gap-2">
        <button
          onClick={() => plan.mutate()}
          disabled={plan.isPending}
          className="rounded-lg bg-accent px-3 py-2 text-[0.76rem] font-semibold text-white disabled:opacity-50"
        >
          {plan.isPending ? "Bezig…" : "Herplan deze week"}
        </button>
        <button
          onClick={onDone}
          disabled={plan.isPending}
          className="rounded-lg border border-line-strong px-3 py-2 text-[0.76rem] font-semibold disabled:opacity-50"
        >
          Later
        </button>
      </div>
    </div>
  );
}

/** Race-anker: een maximale test is geen ruis, dus die mag direct een voorstel
 *  opleveren zonder de trend van 3-uit-4 af te wachten. */
function RaceAnchorForm({ busy }: { busy: boolean }) {
  const postRace = usePostRaceResult();
  const [distance, setDistance] = useState(5000);
  const [time, setTime] = useState("");

  const seconds = parseDuration(time);
  const onSubmit = () => {
    if (!seconds) return;
    postRace.mutate(
      { distance_m: distance, time_sec: seconds },
      { onSuccess: () => setTime("") },
    );
  };

  return (
    <div className="mt-4 border-t border-line pt-4">
      <p className="font-mono text-[0.6rem] uppercase tracking-[0.18em] text-dim">
        race-resultaat
      </p>
      <p className="mt-1 text-[0.76rem] leading-relaxed text-muted">
        Wedstrijd of maximale test gelopen? Dat is een hard anker voor je drempel.
      </p>
      <div className="mt-3 flex gap-2">
        <select
          value={distance}
          onChange={(e) => setDistance(Number(e.target.value))}
          className="rounded-lg border border-line bg-elevated px-2 py-2 font-mono text-[0.78rem] outline-none focus:border-accent"
        >
          {RACE_DISTANCES.map((d) => (
            <option key={d.meters} value={d.meters}>
              {d.label}
            </option>
          ))}
        </select>
        <input
          value={time}
          onChange={(e) => setTime(e.target.value)}
          placeholder="19:30"
          className="w-24 rounded-lg border border-line bg-elevated px-3 py-2 text-center font-mono text-[0.78rem] outline-none focus:border-accent"
        />
        <button
          onClick={onSubmit}
          disabled={busy || postRace.isPending || !seconds}
          className="flex-1 rounded-lg border border-line-strong px-3 py-2 text-[0.76rem] font-semibold disabled:opacity-50"
        >
          Voorstel
        </button>
      </div>
      {postRace.isSuccess && !postRace.data.suggestion && (
        <p className="mt-2 text-[0.76rem] text-muted">
          Geen voorstel — er staat al een open voorstel.
        </p>
      )}
    </div>
  );
}

const RACE_DISTANCES = [
  { meters: 5000, label: "5 km" },
  { meters: 10000, label: "10 km" },
  { meters: 21097, label: "halve" },
];

/** "19:30" of "1:23:45" -> seconden. */
function parseDuration(raw: string): number | null {
  const parts = raw.trim().split(":");
  if (parts.length < 2 || parts.length > 3) return null;
  if (parts.some((p) => p === "" || !/^\d+$/.test(p))) return null;
  const nums = parts.map(Number);
  const seconds =
    nums.length === 3
      ? nums[0] * 3600 + nums[1] * 60 + nums[2]
      : nums[0] * 60 + nums[1];
  return seconds > 0 ? seconds : null;
}

function ThresholdSuggestionCard({
  view,
  busy,
  onResolve,
}: {
  view: ThresholdPaceView;
  busy: boolean;
  onResolve: (accepted: boolean) => void;
}) {
  const suggestion = view.suggestion;
  if (!suggestion) return null;
  return (
    <div className="mt-4 rounded-xl border border-warning/40 bg-warning/10 px-3.5 py-3">
      <p className="font-mono text-[0.62rem] uppercase tracking-[0.16em] text-warning">
        voorstel
      </p>
      <p className="mt-1 text-sm font-medium">
        {paceLabel(suggestion.old_sec)}/km → {paceLabel(suggestion.proposed_sec)}/km
      </p>
      <p className="mt-1.5 text-[0.78rem] leading-relaxed text-muted">
        {suggestion.reason}
      </p>
      <div className="mt-3 flex gap-2">
        <button
          onClick={() => onResolve(true)}
          disabled={busy}
          className="rounded-lg bg-accent px-3 py-2 text-[0.76rem] font-semibold text-white disabled:opacity-50"
        >
          Accepteren
        </button>
        <button
          onClick={() => onResolve(false)}
          disabled={busy}
          className="rounded-lg border border-line-strong px-3 py-2 text-[0.76rem] font-semibold disabled:opacity-50"
        >
          Afwijzen
        </button>
      </div>
    </div>
  );
}

function paceLabel(sec: number): string {
  const m = Math.floor(sec / 60);
  const s = Math.round(sec % 60);
  return `${m}:${String(s).padStart(2, "0")}`;
}

function parsePace(raw: string): number | null {
  const match = raw.trim().match(/^(\d):(\d{2})$/);
  if (!match) return null;
  const sec = Number(match[1]) * 60 + Number(match[2]);
  return sec >= 220 && sec <= 320 ? sec : null;
}

function FixedSessionRow({
  weekday,
  label,
  session,
}: {
  weekday: number;
  label: string;
  session?: FixedSession;
}) {
  const save = usePutFixedSession();
  const remove = useDeleteFixedSession();
  const [enabled, setEnabled] = useState(Boolean(session?.enabled));
  const [name, setName] = useState(session?.name ?? "Forenzen-rit");
  const [duration, setDuration] = useState(String(session?.duration_min ?? 100));

  useEffect(() => {
    setEnabled(Boolean(session?.enabled));
    setName(session?.name ?? "Forenzen-rit");
    setDuration(String(session?.duration_min ?? 100));
  }, [session]);

  const busy = save.isPending || remove.isPending;
  const hasSession = Boolean(session);

  const onSave = () => {
    const durationMin = Math.max(1, Math.min(600, Number(duration) || 100));
    save.mutate({
      weekday,
      body: {
        name: name.trim() || "Forenzen-rit",
        sport: session?.sport ?? "VirtualRide",
        duration_min: durationMin,
        if_estimate: session?.if_estimate ?? 0.65,
        enabled,
      },
    });
  };

  return (
    <li className="border-b border-line px-5 py-3 last:border-b-0">
      <div className="grid grid-cols-[1fr_auto] gap-3">
        <label className="flex items-center gap-2">
          <input
            type="checkbox"
            checked={enabled}
            onChange={(e) => setEnabled(e.target.checked)}
            className="h-4 w-4 accent-[var(--accent)]"
          />
          <span className="text-[0.84rem] capitalize">{label}</span>
        </label>
        <button
          onClick={() => hasSession && remove.mutate(weekday)}
          disabled={!hasSession || busy}
          className="font-mono text-[0.62rem] uppercase tracking-[0.14em] text-dim disabled:opacity-30"
        >
          wis
        </button>
      </div>
      <div className="mt-2 grid grid-cols-[1fr_5.5rem_auto] gap-2">
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          className="min-w-0 rounded-lg border border-line bg-elevated px-3 py-2 text-[0.78rem] outline-none focus:border-accent"
        />
        <input
          value={duration}
          type="number"
          min={1}
          max={600}
          onChange={(e) => setDuration(e.target.value)}
          className="rounded-lg border border-line bg-elevated px-3 py-2 text-[0.78rem] outline-none focus:border-accent"
        />
        <button
          onClick={onSave}
          disabled={busy}
          className="rounded-lg bg-accent px-3 py-2 text-[0.76rem] font-semibold text-white disabled:opacity-50"
        >
          {busy ? "..." : "OK"}
        </button>
      </div>
    </li>
  );
}

function ReadonlyTile({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone?: "positive" | "dim";
}) {
  return (
    <div className="rounded-2xl border border-line bg-raised px-4 py-3.5">
      <div
        className={`font-mono text-[0.95rem] font-medium ${
          tone === "positive" ? "text-positive" : tone === "dim" ? "text-muted" : ""
        }`}
      >
        {value}
      </div>
      <div className="mt-0.5 font-mono text-[0.58rem] uppercase tracking-[0.16em] text-dim">
        {label}
      </div>
    </div>
  );
}
