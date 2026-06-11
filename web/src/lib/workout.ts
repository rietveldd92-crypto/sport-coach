import type { EventSummary, IcuEvent } from "../api/types";

/** Zone-indeling — zelfde palet overal:
 *  Z1 grijsblauw · Z2 groenig · tempo amber · drempel terracotta · race rood */
export type Zone = "z1" | "z2" | "tempo" | "drempel" | "race";

export const ZONE_LABEL: Record<Zone, string> = {
  z1: "Z1 herstel",
  z2: "Z2 duur",
  tempo: "Tempo",
  drempel: "Drempel",
  race: "Race",
};

export const ZONE_VAR: Record<Zone, string> = {
  z1: "var(--zone-z1)",
  z2: "var(--zone-z2)",
  tempo: "var(--zone-tempo)",
  drempel: "var(--zone-drempel)",
  race: "var(--zone-race)",
};

/** Hoogste intensiteit uit de beschrijving ("- 10m 95-100%") bepaalt de zone. */
export function zoneOf(event: IcuEvent): Zone {
  const desc = `${event.description ?? ""} ${event.name ?? ""}`.toLowerCase();
  if (/\brace|wedstrijd/.test(desc)) return "race";

  let maxPct = 0;
  for (const m of desc.matchAll(/(\d{2,3})(?:\s*-\s*(\d{2,3}))?\s*%/g)) {
    const hi = Number(m[2] ?? m[1]);
    if (hi > maxPct) maxPct = hi;
  }
  if (maxPct > 102) return "race";
  if (maxPct >= 88) return "drempel";
  if (maxPct >= 78) return "tempo";
  if (maxPct >= 60) return "z2";
  if (maxPct > 0) return "z1";

  // Geen percentages — val terug op naamheuristiek.
  if (/threshold|drempel|interval|vo2/.test(desc)) return "drempel";
  if (/tempo/.test(desc)) return "tempo";
  if (/recovery|herstel/.test(desc)) return "z1";
  return "z2";
}

/** Duur in minuten: moving_time → workout_doc → "NN min" in naam. */
export function durationMin(event: IcuEvent): number | null {
  if (event.moving_time) return Math.round(event.moving_time / 60);
  if (event.workout_doc?.duration)
    return Math.round(event.workout_doc.duration / 60);
  const m = (event.name ?? "").match(/(\d{2,3})\s*min/i);
  if (m) return Number(m[1]);
  return null;
}

export function fmtDuration(min: number | null): string {
  if (min == null) return "—";
  if (min < 60) return `${min}m`;
  const h = Math.floor(min / 60);
  const rest = min % 60;
  return rest ? `${h}u${String(rest).padStart(2, "0")}` : `${h}u`;
}

export type SportKind = "run" | "ride" | "strength" | "other";

export function sportKind(event: IcuEvent): SportKind {
  const t = (event.type ?? "").toLowerCase();
  if (t.includes("run")) return "run";
  if (t.includes("ride")) return "ride";
  if (t.includes("weight") || t.includes("strength") || t.includes("workout"))
    return "strength";
  return "other";
}

export const SPORT_LABEL: Record<SportKind, string> = {
  run: "Run",
  ride: "Fiets",
  strength: "Kracht",
  other: "Sessie",
};

/** Syncbaar naar Zwift (via TP): fietssessie met structuur, nog niet gedaan. */
export function isSyncable(item: EventSummary): boolean {
  const kind = sportKind(item.event);
  return (
    (kind === "ride" || (item.event.type ?? "").includes("Virtual")) &&
    !item.done &&
    Boolean(item.event.description)
  );
}

export interface DescLine {
  kind: "repeat" | "step" | "text";
  text: string;
}

/** "3x\n- 10m 95-100%\n- 5m 55%" → nette regels voor mono-weergave. */
export function parseDescription(description?: string | null): DescLine[] {
  if (!description) return [];
  return description
    .split("\n")
    .map((raw) => raw.trim())
    .filter(Boolean)
    .map((line): DescLine => {
      if (/^\d+\s*x$/i.test(line)) return { kind: "repeat", text: line };
      if (line.startsWith("-"))
        return { kind: "step", text: line.replace(/^-\s*/, "") };
      return { kind: "text", text: line };
    });
}

export type SessionStatus = "done" | "missed" | "planned";

export function sessionStatus(item: EventSummary, todayIso: string): SessionStatus {
  if (item.done) return "done";
  const d = (item.event.start_date_local ?? "").slice(0, 10);
  if (d && d < todayIso) return "missed";
  return "planned";
}
