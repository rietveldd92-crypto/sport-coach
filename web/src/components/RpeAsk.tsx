import { useState } from "react";
import { usePostWorkoutRpe } from "../api/queries";
import type { EventSummary } from "../api/types";

/** Vraagt de RPE uit na een voltooide drempelsessie.
 *
 *  De RPE is geen sfeervraag: de sneller-trend eist RPE <= 7, dus zonder deze
 *  waarde kan het drempelvoorstel nooit vallen. Daarom vraagt zowel Today als
 *  de Week-lijst ernaar — je mist de vraag anders zodra de dag voorbij is.
 */
export function asksRpe(item: EventSummary): boolean {
  const event = item.event;
  return Boolean(
    item.done &&
      item.activity &&
      event.type === "Run" &&
      /drempel|threshold/i.test(event.name ?? ""),
  );
}

export default function RpeAsk({
  item,
  compact = false,
}: {
  item: EventSummary;
  compact?: boolean;
}) {
  const mutation = usePostWorkoutRpe();
  const [value, setValue] = useState<number | null>(null);

  const pick = (rpe: number) => {
    setValue(rpe);
    mutation.mutate({
      activityId: item.activity!.id,
      rpe,
      date: (item.activity!.start_date_local ?? "").slice(0, 10),
    });
  };

  return (
    <div
      className={`rounded-xl border border-line bg-elevated px-3.5 py-3 ${
        compact ? "mt-2" : "mt-5"
      }`}
    >
      <p className="font-mono text-[0.62rem] uppercase tracking-[0.16em] text-dim">
        Hoe zwaar voelde dit?
      </p>
      <div className="mt-2 grid grid-cols-10 gap-1">
        {Array.from({ length: 10 }, (_, i) => i + 1).map((rpe) => (
          <button
            key={rpe}
            onClick={() => pick(rpe)}
            disabled={mutation.isPending}
            className={`rounded-md border text-[0.72rem] font-semibold ${
              compact ? "h-7" : "h-8"
            } ${
              value === rpe
                ? "border-accent bg-accent text-white"
                : "border-line-strong text-muted"
            } disabled:opacity-60`}
          >
            {rpe}
          </button>
        ))}
      </div>
    </div>
  );
}
