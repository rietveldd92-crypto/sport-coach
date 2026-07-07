import { useMemo, useState } from "react";
import BottomSheet from "../components/BottomSheet";
import { useCreateGoal, useReplaceGoal } from "../api/queries";
import type { Goal, GoalCreate, GoalCreateResult, GoalType } from "../api/types";
import { addDays, longDate, todayISO } from "../lib/dates";
import {
  GOAL_TYPES,
  fmtPhase,
  phaseColor,
  previewBlocks,
  weeksUntil,
} from "../lib/season";

interface Props {
  open: boolean;
  onClose: () => void;
  activeGoal?: Goal | null;
}

/** Goal wizard (UPGRADE_PLAN §4.3): type+datum → streeftijd+prioriteit →
 *  blok-preview + haalbaarheid → bevestigen = POST /api/goals. */
export default function GoalWizardSheet({ open, onClose, activeGoal }: Props) {
  const today = todayISO();
  const [step, setStep] = useState(0);
  const [type, setType] = useState<GoalType>("marathon");
  const [eventDate, setEventDate] = useState(() => addDays(today, 7 * 18));
  const [target, setTarget] = useState("");
  const [priority, setPriority] = useState<"A" | "B" | "C">("A");
  const create = useCreateGoal();
  const replace = useReplaceGoal();

  const meta = GOAL_TYPES.find((g) => g.value === type) ?? GOAL_TYPES[0];
  const weeks = weeksUntil(eventDate, today);
  const blocks = useMemo(() => previewBlocks(weeks), [weeks]);

  const reset = () => {
    setStep(0);
    create.reset();
    replace.reset();
  };

  const close = () => {
    reset();
    onClose();
  };

  const confirm = () => {
    const body: GoalCreate = {
      type,
      sport: meta.sport,
      event_date: eventDate,
      target_value: target.trim() || null,
      priority,
    };
    if (priority === "A" && activeGoal?.id && activeGoal.id > 0) {
      const oldLabel =
        GOAL_TYPES.find((g) => g.value === activeGoal.type)?.label ??
        activeGoal.type;
      const ok = window.confirm(
        `Er is al een A-doel (${oldLabel}). Wil je dit doel verwijderen en vervangen door je nieuwe doel?`,
      );
      if (!ok) return;
      replace.mutate({ goalId: activeGoal.id, body });
      return;
    }
    create.mutate(body);
  };

  const result = create.data ?? replace.data ?? null;
  const busy = create.isPending || replace.isPending;
  const isError = create.isError || replace.isError;
  const error = create.error ?? replace.error;

  return (
    <BottomSheet open={open} onClose={close} title="Nieuw doel">
      {/* Stappen-indicator */}
      <div className="mb-5 flex items-center gap-1.5">
        {[0, 1, 2].map((i) => (
          <span
            key={i}
            className={`h-1 flex-1 rounded-full transition-colors ${
              i <= step ? "bg-accent" : "bg-line-strong"
            }`}
          />
        ))}
      </div>

      {result ? (
        <DoneStep result={result} onClose={close} />
      ) : step === 0 ? (
        <StepTypeDate
          type={type}
          eventDate={eventDate}
          today={today}
          onType={setType}
          onDate={setEventDate}
          onNext={() => setStep(1)}
        />
      ) : step === 1 ? (
        <StepTarget
          target={target}
          priority={priority}
          hint={meta.targetHint}
          label={meta.targetLabel}
          onTarget={setTarget}
          onPriority={setPriority}
          onBack={() => setStep(0)}
          onNext={() => setStep(2)}
        />
      ) : (
        <StepPreview
          typeLabel={meta.label}
          eventDate={eventDate}
          target={target}
          priority={priority}
          weeks={weeks}
          blocks={blocks}
          busy={busy}
          error={
            isError
              ? (error as Error)?.message?.includes("409")
                ? "Er is al een actief A-doel. Bevestig vervangen, of kies prioriteit B/C."
                : "Doel aanmaken mislukt — probeer het opnieuw."
              : null
          }
          onBack={() => setStep(1)}
          onConfirm={confirm}
        />
      )}
    </BottomSheet>
  );
}

// ── Stap 1: type + datum ──────────────────────────────────────────────────

