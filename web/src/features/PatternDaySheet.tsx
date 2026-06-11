import { useState } from "react";
import BottomSheet from "../components/BottomSheet";
import { usePutPattern } from "../api/queries";
import type { AvailabilitySlot } from "../api/types";

const PRESETS: { label: string; slots: AvailabilitySlot[] }[] = [
  { label: "Ochtend", slots: [{ start: "06:00", end: "08:00", context: "any" }] },
  { label: "Avond", slots: [{ start: "18:00", end: "21:00", context: "any" }] },
  { label: "Rustdag", slots: [] },
];

interface Props {
  weekday: number; // 0=ma .. 6=zo
  dayLabel: string;
  initial: AvailabilitySlot[];
  onClose: () => void;
}

/** Tijdvensters van één weekdag in het terugkerende patroon bewerken
 *  (zelfde slot-UI als AvailabilitySheet, maar → PUT /availability/pattern). */
export default function PatternDaySheet({ weekday, dayLabel, initial, onClose }: Props) {
  const [slots, setSlots] = useState<AvailabilitySlot[]>(initial);
  const pattern = usePutPattern();

  const update = (i: number, patch: Partial<AvailabilitySlot>) =>
    setSlots((cur) => cur.map((s, j) => (j === i ? { ...s, ...patch } : s)));

  const save = () =>
    pattern.mutate({ [weekday]: slots }, { onSuccess: onClose });

  return (
    <BottomSheet open onClose={onClose} title="Weekpatroon">
      <p className="-mt-2 mb-4 font-mono text-[0.68rem] uppercase tracking-[0.16em] text-dim">
        elke {dayLabel}
      </p>

      <div className="space-y-4 pb-2">
        <div className="flex gap-2">
          {PRESETS.map((p) => (
            <button
              key={p.label}
              onClick={() => setSlots(p.slots)}
              className="flex-1 rounded-full border border-line-strong px-3 py-1.5 text-[0.74rem] font-medium text-muted transition-colors hover:border-accent hover:text-ink"
            >
              {p.label}
            </button>
          ))}
        </div>

        {slots.length === 0 ? (
          <p className="rounded-xl bg-elevated px-4 py-3.5 text-sm text-muted">
            Geen vensters — standaard een rustdag.
          </p>
        ) : (
          <div className="space-y-2">
            {slots.map((slot, i) => (
              <div
                key={i}
                className="flex items-center gap-2.5 rounded-xl border border-line bg-elevated px-3.5 py-2.5"
              >
                <input
                  type="time"
                  value={slot.start}
                  onChange={(e) => update(i, { start: e.target.value })}
                />
                <span className="text-dim">–</span>
                <input
                  type="time"
                  value={slot.end}
                  onChange={(e) => update(i, { end: e.target.value })}
                />
                <button
                  aria-label="Venster verwijderen"
                  onClick={() => setSlots((cur) => cur.filter((_, j) => j !== i))}
                  className="ml-auto p-1 text-dim transition-colors hover:text-alert"
                >
                  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
                    <path d="M6 6l12 12M18 6 6 18" />
                  </svg>
                </button>
              </div>
            ))}
          </div>
        )}

        <button
          onClick={() =>
            setSlots((cur) => [
              ...cur,
              { start: "18:00", end: "19:30", context: "any" },
            ])
          }
          className="w-full rounded-xl border border-dashed border-line-strong py-2.5 text-[0.8rem] font-medium text-muted hover:border-accent hover:text-ink"
        >
          + venster toevoegen
        </button>

        {pattern.isError && (
          <p className="text-sm text-alert">
            Opslaan mislukt — check de tijden (einde na begin?).
          </p>
        )}

        <button
          data-testid="save-pattern"
          onClick={save}
          disabled={pattern.isPending}
          className="w-full rounded-xl bg-accent py-3 text-sm font-semibold text-white hover:bg-accent-hover disabled:opacity-50"
        >
          {pattern.isPending ? "Opslaan…" : "Patroon opslaan"}
        </button>
      </div>
    </BottomSheet>
  );
}
