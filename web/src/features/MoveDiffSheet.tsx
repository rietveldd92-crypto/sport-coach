import BottomSheet from "../components/BottomSheet";
import type { MoveResult } from "../api/types";
import { dayShort } from "../lib/dates";

export interface PendingMove {
  eventId: string;
  eventName: string;
  targetDate: string;
  result: MoveResult;
}

interface Props {
  pending: PendingMove | null;
  busy: boolean;
  onConfirm: () => void;
  onClose: () => void;
}

/** Diff-preview na een drag: wat schuift er, en waarom (solver-redenen). */
export default function MoveDiffSheet({ pending, busy, onConfirm, onClose }: Props) {
  if (!pending) return null;
  const { result } = pending;
  const infeasible = result.status === "INFEASIBLE";
  const movedNotes = result.placements.filter(
    (p) => (p.moved_days ?? 0) !== 0 && p.notes,
  );

  return (
    <BottomSheet open onClose={onClose} title="Verplaatsing">
      <div className="space-y-4 pb-2">
        {infeasible ? (
          <div className="rounded-xl border border-alert/40 bg-alert/10 px-4 py-3 text-sm text-alert">
            Past niet: de week krijgt dit niet ingepland binnen de
            beschikbaarheid.
            {result.dropped.length > 0 && (
              <span>
                {" "}
                Knelpunt: {result.dropped.map((d) => d.naam).join(", ")}.
              </span>
            )}
          </div>
        ) : result.diff.length === 0 ? (
          <p className="text-sm text-muted">
            Geen verschuiving nodig — alles staat al goed.
          </p>
        ) : (
          <ul className="space-y-2">
            {result.diff.map((d) => (
              <li
                key={d.event_id}
                className="flex items-center justify-between gap-3 rounded-xl border border-line bg-elevated px-4 py-3"
              >
                <span className="min-w-0 truncate text-sm font-medium">
                  {d.event_name}
                </span>
                <span className="shrink-0 font-mono text-[0.78rem] text-muted">
                  {dayShort(d.from)} → {dayShort(d.to)}{" "}
                  <span className="text-accent">{d.to_time}</span>
                </span>
              </li>
            ))}
          </ul>
        )}

        {movedNotes.length > 0 && (
          <div className="rounded-xl bg-elevated px-4 py-3">
            <p className="mb-1.5 font-mono text-[0.6rem] uppercase tracking-[0.18em] text-dim">
              solver
            </p>
            {movedNotes.map((p) => (
              <p key={p.event_id} className="text-[0.78rem] leading-relaxed text-muted">
                {p.naam}: {p.notes}
              </p>
            ))}
          </div>
        )}

        <div className="flex gap-2.5 pt-1">
          <button
            onClick={onClose}
            className="flex-1 rounded-xl border border-line-strong py-3 text-sm font-semibold text-muted hover:text-ink"
          >
            Annuleren
          </button>
          {!infeasible && (
            <button
              onClick={onConfirm}
              disabled={busy}
              data-testid="confirm-move"
              className="flex-1 rounded-xl bg-accent py-3 text-sm font-semibold text-white hover:bg-accent-hover disabled:opacity-50"
            >
              {busy ? "Verplaatsen…" : "Bevestigen"}
            </button>
          )}
        </div>
      </div>
    </BottomSheet>
  );
}