function StepTypeDate({
  type,
  eventDate,
  today,
  onType,
  onDate,
  onNext,
}: {
  type: GoalType;
  eventDate: string;
  today: string;
  onType: (t: GoalType) => void;
  onDate: (d: string) => void;
  onNext: () => void;
}) {
  const valid = eventDate > today;
  return (
    <div className="space-y-5 pb-2">
      <div>
        <SheetLabel>doeltype</SheetLabel>
        <div className="grid grid-cols-2 gap-2">
          {GOAL_TYPES.map((g) => (
            <button
              key={g.value}
              onClick={() => onType(g.value)}
              className={`rounded-xl border px-3.5 py-3 text-left text-sm font-medium transition-colors ${
                type === g.value
                  ? "border-accent bg-[var(--accent-bg)] text-ink"
                  : "border-line bg-elevated text-muted hover:border-line-strong"
              }`}
            >
              {g.label}
              <span className="mt-0.5 block font-mono text-[0.6rem] uppercase tracking-[0.14em] text-dim">
                {g.sport === "run" ? "lopen" : g.sport === "ride" ? "fietsen" : "multi"}
              </span>
            </button>
          ))}
        </div>
      </div>

      <div>
        <SheetLabel>datum</SheetLabel>
        <input
          type="date"
          value={eventDate}
          min={addDays(today, 1)}
          onChange={(e) => onDate(e.target.value)}
          className="w-full rounded-xl border border-line-strong bg-elevated px-3.5 py-2.5 font-mono text-sm text-ink [color-scheme:dark]"
        />
        {valid && (
          <p className="mt-2 font-mono text-[0.7rem] text-muted">
            {longDate(eventDate)} · over {weeksUntil(eventDate, today)} weken
          </p>
        )}
      </div>

      <button
        data-testid="wizard-next"
        onClick={onNext}
        disabled={!valid}
        className="w-full rounded-xl bg-accent py-3 text-sm font-semibold text-white hover:bg-accent-hover disabled:opacity-50"
      >
        Verder
      </button>
    </div>
  );
}

// ── Stap 2: streeftijd + prioriteit ───────────────────────────────────────

function StepTarget({
  target,
  priority,
  hint,
  label,
  onTarget,
  onPriority,
  onBack,
  onNext,
}: {
  target: string;
  priority: "A" | "B" | "C";
  hint: string;
  label: string;
  onTarget: (v: string) => void;
  onPriority: (p: "A" | "B" | "C") => void;
  onBack: () => void;
  onNext: () => void;
}) {
  return (
    <div className="space-y-5 pb-2">
      <div>
        <SheetLabel>{label} (optioneel)</SheetLabel>
        <input
          type="text"
          value={target}
          placeholder={hint}
          onChange={(e) => onTarget(e.target.value)}
          className="w-full rounded-xl border border-line-strong bg-elevated px-3.5 py-2.5 font-mono text-sm text-ink placeholder:text-dim"
        />
      </div>

      <div>
        <SheetLabel>prioriteit</SheetLabel>
        <div className="flex gap-2">
          {(["A", "B", "C"] as const).map((p) => (
            <button
              key={p}
              onClick={() => onPriority(p)}
              className={`flex-1 rounded-xl border py-2.5 font-mono text-sm font-semibold transition-colors ${
                priority === p
                  ? "border-accent bg-[var(--accent-bg)] text-ink"
                  : "border-line bg-elevated text-muted hover:border-line-strong"
              }`}
            >
              {p}
            </button>
          ))}
        </div>
        <p className="mt-2 text-[0.76rem] leading-relaxed text-muted">
          {priority === "A"
            ? "Hoofddoel — krijgt een volledig macroplan met blokperiodisering."
            : "Tussendoel — mini-taper + korte recovery in het bestaande plan."}
        </p>
      </div>

      <div className="flex gap-2.5">
        <BackButton onClick={onBack} />
        <button
          data-testid="wizard-next"
          onClick={onNext}
          className="flex-1 rounded-xl bg-accent py-3 text-sm font-semibold text-white hover:bg-accent-hover"
        >
          Verder
        </button>
      </div>
    </div>
  );
}

// ── Stap 3: preview + bevestigen ──────────────────────────────────────────

