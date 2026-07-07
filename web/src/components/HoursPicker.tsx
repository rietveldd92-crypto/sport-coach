interface Props {
  minutes: number; // 0 = rustdag
  onChange: (minutes: number) => void;
}

const CHIPS: { label: string; minutes: number }[] = [
  { label: "Rustdag", minutes: 0 },
  { label: "1u", minutes: 60 },
  { label: "1,5u", minutes: 90 },
  { label: "2u", minutes: 120 },
  { label: "3u", minutes: 180 },
  { label: "4u", minutes: 240 },
];

const MIN_MINUTES = 0;
const MAX_MINUTES = 360; // 6u
const STEP_MINUTES = 30;

function bigLabel(minutes: number): string {
  if (minutes <= 0) return "rustdag";
  const hours = minutes / 60;
  const str = Number.isInteger(hours)
    ? String(hours)
    : hours.toFixed(1).replace(".", ",");
  return `${str} uur`;
}

/** Urenkiezer voor beschikbaarheid: chips voor veelgebruikte waarden + een
 *  ±30min-stepper voor tussenwaarden. Geen tijden, alleen een aantal uur. */
export default function HoursPicker({ minutes, onChange }: Props) {
  const clamp = (v: number) => Math.min(MAX_MINUTES, Math.max(MIN_MINUTES, v));

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-2">
        {CHIPS.map((c) => (
          <button
            key={c.label}
            type="button"
            onClick={() => onChange(c.minutes)}
            className={`rounded-full border px-3.5 py-1.5 text-[0.78rem] font-medium transition-colors ${
              minutes === c.minutes
                ? "border-accent bg-accent/15 text-ink"
                : "border-line-strong text-muted hover:border-accent/50"
            }`}
          >
            {c.label}
          </button>
        ))}
      </div>

      <div className="flex items-center justify-center gap-5 rounded-xl border border-line bg-elevated px-4 py-4">
        <button
          type="button"
          aria-label="30 minuten minder"
          onClick={() => onChange(clamp(minutes - STEP_MINUTES))}
          disabled={minutes <= MIN_MINUTES}
          className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full border border-line-strong text-lg leading-none text-muted transition-colors hover:border-accent hover:text-ink disabled:opacity-30"
        >
          −
        </button>
        <p className="font-display min-w-[7ch] text-center text-2xl font-semibold">
          {bigLabel(minutes)}
        </p>
        <button
          type="button"
          aria-label="30 minuten meer"
          onClick={() => onChange(clamp(minutes + STEP_MINUTES))}
          disabled={minutes >= MAX_MINUTES}
          className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full border border-line-strong text-lg leading-none text-muted transition-colors hover:border-accent hover:text-ink disabled:opacity-30"
        >
          +
        </button>
      </div>
    </div>
  );
}
