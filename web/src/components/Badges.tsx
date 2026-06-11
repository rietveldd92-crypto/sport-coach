import type { InjuryGuard } from "../api/types";
import type { SportKind, Zone } from "../lib/workout";
import { SPORT_LABEL, ZONE_LABEL, ZONE_VAR } from "../lib/workout";

const GUARD_STYLE: Record<InjuryGuard["status"], { label: string; cls: string }> = {
  groen: { label: "GREEN", cls: "text-positive border-positive/40 bg-positive/10" },
  geel: { label: "YELLOW", cls: "text-warning border-warning/40 bg-warning/10" },
  rood: { label: "RED", cls: "text-alert border-alert/40 bg-alert/10" },
};

export function InjuryBadge({ guard }: { guard: InjuryGuard | null }) {
  if (!guard) return null;
  const s = GUARD_STYLE[guard.status] ?? GUARD_STYLE.groen;
  return (
    <span
      title={guard.message}
      className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 font-mono text-[0.62rem] font-medium tracking-[0.12em] ${s.cls}`}
    >
      <span className="h-1.5 w-1.5 rounded-full bg-current" />
      {s.label}
    </span>
  );
}

export function SportBadge({ kind }: { kind: SportKind }) {
  return (
    <span className="inline-flex items-center rounded-full border border-line-strong bg-elevated px-2.5 py-0.5 text-[0.66rem] font-medium uppercase tracking-[0.14em] text-muted">
      {SPORT_LABEL[kind]}
    </span>
  );
}

export function ZoneChip({ zone }: { zone: Zone }) {
  return (
    <span className="inline-flex items-center gap-1.5 text-[0.7rem] font-medium text-muted">
      <span
        className="h-2 w-2 rounded-sm"
        style={{ background: ZONE_VAR[zone] }}
      />
      {ZONE_LABEL[zone]}
    </span>
  );
}
