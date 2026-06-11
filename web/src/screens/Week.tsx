import { useMemo, useState } from "react";
import {
  DndContext,
  DragOverlay,
  PointerSensor,
  TouchSensor,
  useDraggable,
  useDroppable,
  useSensor,
  useSensors,
} from "@dnd-kit/core";
import type { DragEndEvent, DragStartEvent } from "@dnd-kit/core";
import { isUnavailable } from "../api/client";
import {
  keys,
  useMovePlacement,
  usePlanWeek,
  useSeason,
  useWeek,
} from "../api/queries";
import type { AvailabilitySlot, EventSummary } from "../api/types";
import OfflineBanner, { useOnline } from "../components/OfflineBanner";
import Spinner from "../components/Spinner";
import AvailabilitySheet from "../features/AvailabilitySheet";
import MoveDiffSheet from "../features/MoveDiffSheet";
import type { PendingMove } from "../features/MoveDiffSheet";
import {
  addDays,
  dayMonth,
  dayShort,
  isoWeekNumber,
  mondayOf,
  timeOf,
  toMinutes,
  todayISO,
} from "../lib/dates";
import {
  ZONE_VAR,
  durationMin,
  fmtDuration,
  sessionStatus,
  zoneOf,
} from "../lib/workout";
import { useQueryClient } from "@tanstack/react-query";