function StepPreview({
  typeLabel,
  eventDate,
  target,
  priority,
  weeks,
  blocks,
  busy,
  error,
  onBack,
  onConfirm,
}: {
  typeLabel: string;
  eventDate: string;
  target: string;
  priority: "A" | "B" | "C";
  weeks: number;
  blocks: { phase: string; weeks: number }[];
  busy: boolean;
  error: string | null;
  onBack: () => void;
  onConfirm: () => void;
}) {
  return (
    <div className="space-y-5 pb-2">
      <div className="rounded-xl border border-line bg-elevated px-4 py-3.5">
        <p className="font-display text-lg font-semibold">
          {typeLabel}
          {target && (
            <span className="ml-2 font-mono text-[0.85rem] font-normal text-accent">
              {target}
            </span>
          )}
        </p>
        <p className="mt-1 font-mono text-[0.7rem] text-muted">
          {longDate(eventDate)} · {weeks} weken · prioriteit {priority}
        </p>
      </div>

      {priority === "A" ? (
        <div>
          <SheetLabel>voorgestelde blokken</SheetLabel>
          <div className="flex h-9 w-full gap-[2px] overflow-hidden rounded-lg">
            {blocks.map((b) => (
              <span
                key={b.phase}
                title={`${fmtPhase(b.phase)} · ${b.weeks} wk`}
                className="h-full"
                style={{
                  background: phaseColor(b.phase),
                  flexGrow: b.weeks,
                  flexBasis: 0,
                }}
              />
            ))}
          </div>
          <div className="mt-2 space-y-1">
            {blocks.map((b) => (
              <div
                key={b.phase}
                className="flex items-center gap-2 font-mono text-[0.7rem] text-muted"
              >
                <span
                  className="h-2 w-2 rounded-sm"
                  style={{ background: phaseColor(b.phase) }}
                />
                <span className="capitalize">{fmtPhase(b.phase)}</span>
                <span className="ml-auto">{b.weeks} wk</span>
              </div>
            ))}
          </div>
          <p className="mt-3 text-[0.74rem] leading-relaxed text-dim">
            Indicatief — de generator bepaalt het exacte plan op basis van je
            huidige CTL en recente volume.
          </p>
        </div>
      ) : (
        <p className="text-sm leading-relaxed text-muted">
          Tussendoel: geen eigen macroplan, wel een mini-taper en korte
          recovery rond de wedstrijddatum.
        </p>
      )}

      {weeks < 12 && priority === "A" && (
        <p className="rounded-xl border border-warning/40 bg-warning/10 px-3.5 py-2.5 text-[0.8rem] text-warning">
          Korte aanloop ({weeks} wk) — het doel is mogelijk niet volledig
          haalbaar.
        </p>
      )}

      {error && <p className="text-sm text-alert">{error}</p>}

      <div className="flex gap-2.5">
        <BackButton onClick={onBack} />
        <button
          data-testid="wizard-confirm"
          onClick={onConfirm}
          disabled={busy}
          className="flex-1 rounded-xl bg-accent py-3 text-sm font-semibold text-white hover:bg-accent-hover disabled:opacity-50"
        >
          {busy ? "Plan genereren…" : "Bevestigen"}
        </button>
      </div>
    </div>
  );
}

// ── Resultaat ─────────────────────────────────────────────────────────────

function DoneStep({
  result,
  onClose,
}: {
  result: GoalCreateResult;
  onClose: () => void;
}) {
  const gen = result.generation;
  return (
    <div className="space-y-4 pb-2">
      <div className="rounded-xl border border-positive/40 bg-positive/10 px-4 py-3.5 text-sm text-positive">
        Doel aangemaakt
        {gen
          ? ` — macroplan met ${gen.plan_weeks} weken gegenereerd` +
            (gen.peak_km ? `, piekweek ${Math.round(gen.peak_km)} km.` : ".")
          : "."}
      </div>
      {gen?.warnings?.length ? (
        <ul className="space-y-1.5">
          {gen.warnings.map((w, i) => (
            <li key={i} className="text-[0.8rem] leading-relaxed text-warning">
              {w}
            </li>
          ))}
        </ul>
      ) : null}
      <button
        onClick={onClose}
        className="w-full rounded-xl bg-accent py-3 text-sm font-semibold text-white hover:bg-accent-hover"
      >
        Naar het seizoen
      </button>
    </div>
  );
}

// ── Kleine bouwstenen ─────────────────────────────────────────────────────

function SheetLabel({ children }: { children: React.ReactNode }) {
  return (
    <p className="mb-2 font-mono text-[0.62rem] uppercase tracking-[0.18em] text-dim">
      {children}
    </p>
  );
}

function BackButton({ onClick }: { onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className="rounded-xl border border-line-strong px-5 py-3 text-sm font-medium text-muted hover:border-accent hover:text-ink"
    >
      Terug
    </button>
  );
}
