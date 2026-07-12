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

export function SportIcon({ kind }: { kind: SportKind }) {
  const common = {
    width: 14,
    height: 14,
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 2,
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
    "aria-hidden": true,
  };
  if (kind === "run") {
    return (
      <svg {...common}>
        <circle cx="13" cy="4" r="2" />
        <path d="M8 20l3-6" />
        <path d="M13 7l-2 5 4 3 3 5" />
        <path d="M10 10l-4 2" />
        <path d="M14 8l4 2" />
      </svg>
    );
  }
  if (kind === "ride") {
    return (
      <svg {...common}>
        <circle cx="6" cy="17" r="3" />
        <circle cx="18" cy="17" r="3" />
        <path d="M8 17l4-8 3 8" />
        <path d="M12 9h4l2-3" />
        <path d="M10 6h3" />
      </svg>
    );
  }
  if (kind === "strength") {
    return (
      <svg {...common}>
        <path d="M4 9v6" />
        <path d="M8 7v10" />
        <path d="M16 7v10" />
        <path d="M20 9v6" />
        <path d="M8 12h8" />
      </svg>
    );
  }
  return (
    <svg {...common}>
      <circle cx="12" cy="12" r="7" />
      <path d="M12 8v4l3 2" />
    </svg>
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
