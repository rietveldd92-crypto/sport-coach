const DAY_NAMES = ["maandag", "dinsdag", "woensdag", "donderdag", "vrijdag", "zaterdag", "zondag"];
const DAY_SHORT = ["ma", "di", "wo", "do", "vr", "za", "zo"];
const MONTHS = ["jan", "feb", "mrt", "apr", "mei", "jun", "jul", "aug", "sep", "okt", "nov", "dec"];

export function toISODate(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

export function parseISO(iso: string): Date {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(y, m - 1, d);
}

export function todayISO(): string {
  return toISODate(new Date());
}

/** Maandag van de week waarin `iso` valt. */
export function mondayOf(iso: string): string {
  const d = parseISO(iso);
  const wd = (d.getDay() + 6) % 7; // 0 = ma
  d.setDate(d.getDate() - wd);
  return toISODate(d);
}

export function addDays(iso: string, days: number): string {
  const d = parseISO(iso);
  d.setDate(d.getDate() + days);
  return toISODate(d);
}

export function weekdayIndex(iso: string): number {
  return (parseISO(iso).getDay() + 6) % 7;
}

export function dayName(iso: string): string {
  return DAY_NAMES[weekdayIndex(iso)];
}

export function dayShort(iso: string): string {
  return DAY_SHORT[weekdayIndex(iso)];
}

/** "wo 11 jun" */
export function shortDate(iso: string): string {
  const d = parseISO(iso);
  return `${DAY_SHORT[weekdayIndex(iso)]} ${d.getDate()} ${MONTHS[d.getMonth()]}`;
}

/** "11 jun" */
export function dayMonth(iso: string): string {
  const d = parseISO(iso);
  return `${d.getDate()} ${MONTHS[d.getMonth()]}`;
}

/** "woensdag 11 juni" — voluit voor de Today-header. */
export function longDate(iso: string): string {
  const d = parseISO(iso);
  const months = ["januari", "februari", "maart", "april", "mei", "juni", "juli", "augustus", "september", "oktober", "november", "december"];
  return `${dayName(iso)} ${d.getDate()} ${months[d.getMonth()]}`;
}

export function isoWeekNumber(iso: string): number {
  const d = parseISO(iso);
  const date = new Date(Date.UTC(d.getFullYear(), d.getMonth(), d.getDate()));
  const dayNum = date.getUTCDay() || 7;
  date.setUTCDate(date.getUTCDate() + 4 - dayNum);
  const yearStart = new Date(Date.UTC(date.getUTCFullYear(), 0, 1));
  return Math.ceil(((date.getTime() - yearStart.getTime()) / 86400000 + 1) / 7);
}

/** "HH:MM" uit een ISO-datetime, of null bij middernacht (= geen slot). */
export function timeOf(startDateLocal?: string): string | null {
  if (!startDateLocal || !startDateLocal.includes("T")) return null;
  const t = startDateLocal.slice(11, 16);
  return t === "00:00" ? null : t;
}

export function toMinutes(hhmm: string): number {
  const [h, m] = hhmm.split(":").map(Number);
  return h * 60 + m;
}
