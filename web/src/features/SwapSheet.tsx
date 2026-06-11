import { useState } from "react";
import BottomSheet from "../components/BottomSheet";
import { useSwap } from "../api/queries";
import type { SwapCategory, SwapResult } from "../api/types";

const OPTIONS: { id: SwapCategory; title: string; sub: string }[] = [
  {
    id: "makkelijker",
    title: "Makkelijker",
    sub: "Minder belasting, zelfde week-doel",
  },
  {
    id: "vergelijkbaar",
    title: "Vergelijkbaar",
    sub: "Zelfde belasting, andere prikkel",
  },
  { id: "harder", title: "Harder", sub: "Meer TSS — alleen als je fris bent" },
];

interface Props {
  open: boolean;
  onClose: () => void;
  eventId: string | number;
}

export default function SwapSheet({ open, onClose, eventId }: Props) {
  const swap = useSwap(eventId);
  const [result, setResult] = useState<SwapResult | null>(null);

  const close = () => {
    setResult(null);
    swap.reset();
    onClose();
  };

  return (
    <BottomSheet open={open} onClose={close} title="Swap workout">
      {result ? (
        <div className="space-y-4 pb-2">
          <p className={`text-sm leading-relaxed ${result.ok ? "" : "text-alert"}`}>
            {result.message}
          </p>
          {result.phase_warning && (
            <p className="rounded-xl border border-warning/40 bg-warning/10 px-3.5 py-2.5 text-[0.8rem] text-warning">
              {result.phase_warning}
            </p>
          )}
          <button
            onClick={close}
            className="w-full rounded-xl bg-accent py-3 text-sm font-semibold text-white hover:bg-accent-hover"
          >
            Klaar
          </button>
        </div>
      ) : (
        <div className="space-y-2.5 pb-2">
          {OPTIONS.map((opt) => (
            <button
              key={opt.id}
              disabled={swap.isPending}
              onClick={() => swap.mutate(opt.id, { onSuccess: setResult })}
              className="flex w-full items-center justify-between rounded-xl border border-line bg-elevated px-4 py-3.5 text-left transition-colors hover:border-accent/60 disabled:opacity-50"
            >
              <span>
                <span className="block text-sm font-semibold">{opt.title}</span>
                <span className="mt-0.5 block text-[0.78rem] text-muted">
                  {opt.sub}
                </span>
              </span>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" className="text-dim">
                <path d="M9 6l6 6-6 6" />
              </svg>
            </button>
          ))}
          {swap.isPending && (
            <p className="pt-1 text-center text-sm text-muted">
              Beste alternatief zoeken…
            </p>
          )}
          {swap.isError && (
            <p className="pt-1 text-sm text-alert">
              Swap mislukt — probeer het nog eens.
            </p>
          )}
        </div>
      )}
    </BottomSheet>
  );
}
