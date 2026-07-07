import { useState } from "react";
import BottomSheet from "../components/BottomSheet";
import HoursPicker from "../components/HoursPicker";
import { usePlanWeek, usePutOverride } from "../api/queries";
import type { AvailabilitySlot } from "../api/types";
import { longDate, toHHMM, toMinutes } from "../lib/dates";

interface Props {
  date: string;
  initial: AvailabilitySlot[];
  weekStart: string;
  onClose: () => void;
}

function totalMinutes(slots: AvailabilitySlot[]): number {
  return slots.reduce((sum, s) => sum + (toMinutes(s.end) - toMinutes(s.start)), 0);
}

/** Uren beschikbaarheid van één dag bewerken → override → week herplannen. */
export default function AvailabilitySheet({ date, initial, weekStart, onClose }: Props) {
  const [minutes, setMinutes] = useState(() => totalMinutes(initial));
  const [planned, setPlanned] = useState<number | null>(null);
  const override = usePutOverride();
  const plan = usePlanWeek(weekStart);

  const save = () => {
    const slots: AvailabilitySlot[] =
      minutes <= 0 ? [] : [{ start: "07:00", end: toHHMM(7 * 60 + minutes), context: "any" }];
    override.mutate(
      { date, slots },
      {
        onSuccess: () =>
          plan.mutate(undefined, {
            onSuccess: (res) => setPlanned(res.planned_sessions),
          }),
      },
    );
  };

  const busy = override.isPending || plan.isPending;

  return (
    <BottomSheet open onClose={onClose} title="Beschikbaarheid">
      <p className="-mt-2 mb-4 font-mono text-[0.68rem] uppercase tracking-[0.16em] text-dim">
        {longDate(date)}
      </p>

      {planned !== null ? (
        <div className="space-y-4 pb-2">
          <div className="rounded-xl border border-positive/40 bg-positive/10 px-4 py-3 text-sm text-positive">
            Week opnieuw gepland — {planned} sessie
            {planned === 1 ? "" : "s"} in de agenda gezet.
          </div>
          <button
            onClick={onClose}
            className="w-full rounded-xl bg-accent py-3 text-sm font-semibold text-white hover:bg-accent-hover"
          >
            Klaar
          </button>
        </div>
      ) : (
        <div className="space-y-4 pb-2">
          <HoursPicker minutes={minutes} onChange={setMinutes} />

          {minutes <= 0 && (
            <p className="rounded-xl bg-elevated px-4 py-3.5 text-sm text-muted">
              0 uur — dit wordt een rustdag.
            </p>
          )}

          {(override.isError || plan.isError) && (
            <p className="text-sm text-alert">
              {override.isError
                ? "Opslaan mislukt — probeer het opnieuw."
                : "Herplannen mislukt — beschikbaarheid is wel opgeslagen."}
            </p>
          )}

          <button
            onClick={save}
            disabled={busy}
            className="w-full rounded-xl bg-accent py-3 text-sm font-semibold text-white hover:bg-accent-hover disabled:opacity-50"
          >
            {override.isPending
              ? "Opslaan…"
              : plan.isPending
                ? "Week herplannen…"
                : "Opslaan & herplannen"}
          </button>
        </div>
      )}
    </BottomSheet>
  );
}
