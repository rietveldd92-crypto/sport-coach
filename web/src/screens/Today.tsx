import { useEffect, useState } from "react";
import { isAuthError, isUnavailable } from "../api/client";
import { useSyncTp, useToday } from "../api/queries";
import type { EventSummary, TodayView } from "../api/types";
import { InjuryBadge, SportBadge, ZoneChip } from "../components/Badges";
import OfflineBanner, { useOnline } from "../components/OfflineBanner";
import Spinner from "../components/Spinner";
import CheckinSheet from "../features/CheckinSheet";
import SwapSheet from "../features/SwapSheet";
import { longDate, timeOf } from "../lib/dates";
import {
  ZONE_VAR,
  durationMin,
  fmtDuration,
  isSyncable,
  parseDescription,
  sportKind,
  zoneOf,
} from "../lib/workout";

export default function Today() {
  const { data, isLoading, isError, error, refetch } = useToday();
  const online = useOnline();
  const [checkinOpen, setCheckinOpen] = useState(false);
  const [swapOpen, setSwapOpen] = useState(false);

  // Eerste bezoek van de dag zonder checkin → sheet vanzelf openen.
  useEffect(() => {
    if (!data) return;
    const key = `checkin-prompted-${data.date}`;
    if (!data.checkin.done && !localStorage.getItem(key)) {
      localStorage.setItem(key, "1");
      setCheckinOpen(true);
    }
  }, [data]);

  if (isLoading) return <Spinner label="Vandaag laden…" />;

  if (!data) {
    const auth = isAuthError(error);
    return (
      <div className="py-16 text-center">
        <p className="font-display text-xl font-semibold">
          {auth ? "Niet gekoppeld" : "Geen verbinding"}
        </p>
        <p className="mx-auto mt-2 max-w-[260px] text-sm leading-relaxed text-muted">
          {auth
            ? "Open de app één keer via de link met ?token=… om hem aan de server te koppelen."
            : "De coach is even onbereikbaar en er is nog geen eerdere data om te tonen."}
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
  const workout = data.workout;

  return (
    <div>
      <OfflineBanner show={stale} />

      <header className="rise-in mb-6 flex items-start justify-between gap-3">
        <div>
          <p className="font-mono text-[0.66rem] uppercase tracking-[0.2em] text-dim">
            {longDate(data.date)}
          </p>
          <h1 className="font-display mt-1.5 text-2xl font-semibold">
            Vandaag
          </h1>
        </div>
        <div className="flex flex-col items-end gap-2">
          <InjuryBadge guard={data.injury_guard} />
          <CheckinChip view={data} onOpen={() => setCheckinOpen(true)} />
        </div>
      </header>

      {workout ? (
        <HeroCard
          workout={workout}
          onSwap={() => setSwapOpen(true)}
        />
      ) : (
        <RestCard />
      )}

      <TomorrowPreview items={data.tomorrow} />

      <CheckinSheet open={checkinOpen} onClose={() => setCheckinOpen(false)} />
      {workout && (
        <SwapSheet
          open={swapOpen}
          onClose={() => setSwapOpen(false)}
          eventId={workout.event.id}
        />
      )}
    </div>
  );
}

// ── Header-chip: checkin-status / knop ────────────────────────────────────

const RECOVERY_TONE: Record<string, string> = {
  go: "border-positive/40 text-positive",
  easy: "border-warning/40 text-warning",
  rust: "border-alert/40 text-alert",
};

function CheckinChip({ view, onOpen }: { view: TodayView; onOpen: () => void }) {
  if (!view.checkin.done) {
    return (
      <button
        data-testid="open-checkin"
        onClick={onOpen}
        className="rounded-full bg-accent px-3.5 py-1.5 text-[0.72rem] font-semibold text-white transition-colors hover:bg-accent-hover"
      >
        Check-in
      </button>
    );
  }
  const level = view.checkin.recovery.level;
  return (
    <button
      data-testid="open-checkin"
      onClick={onOpen}
      title={view.checkin.recovery.message}
      className={`rounded-full border px-3 py-1 font-mono text-[0.62rem] uppercase tracking-[0.14em] ${RECOVERY_TONE[level] ?? RECOVERY_TONE.easy}`}
    >
      checkin · {level}
    </button>
  );
}

// ── Hero ──────────────────────────────────────────────────────────────────

function HeroCard({
  workout,
  onSwap,
}: {
  workout: EventSummary & { coach_note: string | null };
  onSwap: () => void;
}) {
  const event = workout.event;
  const zone = zoneOf(event);
  const kind = sportKind(event);
  const startTime = timeOf(event.start_date_local) ?? workout.placement?.slot_start ?? null;
  const dur = durationMin(event);
  const tss = event.load_target ?? null;
  const doneKey = `done-local-${event.id}`;
  const [localDone, setLocalDone] = useState(
    () => localStorage.getItem(doneKey) === "1",
  );
  const done = workout.done || localDone;
  const sync = useSyncTp();

  const toggleDone = () => {
    if (workout.done) return; // echte activity wint altijd
    const next = !localDone;
    setLocalDone(next);
    localStorage.setItem(doneKey, next ? "1" : "0");
  };

  return (
    <section className="rise-in relative overflow-hidden rounded-2xl border border-line bg-raised">
      <div
        className="absolute inset-x-0 top-0 h-[3px]"
        style={{ background: ZONE_VAR[zone] }}
      />
      <div className="px-5 pb-5 pt-6">
        <div className="flex flex-wrap items-center gap-2.5">
          <SportBadge kind={kind} />
          {startTime && (
            <span className="font-mono text-[0.8rem] text-muted">
              {startTime}
            </span>
          )}
          {done && (
            <span className="ml-auto inline-flex items-center gap-1.5 font-mono text-[0.66rem] uppercase tracking-[0.14em] text-positive">
              <CheckIcon /> gedaan
            </span>
          )}
        </div>

        <h2 className="font-display mt-4 text-[2.1rem] font-semibold leading-[1.04]">
          {event.name ?? "Workout"}
        </h2>

        <div className="mt-5 flex items-center gap-6">
          <Metric label="duur" value={fmtDuration(dur)} />
          <Metric label="tss" value={tss != null ? String(Math.round(tss)) : "—"} />
          <ZoneChip zone={zone} />
        </div>

        {workout.activity && (
          <p className="mt-3 font-mono text-[0.74rem] text-muted">
            gereden: {fmtDuration(Math.round((workout.activity.moving_time ?? 0) / 60))}
            {" · "}
            {Math.round(workout.activity.icu_training_load ?? 0)} tss
          </p>
        )}

        <Description text={event.description} />

        {workout.coach_note && <CoachNote note={workout.coach_note} />}

        <div className="mt-6 flex gap-2.5">
          <button
            onClick={toggleDone}
            data-testid="done-toggle"
            className={`flex flex-1 items-center justify-center gap-2 rounded-xl border py-3 text-sm font-semibold transition-colors ${
              done
                ? "border-positive/50 bg-positive/10 text-positive"
                : "border-line-strong hover:border-positive/60"
            }`}
          >
            <CheckIcon />
            {done ? "Gedaan" : "Done"}
          </button>
          {!done && (
            <button
              onClick={onSwap}
              data-testid="open-swap"
              className="flex flex-1 items-center justify-center gap-2 rounded-xl border border-line-strong py-3 text-sm font-semibold transition-colors hover:border-accent"
            >
              <SwapIcon />
              Swap
            </button>
          )}
          {isSyncable(workout) && (
            <button
              onClick={() => sync.mutate(event.id)}
              disabled={sync.isPending || sync.isSuccess}
              className="flex flex-1 items-center justify-center gap-2 rounded-xl border border-line-strong py-3 text-sm font-semibold transition-colors hover:border-accent disabled:opacity-60"
            >
              <BoltIcon />
              {sync.isSuccess ? "Gesynct" : "Zwift"}
            </button>
          )}
        </div>
        {sync.isError && (
          <p className="mt-2.5 text-[0.78rem] text-warning">
            Sync niet gelukt: {(sync.error as Error)?.message?.includes("409")
              ? "TP-sync staat uit (TP_SYNC_ENABLED)."
              : "probeer het later opnieuw."}
          </p>
        )}
      </div>
    </section>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="font-mono text-[1.05rem] font-medium">{value}</div>
      <div className="font-mono text-[0.6rem] uppercase tracking-[0.18em] text-dim">
        {label}
      </div>
    </div>
  );
}

function Description({ text }: { text?: string | null }) {
  const [open, setOpen] = useState(false);
  const lines = parseDescription(text);
  if (!lines.length) return null;
  return (
    <div className="mt-5 border-t border-line pt-4">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between text-left text-[0.78rem] font-medium uppercase tracking-[0.14em] text-muted"
      >
        Opbouw
        <svg
          width="14"
          height="14"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          className={`transition-transform ${open ? "rotate-180" : ""}`}
        >
          <path d="M6 9l6 6 6-6" />
        </svg>
      </button>
      {open && (
        <div className="mt-3 space-y-1.5 font-mono text-[0.8rem] leading-relaxed">
          {lines.map((line, i) =>
            line.kind === "repeat" ? (
              <p key={i} className="pt-1 font-semibold text-accent">
                {line.text}
              </p>
            ) : (
              <p key={i} className={line.kind === "step" ? "pl-3 text-ink" : "text-muted"}>
                {line.kind === "step" && (
                  <span className="-ml-3 pr-2 text-dim">·</span>
                )}
                {line.text}
              </p>
            ),
          )}
        </div>
      )}
    </div>
  );
}

function CoachNote({ note }: { note: string }) {
  return (
    <blockquote className="mt-5 rounded-r-xl border-l-2 border-accent bg-[var(--accent-bg)] px-4 py-3.5">
      <p className="font-display text-[0.95rem] italic leading-relaxed text-ink/90">
        {note}
      </p>
      <footer className="mt-1.5 font-mono text-[0.6rem] uppercase tracking-[0.18em] text-muted">
        coach
      </footer>
    </blockquote>
  );
}

// ── Rustdag ───────────────────────────────────────────────────────────────

function RestCard() {
  return (
    <section className="rise-in rounded-2xl border border-line bg-raised px-5 py-10 text-center">
      <p className="font-mono text-[0.66rem] uppercase tracking-[0.2em] text-dim">
        geen sessie gepland
      </p>
      <h2 className="font-display mt-3 text-[2rem] font-semibold">Rustdag</h2>
      <p className="mx-auto mt-3 max-w-[260px] text-sm leading-relaxed text-muted">
        Herstel is ook training. Slaap, eet en laat de benen het werk van
        morgen voorbereiden.
      </p>
    </section>
  );
}

// ── Morgen ────────────────────────────────────────────────────────────────

function TomorrowPreview({ items }: { items: EventSummary[] }) {
  return (
    <section className="rise-in-late mt-8">
      <h3 className="mb-3 font-mono text-[0.66rem] uppercase tracking-[0.2em] text-dim">
        morgen
      </h3>
      {items.length === 0 ? (
        <p className="text-sm text-muted">Niets gepland — rustdag.</p>
      ) : (
        <div className="space-y-2">
          {items.map((item) => {
            const e = item.event;
            const zone = zoneOf(e);
            const t = timeOf(e.start_date_local);
            return (
              <div
                key={String(e.id)}
                className="flex items-center gap-3 rounded-xl border border-line bg-raised px-4 py-3"
              >
                <span
                  className="h-8 w-1 shrink-0 rounded-full"
                  style={{ background: ZONE_VAR[zone] }}
                />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium">{e.name}</p>
                  <p className="mt-0.5 font-mono text-[0.7rem] text-muted">
                    {fmtDuration(durationMin(e))}
                    {e.load_target != null && ` · ${Math.round(e.load_target)} tss`}
                    {t && ` · ${t}`}
                  </p>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </section>
  );
}

// ── Icons ─────────────────────────────────────────────────────────────────

function CheckIcon() {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M5 12.5l4.5 4.5L19 7.5" />
    </svg>
  );
}

function SwapIcon() {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M7 8h11M15 4.5 18.5 8 15 11.5M17 16H6M9 12.5 5.5 16 9 19.5" />
    </svg>
  );
}

function BoltIcon() {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M13 2.5 4.5 13.5H11l-1 8 8.5-11H12l1-8Z" />
    </svg>
  );
}