export default function Week() {
  const today = todayISO();
  const [weekStart, setWeekStart] = useState(() => mondayOf(today));
  const { data, isLoading, isError, error } = useWeek(weekStart);
  const season = useSeason();
  const online = useOnline();
  const qc = useQueryClient();

  const move = useMovePlacement();
  const planWeek = usePlanWeek(weekStart);
  const [pendingMove, setPendingMove] = useState<PendingMove | null>(null);
  const [dragItem, setDragItem] = useState<EventSummary | null>(null);
  const [availDate, setAvailDate] = useState<string | null>(null);
  const [moveError, setMoveError] = useState<string | null>(null);

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 6 } }),
    useSensor(TouchSensor, {
      activationConstraint: { delay: 220, tolerance: 8 },
    }),
  );

  const days = useMemo(
    () => Array.from({ length: 7 }, (_, i) => addDays(weekStart, i)),
    [weekStart],
  );

  const itemsByDay = useMemo(() => {
    const map: Record<string, EventSummary[]> = {};
    for (const item of data?.items ?? []) {
      if (item.is_note) continue;
      const d = (item.event.start_date_local ?? "").slice(0, 10);
      if (!d) continue;
      (map[d] ??= []).push(item);
    }
    return map;
  }, [data]);

  const totals = useMemo(() => {
    let planned = 0;
    let done = 0;
    let runKm = 0;
    for (const item of data?.items ?? []) {
      if (item.is_note) continue;
      planned += item.event.load_target ?? 0;
      if (item.done && item.activity) {
        done += item.activity.icu_training_load ?? 0;
        if ((item.activity.type ?? "").includes("Run"))
          runKm += (item.activity.distance ?? 0) / 1000;
      }
    }
    return { planned: Math.round(planned), done: Math.round(done), runKm };
  }, [data]);

  const phaseInfo = useMemo(() => {
    const row = season.data?.plan_weeks?.find((w) => w.week_start === weekStart);
    if (!row) return null;
    return { phase: row.phase ?? "", deload: Boolean(row.is_deload) };
  }, [season.data, weekStart]);

  const isDraggable = (item: EventSummary) => {
    const d = (item.event.start_date_local ?? "").slice(0, 10);
    return (
      !item.done &&
      item.event.category !== "NOTE" &&
      d >= today
    );
  };

  const onDragStart = (e: DragStartEvent) => {
    setMoveError(null);
    setDragItem((e.active.data.current as { item: EventSummary }).item);
  };

  const onDragEnd = (e: DragEndEvent) => {
    const item = dragItem;
    setDragItem(null);
    if (!item || !e.over) return;
    const targetDate = String(e.over.id);
    const fromDate = (item.event.start_date_local ?? "").slice(0, 10);
    if (targetDate === fromDate) return;
    const eventId = String(item.event.id);
    move.mutate(
      { eventId, targetDate, apply: false },
      {
        onSuccess: (result) =>
          setPendingMove({
            eventId,
            eventName: item.event.name ?? "?",
            targetDate,
            result,
          }),
        onError: (err) =>
          setMoveError(
            err instanceof Error ? err.message.replace(/^\d+:\s*/, "") : "Verplaatsen kan niet.",
          ),
      },
    );
  };

  const confirmMove = () => {
    if (!pendingMove) return;
    move.mutate(
      { eventId: pendingMove.eventId, targetDate: pendingMove.targetDate, apply: true },
      {
        onSuccess: () => {
          setPendingMove(null);
          qc.invalidateQueries({ queryKey: keys.week(weekStart) });
          qc.invalidateQueries({ queryKey: keys.today });
        },
        onError: (err) => {
          setPendingMove(null);
          setMoveError(err instanceof Error ? err.message : "Toepassen mislukt.");
        },
      },
    );
  };

  if (isLoading) return <Spinner label="Week laden…" />;

  if (!data) {
    return (
      <div className="py-16 text-center">
        <p className="font-display text-xl font-semibold">Geen verbinding</p>
        <p className="mt-2 text-sm text-muted">
          Weekdata is nu niet op te halen.
        </p>
      </div>
    );
  }

  const stale = !online || (isError && isUnavailable(error));
  const hasWorkouts = (data.items ?? []).some((i) => !i.is_note);

  return (
    <DndContext sensors={sensors} onDragStart={onDragStart} onDragEnd={onDragEnd}>
      <div>
        {/* Sticky weeknav + totalen */}
        <header className="sticky top-0 z-30 -mx-5 mb-4 border-b border-line bg-bg/95 px-5 pb-3 pt-3 backdrop-blur-md">
          <div className="flex items-center justify-between">
            <button
              aria-label="Vorige week"
              onClick={() => setWeekStart((w) => addDays(w, -7))}
              className="rounded-lg border border-line p-2 text-muted hover:border-accent hover:text-ink"
            >
              <Chevron dir="left" />
            </button>
            <div className="text-center">
              <h1 className="font-display text-lg font-semibold leading-tight">
                Week {isoWeekNumber(weekStart)}
              </h1>
              <p className="font-mono text-[0.64rem] uppercase tracking-[0.16em] text-dim">
                {dayMonth(weekStart)} – {dayMonth(addDays(weekStart, 6))}
                {phaseInfo && (
                  <>
                    {" · "}
                    <span className="text-accent">{fmtPhase(phaseInfo.phase)}</span>
                    {phaseInfo.deload && (
                      <span className="text-positive"> · deload</span>
                    )}
                  </>
                )}
              </p>
            </div>
            <button
              aria-label="Volgende week"
              onClick={() => setWeekStart((w) => addDays(w, 7))}
              className="rounded-lg border border-line p-2 text-muted hover:border-accent hover:text-ink"
            >
              <Chevron dir="right" />
            </button>
          </div>
          <div className="mt-2.5 flex items-center justify-center gap-5 font-mono text-[0.72rem] text-muted">
            <span>
              tss <span className="text-ink">{totals.done}</span>
              <span className="text-dim">/{totals.planned}</span>
            </span>
            <span className="text-dim">·</span>
            <span>
              run <span className="text-ink">{totals.runKm.toFixed(1)}</span> km
            </span>
          </div>
        </header>

        <OfflineBanner show={stale} />
        {moveError && (
          <div className="mb-4 rounded-xl border border-alert/40 bg-alert/10 px-3.5 py-2.5 text-[0.8rem] text-alert">
            {moveError}
          </div>
        )}

        {!hasWorkouts && (
          <div className="rise-in mb-5 rounded-2xl border border-line bg-raised px-5 py-7 text-center">
            <p className="font-display text-lg font-semibold">Nog niets gepland</p>
            <p className="mx-auto mt-1.5 max-w-[260px] text-sm text-muted">
              Laat de planner deze week vullen op basis van je beschikbaarheid.
            </p>
            <button
              onClick={() => planWeek.mutate()}
              disabled={planWeek.isPending}
              className="mt-4 rounded-xl bg-accent px-6 py-2.5 text-sm font-semibold text-white hover:bg-accent-hover disabled:opacity-50"
            >
              {planWeek.isPending ? "Plannen…" : "Plan week"}
            </button>
            {planWeek.isError && (
              <p className="mt-2.5 text-[0.78rem] text-alert">
                Plannen mislukt — staat je beschikbaarheid goed?
              </p>
            )}
          </div>
        )}

        <div className="space-y-3 rise-in">
          {days.map((d) => (
            <DayRow
              key={d}
              date={d}
              today={today}
              items={itemsByDay[d] ?? []}
              slots={data.availability[d] ?? []}
              isDraggable={isDraggable}
              onEditAvailability={() => setAvailDate(d)}
            />
          ))}
        </div>

        <DragOverlay dropAnimation={null}>
          {dragItem && <SessionCard item={dragItem} today={today} overlay />}
        </DragOverlay>

        <MoveDiffSheet
          pending={pendingMove}
          busy={move.isPending}
          onConfirm={confirmMove}
          onClose={() => setPendingMove(null)}
        />
        {availDate && (
          <AvailabilitySheet
            date={availDate}
            initial={data.availability[availDate] ?? []}
            weekStart={weekStart}
            onClose={() => setAvailDate(null)}
          />
        )}
      </div>
    </DndContext>
  );
}

