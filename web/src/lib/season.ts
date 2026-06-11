import type { GoalType } from "../api/types";

/** Fase → kleur. Accumulatie loopt van blauw naar groen, transformatie is
 *  amber, realisatie terracotta — zelfde families als de zone-kleuren. */
export function phaseColor(phase?: string): string {
  const p = (phase ?? "").toLowerCase();
  if (p.startsWith("realisatie")) return "var(--accent)";
  if (p.startsWith("transformatie")) return "var(--zone-tempo)";
  if (p.startsWith("accumulatie")) {
    if (p.endsWith("iii")) return "var(--zone-z2)"; // groen
    if (p.endsWith("ii")) return "#648a87"; // blauwgroen (tussenstap)
    return "var(--zone-z1)"; // grijsblauw
  }
  return "var(--border-strong)";
}

export function fmtPhase(phase?: string): string {
  return (phase ?? "").replace(/_/g, " ");
}

export const GOAL_LABEL: Record<string, string> = {
  marathon: "Marathon",
  half: "Halve marathon",
  "10k": "10K",
  "5k": "5K",
  gran_fondo: "Gran fondo",
  ftp: "FTP-blok",
  triathlon: "Triatlon",
  custom: "Eigen doel",
};

export interface GoalTypeMeta {
  value: GoalType;
  label: string;
  sport: "run" | "ride" | "multi";
  targetHint: string;
  targetLabel: string;
}

export const GOAL_TYPES: GoalTypeMeta[] = [
  { value: "marathon", label: "Marathon", sport: "run", targetHint: "2:59:00", targetLabel: "streeftijd" },
  { value: "half", label: "Halve marathon", sport: "run", targetHint: "1:25:00", targetLabel: "streeftijd" },
  { value: "10k", label: "10K", sport: "run", targetHint: "0:42:00", targetLabel: "streeftijd" },
  { value: "5k", label: "5K", sport: "run", targetHint: "0:20:00", targetLabel: "streeftijd" },
  { value: "gran_fondo", label: "Gran fondo", sport: "ride", targetHint: "5:30:00", targetLabel: "streeftijd" },
  { value: "ftp", label: "FTP-blok", sport: "ride", targetHint: "310W", targetLabel: "doelvermogen" },
];

/** Aantal hele weken tussen vandaag en een datum (afgerond naar beneden). */
export function weeksUntil(eventDateIso: string, todayIso: string): number {
  const ms =
    new Date(eventDateIso + "T00:00:00").getTime() -
    new Date(todayIso + "T00:00:00").getTime();
  return Math.max(0, Math.floor(ms / (7 * 24 * 3600 * 1000)));
}

/** Indicatieve blokverdeling voor de wizard-preview — zelfde ratio's als
 *  core/periodization_generator (UPGRADE_PLAN §4.1). De generator zelf is
 *  leidend; dit is alleen de visuele preview vóór het bevestigen. */
export function previewBlocks(
  weeks: number,
): { phase: string; weeks: number }[] {
  const ratios: [string, number][] =
    weeks >= 20
      ? [
          ["accumulatie_I", 0.25],
          ["accumulatie_II", 0.25],
          ["transformatie_I", 0.15],
          ["accumulatie_III", 0.14],
          ["transformatie_II", 0.11],
          ["realisatie", 0.1],
        ]
      : weeks >= 12
        ? [
            ["accumulatie_I", 0.4],
            ["transformatie_I", 0.25],
            ["accumulatie_II", 0.15],
            ["transformatie_II", 0.12],
            ["realisatie", 0.08],
          ]
        : [
            ["accumulatie_I", 0.45],
            ["transformatie_I", 0.35],
            ["realisatie", 0.2],
          ];

  const blocks = ratios.map(([phase, r]) => ({
    phase,
    weeks: Math.max(1, Math.round(weeks * r)),
  }));
  // Afronding corrigeren zodat de som klopt (verschil in het grootste blok).
  const diff = weeks - blocks.reduce((s, b) => s + b.weeks, 0);
  if (diff !== 0) {
    const biggest = blocks.reduce((a, b) => (b.weeks > a.weeks ? b : a));
    biggest.weeks = Math.max(1, biggest.weeks + diff);
  }
  return blocks;
}
