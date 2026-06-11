import { useState } from "react";
import BottomSheet from "../components/BottomSheet";
import { useCheckin } from "../api/queries";
import type { CheckinResult } from "../api/types";

const SLIDERS = [
  { key: "sleep_score", label: "Slaap", low: "slecht", high: "diep" },
  { key: "energy", label: "Energie", low: "leeg", high: "vol" },
  { key: "soreness", label: "Spieren", low: "zwaar", high: "fris" },
  { key: "motivation", label: "Motivatie", low: "meh", high: "zin" },
] as const;

type SliderKey = (typeof SLIDERS)[number]["key"];

const SIGNALS = [
  { id: "knie_pijn", label: "Knie pijn" },
  { id: "rug_pijn", label: "Rug pijn" },
  { id: "heup_pijn", label: "Heup pijn" },
  { id: "knie_twinge", label: "Knie twinge" },
  { id: "soreness_hoog", label: "Soreness hoog" },
];

const GUARD_TONE: Record<string, string> = {
  groen: "border-positive/40 bg-positive/10 text-positive",
  geel: "border-warning/40 bg-warning/10 text-warning",
  rood: "border-alert/40 bg-alert/10 text-alert",
};

interface Props {
  open: boolean;
  onClose: () => void;
}

export default function CheckinSheet({ open, onClose }: Props) {
  const checkin = useCheckin();
  const [values, setValues] = useState<Record<SliderKey, number>>({
    sleep_score: 3,
    energy: 3,
    soreness: 3,
    motivation: 3,
  });
  const [signals, setSignals] = useState<string[]>([]);
  const [result, setResult] = useState<CheckinResult | null>(null);

  const toggleSignal = (id: string) =>
    setSignals((cur) =>
      cur.includes(id) ? cur.filter((s) => s !== id) : [...cur, id],
    );

  const submit = () => {
    checkin.mutate(
      { ...values, injury_signals: signals },
      { onSuccess: setResult },
    );
  };

  const close = () => {
    setResult(null);
    checkin.reset();
    onClose();
  };

  return (
    <BottomSheet open={open} onClose={close} title="Ochtend-checkin">
      {result ? (
        <div data-testid="checkin-result" className="space-y-4 pb-2">
          <div
            className={`rounded-xl border px-4 py-3 text-sm ${GUARD_TONE[result.injury_guard.status] ?? GUARD_TONE.groen}`}
          >
            <p className="font-mono text-[0.65rem] uppercase tracking-[0.16em]">
              Injury guard · {result.injury_guard.status}
            </p>
            <p className="mt-1.5 leading-snug">{result.injury_guard.message}</p>
          </div>
          <p className="text-sm leading-relaxed text-muted">
            {result.recovery.message}
          </p>
          <button
            onClick={close}
            className="w-full rounded-xl bg-accent py-3 text-sm font-semibold text-white transition-colors hover:bg-accent-hover"
          >
            Klaar
          </button>
        </div>
      ) : (
        <div className="space-y-6 pb-2">
          {SLIDERS.map((s) => (
            <div key={s.key}>
              <div className="mb-2 flex items-baseline justify-between">
                <label className="text-sm font-medium">{s.label}</label>
                <span className="font-mono text-sm text-accent">
                  {values[s.key]}
                </span>
              </div>
              <input
                type="range"
                min={1}
                max={5}
                step={1}
                value={values[s.key]}
                aria-label={s.label}
                onChange={(e) =>
                  setValues((v) => ({ ...v, [s.key]: Number(e.target.value) }))
                }
              />
              <div className="mt-1 flex justify-between text-[0.62rem] uppercase tracking-wider text-dim">
                <span>{s.low}</span>
                <span>{s.high}</span>
              </div>
            </div>
          ))}

          <div>
            <p className="mb-2.5 text-sm font-medium">Signalen</p>
            <div className="flex flex-wrap gap-2">
              {SIGNALS.map((sig) => {
                const active = signals.includes(sig.id);
                return (
                  <button
                    key={sig.id}
                    onClick={() => toggleSignal(sig.id)}
                    className={`rounded-full border px-3.5 py-1.5 text-[0.78rem] transition-colors ${
                      active
                        ? "border-accent bg-accent/15 text-accent"
                        : "border-line-strong text-muted hover:border-accent/50"
                    }`}
                  >
                    {sig.label}
                  </button>
                );
              })}
            </div>
          </div>

          {checkin.isError && (
            <p className="text-sm text-alert">
              Versturen mislukt — probeer het nog eens.
            </p>
          )}

          <button
            onClick={submit}
            disabled={checkin.isPending}
            className="w-full rounded-xl bg-accent py-3 text-sm font-semibold text-white transition-colors hover:bg-accent-hover disabled:opacity-50"
          >
            {checkin.isPending ? "Versturen…" : "Check in"}
          </button>
        </div>
      )}
    </BottomSheet>
  );
}