function fmtPhase(phase: string): string {
  return phase.replace(/_/g, " ");
}

// ── Dag ───────────────────────────────────────────────────────────────────

const DAY_START = 6 * 60; // tijdbalk toont 06:00–23:00
const DAY_SPAN = 17 * 60;

function DayRow({
  date,
  today,
  items,
  slots,
  isDraggable,
  onEditAvailability,
}: {
  date: string;
  today: string;
  items: EventSummary[];
  slots: AvailabilitySlot[];
  isDraggable: (item: EventSummary) => boolean;
  onEditAvailability: () => void;
}) {
  const { isOver, setNodeRef } = useDroppable({ id: date });
  const isToday = date === today;

  return (
    <section
      ref={setNodeRef}
      data-day={date}
      className={`rounded-2xl border px-4 py-3.5 transition-colors ${
        isOver
          ? "border-accent bg-[var(--accent-bg)]"
          : isToday
            ? "border-line-strong bg-raised"
            : "border-line bg-raised/60"
      }`}
    >
      <button
        onClick={onEditAvailability}
        className="block w-full text-left"
        aria-label={`Beschikbaarheid ${date} bewerken`}
      >
        <div className="flex items-baseline justify-between">
          <span
            className={`text-[0.8rem] font-semibold capitalize ${isToday ? "text-accent" : ""}`}
          >
            {dayShort(date)}{" "}
            <span className="font-mono text-[0.68rem] font-normal text-dim">
              {dayMonth(date)}
            </span>
            {isToday && (
              <span className="ml-1.5 font-mono text-[0.58rem] uppercase tracking-[0.16em] text-accent">
                vandaag
              </span>
            )}
          </span>
          <span className="font-mono text-[0.62rem] text-dim">
            {slots.length === 0
              ? "geen venster"
              : slots.map((s) => `${s.start}–${s.end}`).join(" · ")}
          </span>
        </div>
        {/* Beschikbaarheid als dunne tijdbalk */}
        <div className="relative mt-2 h-[3px] overflow-hidden rounded-full bg-elevated">
          {slots.map((s, i) => {
            const left = Math.max(0, ((toMinutes(s.start) - DAY_START) / DAY_SPAN) * 100);
            const width = Math.min(
              100 - left,
              ((toMinutes(s.end) - toMinutes(s.start)) / DAY_SPAN) * 100,
            );
            return (
              <span
                key={i}
                className="absolute top-0 h-full rounded-full bg-line-strong"
                style={{ left: `${left}%`, width: `${width}%` }}
              />
            );
          })}
        </div>
      </button>

      {items.length > 0 && (
        <div className="mt-3 space-y-2">
          {items.map((item) =>
            isDraggable(item) ? (
              <DraggableSession key={String(item.event.id)} item={item} today={today} />
            ) : (
              <SessionCard key={String(item.event.id)} item={item} today={today} />
            ),
          )}
        </div>
      )}
    </section>
  );
}

