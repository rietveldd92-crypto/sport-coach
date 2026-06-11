import { useMemo, useState } from "react";
import {
  Bar,
  BarChart,
  Cell,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { isUnavailable } from "../api/client";
import { useCheckinHistory, usePattern, useTrends } from "../api/queries";
import type {
  AvailabilitySlot,
  CheckinHistoryView,
  InjuryGuard,
  PatternSlot,
  TrendsView,
} from "../api/types";
import OfflineBanner, { useOnline } from "../components/OfflineBanner";
import Spinner from "../components/Spinner";
import PatternDaySheet from "../features/PatternDaySheet";
import { dayMonth } from "../lib/dates";

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
  const [editDay, setEditDay] = useState<number | null>(null);

  return (
    <section className="rise-in-late">
      <h3 className="mb-3 font-mono text-[0.66rem] uppercase tracking-[0.2em] text-dim">
        instellingen
      </h3>

      {/* Weekpatroon-editor */}
      <div className="overflow-hidden rounded-2xl border border-line bg-raised">
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
                        : slots
                            .map((s) => `${s.slot_start}–${s.slot_end}`)
                            .join(" · ")}
                    </span>
                  </button>
                </li>
              );
            })}
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
