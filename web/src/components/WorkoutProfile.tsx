import type { WorkoutProfileStep } from "../api/types";
import { ZONE_VAR } from "../lib/workout";

export default function WorkoutProfile({
  profile,
  height = 28,
}: {
  profile: WorkoutProfileStep[];
  height?: number;
}) {
  if (!profile || profile.length < 2) return null;
  const total = profile.reduce((sum, step) => sum + Math.max(1, step.sec), 0);
  if (total <= 0) return null;
  let x = 0;
  const scaleMax = 125;

  return (
    <svg
      viewBox={`0 0 ${total} ${height}`}
      role="img"
      aria-label="Workoutprofiel"
      className="block w-full overflow-visible"
      style={{ height }}
      preserveAspectRatio="none"
    >
      {profile.map((step, i) => {
        const width = Math.max(1, step.sec);
        const pct = Math.max(0, Math.min(scaleMax, step.pct));
        const barHeight = Math.max(height * 0.15, (pct / scaleMax) * height);
        const y = height - barHeight;
        const rect = (
          <rect
            key={`${i}-${x}`}
            x={x}
            y={y}
            width={width}
            height={barHeight}
            rx={Math.min(2, width / 2)}
            fill={colorForPct(step.pct)}
            opacity={step.pct < 63 ? 0.55 : 0.88}
          />
        );
        x += width;
        return rect;
      })}
    </svg>
  );
}

function colorForPct(pct: number): string {
  if (pct > 105) return ZONE_VAR.race;
  if (pct >= 95) return ZONE_VAR.drempel;
  if (pct >= 78) return ZONE_VAR.tempo;
  return ZONE_VAR.z2;
}
