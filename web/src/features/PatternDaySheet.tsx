import { useState } from "react";
import BottomSheet from "../components/BottomSheet";
import HoursPicker from "../components/HoursPicker";
import { usePutPattern } from "../api/queries";
import type { AvailabilitySlot } from "../api/types";
import { toHHMM, toMinutes } from "../lib/dates";

interface Props {
  weekday: number; // 0=ma .. 6=zo
  dayLabel: string;
  initial: AvailabilitySlot[];
  onClose: () => void;
}

function totalMinutes(slots: AvailabilitySlot[]): number {
  return slots.reduce((sum, s) => sum + (toMinutes(s.end) - toMinutes(s.start)), 0);
}

/** Uren van één weekdag in het terugkerende patroon bewerken
 *  (zelfde urenkiezer als AvailabilitySheet, maar → PUT /availability/pattern). */
export default function PatternDaySheet({ weekday, dayLabel, initial, onClose }: Props) {
  const [minutes, setMinutes] = useState(() => totalMinutes(initial));
  const pattern = usePutPattern();

  const save = () => {
    const slots: AvailabilitySlot[] =
      minutes <= 0 ? [] : [{ start: "07:00", end: toHHMM(7 * 60 + minutes), context: "any" }];
    pattern.mutate({ [weekday]: slots }, { onSuccess: onClose });
  };

  return (
    <BottomSheet open onClose={onClose} title="Weekpatroon">
      <p className="-mt-2 mb-4 font-mono text-[0.68rem] uppercase tracking-[0.16em] text-dim">
        elke {dayLabel}
      </p>

      <div className="space-y-4 pb-2">
        <HoursPicker minutes={minutes} onChange={setMinutes} />

        {minutes <= 0 && (
          <p className="rounded-xl bg-elevated px-4 py-3.5 text-sm text-muted">
            0 uur — standaard een rustdag.
          </p>
        )}

        {pattern.isError && (
          <p className="text-sm text-alert">Opslaan mislukt — probeer het opnieuw.</p>
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