// ── Sessiekaart ───────────────────────────────────────────────────────────

function DraggableSession({ item, today }: { item: EventSummary; today: string }) {
  const { attributes, listeners, setNodeRef, isDragging } = useDraggable({
    id: String(item.event.id),
    data: { item },
  });
  return (
    <div
      ref={setNodeRef}
      {...listeners}
      {...attributes}
      className={isDragging ? "opacity-30" : "cursor-grab touch-none"}
    >
      <SessionCard item={item} today={today} draggable />
    </div>
  );
}

function SessionCard({
  item,
  today,
  overlay = false,
  draggable = false,
}: {
  item: EventSummary;
  today: string;
  overlay?: boolean;
  draggable?: boolean;
}) {
  const e = item.event;
  const zone = zoneOf(e);
  const status = sessionStatus(item, today);
  const t = timeOf(e.start_date_local) ?? item.placement?.slot_start ?? null;
  const dur = item.done && item.activity
    ? Math.round((item.activity.moving_time ?? 0) / 60)
    : durationMin(e);
  const tss = item.done && item.activity
    ? item.activity.icu_training_load
    : e.load_target;

  return (
    <div
      data-session={String(e.id)}
      className={`flex items-center gap-3 rounded-xl border bg-elevated px-3.5 py-2.5 ${
        overlay
          ? "border-accent shadow-[0_8px_30px_rgba(0,0,0,0.55)]"
          : "border-line"
      } ${status === "done" ? "opacity-75" : ""} ${status === "missed" ? "opacity-55" : ""}`}
    >
      <span
        className="h-9 w-1 shrink-0 rounded-full"
        style={{ background: ZONE_VAR[zone] }}
      />
      <div className="min-w-0 flex-1">
        <p className="truncate text-[0.86rem] font-medium leading-snug">
          {e.name ?? "Workout"}
        </p>
        <p className="mt-0.5 font-mono text-[0.68rem] text-muted">
          {fmtDuration(dur)}
          {tss != null && ` · ${Math.round(tss)} tss`}
          {t && status === "planned" && ` · ${t}`}
        </p>
      </div>
      <StatusMark status={status} />
      {draggable && !overlay && (
        <svg width="13" height="13" viewBox="0 0 24 24" fill="currentColor" className="shrink-0 text-dim">
          <circle cx="9" cy="6" r="1.6" /><circle cx="15" cy="6" r="1.6" />
          <circle cx="9" cy="12" r="1.6" /><circle cx="15" cy="12" r="1.6" />
          <circle cx="9" cy="18" r="1.6" /><circle cx="15" cy="18" r="1.6" />
        </svg>
      )}
    </div>
  );
}

function StatusMark({ status }: { status: "done" | "missed" | "planned" }) {
  if (status === "done") {
    return (
      <span className="shrink-0 text-positive" title="Gedaan">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round">
          <path d="M5 12.5l4.5 4.5L19 7.5" />
        </svg>
      </span>
    );
  }
  if (status === "missed") {
    return (
      <span className="shrink-0 font-mono text-[0.58rem] uppercase tracking-[0.14em] text-dim">
        gemist
      </span>
    );
  }
  return null;
}

function Chevron({ dir }: { dir: "left" | "right" }) {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      {dir === "left" ? <path d="M15 6l-6 6 6 6" /> : <path d="M9 6l6 6-6 6" />}
    </svg>
  );
}
