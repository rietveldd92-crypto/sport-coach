import {
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { del, get, post, put } from "./client";
import type {
  AvailabilitySlot,
  CheckinHistoryView,
  FixedSessionsView,
  CheckinResult,
  Goal,
  GoalCreate,
  GoalCreateResult,
  MoveResult,
  OverrideResult,
  PatternView,
  PlanWeekResult,
  RegenerateResult,
  SeasonView,
  SwapCategory,
  SwapResult,
  ThresholdMutationResult,
  ThresholdPaceView,
  ThresholdSuggestion,
  TodayView,
  TrendsView,
  WeekView,
} from "./types";

export const keys = {
  today: ["today"] as const,
  week: (weekStart: string) => ["week", weekStart] as const,
  season: ["season"] as const,
  goals: ["goals"] as const,
  trends: ["trends"] as const,
  checkinHistory: ["checkin-history"] as const,
  pattern: ["pattern"] as const,
  fixedSessions: ["fixed-sessions"] as const,
  thresholdPace: ["threshold-pace"] as const,
};

export function useToday() {
  return useQuery({
    queryKey: keys.today,
    queryFn: () => get<TodayView>("/api/today"),
  });
}

export function useWeek(weekStart: string) {
  return useQuery({
    queryKey: keys.week(weekStart),
    queryFn: () => get<WeekView>(`/api/week/${weekStart}`),
    placeholderData: (prev) => prev,
  });
}

export function useSeason() {
  return useQuery({
    queryKey: keys.season,
    queryFn: () => get<SeasonView>("/api/season"),
    staleTime: 10 * 60_000,
    retry: 0,
  });
}

export function useCheckin() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: {
      sleep_score: number;
      energy: number;
      soreness: number;
      motivation: number;
      injury_signals: string[];
      notes?: string;
    }) => post<CheckinResult>("/api/checkin", body),
    onSuccess: (result) => {
      // Status-badge + checkin-kaart direct bijwerken, daarna verversen.
      qc.setQueryData<TodayView>(keys.today, (old) =>
        old
          ? {
              ...old,
              checkin: {
                ...old.checkin,
                done: true,
                score: result.checkin_score,
                recovery: result.recovery,
              },
              injury_guard: result.injury_guard,
            }
          : old,
      );
      qc.invalidateQueries({ queryKey: keys.today });
    },
  });
}

export function useSwap(eventId: string | number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (category: SwapCategory) =>
      post<SwapResult>(`/api/placements/${eventId}/swap`, { category }),
    onSuccess: (result) => {
      if (!result.ok || !result.chosen) return;
      const chosen = result.chosen;
      // Optimistic: hero meteen de nieuwe workout laten tonen.
      qc.setQueryData<TodayView>(keys.today, (old) => {
        if (!old?.workout || String(old.workout.event.id) !== String(eventId))
          return old;
        return {
          ...old,
          workout: {
            ...old.workout,
            event: {
              ...old.workout.event,
              name: chosen.naam ?? old.workout.event.name,
              description:
                chosen.beschrijving ?? old.workout.event.description,
              type: chosen.sport ?? old.workout.event.type,
              load_target:
                chosen.tss_geschat ?? old.workout.event.load_target,
            },
          },
        };
      });
      qc.invalidateQueries({ queryKey: keys.today });
      qc.invalidateQueries({ queryKey: ["week"] });
    },
  });
}

export function useSyncTp() {
  return useMutation({
    mutationFn: (eventId: string | number) =>
      post<Record<string, unknown>>(`/api/sync/tp/${eventId}`),
  });
}

export function useMovePlacement() {
  return useMutation({
    mutationFn: ({
      eventId,
      targetDate,
      apply,
    }: {
      eventId: string;
      targetDate: string;
      apply: boolean;
    }) =>
      post<MoveResult>(
        `/api/placements/${eventId}/move${apply ? "?apply=true" : ""}`,
        { target_date: targetDate },
      ),
  });
}

export function usePlanWeek(weekStart: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () =>
      post<PlanWeekResult>(`/api/week/${weekStart}/plan`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: keys.week(weekStart) });
      qc.invalidateQueries({ queryKey: keys.today });
    },
  });
}

export function usePutOverride() {
  return useMutation({
    mutationFn: ({
      date,
      slots,
    }: {
      date: string;
      slots: AvailabilitySlot[] | null;
    }) => put<OverrideResult>(`/api/availability/override/${date}`, { slots }),
  });
}

// ── Fase 5: Season + Jij ──────────────────────────────────────────────────

export function useGoals() {
  return useQuery({
    queryKey: keys.goals,
    queryFn: () => get<{ goals: Goal[] }>("/api/goals"),
    staleTime: 10 * 60_000,
  });
}

export function useCreateGoal() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: GoalCreate) =>
      post<GoalCreateResult>("/api/goals", body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: keys.season });
      qc.invalidateQueries({ queryKey: keys.goals });
    },
  });
}

export function useDeleteGoal() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (goalId: number) => del<void>(`/api/goals/${goalId}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: keys.season });
      qc.invalidateQueries({ queryKey: keys.goals });
    },
  });
}

export function useReplaceGoal() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({
      goalId,
      body,
    }: {
      goalId: number;
      body: GoalCreate;
    }) => {
      await del<void>(`/api/goals/${goalId}`);
      return post<GoalCreateResult>("/api/goals", body);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: keys.season });
      qc.invalidateQueries({ queryKey: keys.goals });
    },
  });
}

export function useRegenerateGoal() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      goalId,
      force = false,
    }: {
      goalId: number;
      force?: boolean;
    }) =>
      post<RegenerateResult>(
        `/api/goals/${goalId}/regenerate${force ? "?force=true" : ""}`,
      ),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: keys.season });
    },
  });
}

export function useTrends() {
  return useQuery({
    queryKey: keys.trends,
    queryFn: () => get<TrendsView>("/api/trends"),
    staleTime: 10 * 60_000,
  });
}

export function useCheckinHistory(days = 14) {
  return useQuery({
    queryKey: [...keys.checkinHistory, days],
    queryFn: () =>
      get<CheckinHistoryView>(`/api/checkin/history?days=${days}`),
    staleTime: 5 * 60_000,
  });
}

export function usePattern() {
  return useQuery({
    queryKey: keys.pattern,
    queryFn: () => get<PatternView>("/api/availability/pattern"),
    staleTime: 10 * 60_000,
  });
}

export function usePutPattern() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (days: Record<number, AvailabilitySlot[] | null>) =>
      put<PatternView>("/api/availability/pattern", { days }),
    onSuccess: (result) => {
      qc.setQueryData<PatternView>(keys.pattern, result);
      qc.invalidateQueries({ queryKey: ["week"] });
    },
  });
}

export function useFixedSessions() {
  return useQuery({
    queryKey: keys.fixedSessions,
    queryFn: () => get<FixedSessionsView>("/api/fixed-sessions"),
    staleTime: 10 * 60_000,
  });
}

export function usePutFixedSession() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      weekday,
      body,
    }: {
      weekday: number;
      body: {
        name: string;
        sport: string;
        duration_min: number;
        if_estimate: number;
        enabled: boolean;
      };
    }) => put<FixedSessionsView>(`/api/fixed-sessions/${weekday}`, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: keys.fixedSessions });
      qc.invalidateQueries({ queryKey: ["week"] });
    },
  });
}

export function useDeleteFixedSession() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (weekday: number) => del<void>(`/api/fixed-sessions/${weekday}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: keys.fixedSessions });
      qc.invalidateQueries({ queryKey: ["week"] });
    },
  });
}

export function useThresholdPace() {
  return useQuery({
    queryKey: keys.thresholdPace,
    queryFn: () => get<ThresholdPaceView>("/api/athlete/threshold-pace"),
    staleTime: 5 * 60_000,
  });
}

export function usePutThresholdPace() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { sec_per_km: number; reason: string }) =>
      put<ThresholdMutationResult>("/api/athlete/threshold-pace", body),
    onSuccess: () => invalidateThreshold(qc),
  });
}

export function useResolveThresholdSuggestion() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      id,
      accepted,
    }: {
      id: number;
      accepted: boolean;
    }) =>
      post<ThresholdMutationResult>(
        `/api/athlete/threshold-pace/suggestion/${id}`,
        { accepted },
      ),
    onSuccess: () => invalidateThreshold(qc),
  });
}

export function usePostRaceResult() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { distance_m: number; time_sec: number }) =>
      post<{ suggestion: ThresholdSuggestion | null }>(
        "/api/athlete/race-result",
        body,
      ),
    onSuccess: () => invalidateThreshold(qc),
  });
}

export function usePostWorkoutRpe() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      activityId,
      rpe,
      date,
    }: {
      activityId: string | number;
      rpe: number;
      date?: string;
    }) => post<{ rpe: { rpe: number } }>(`/api/workout/${activityId}/rpe`, { rpe, date }),
    // Een RPE vult de bijbehorende observatie aan en kan daarmee net de
    // drempeltrend laten omslaan — dossier en voorstel dus opnieuw ophalen.
    onSuccess: () => invalidateThreshold(qc),
  });
}

function invalidateThreshold(qc: ReturnType<typeof useQueryClient>) {
  qc.invalidateQueries({ queryKey: keys.thresholdPace });
  qc.invalidateQueries({ queryKey: keys.trends });
  qc.invalidateQueries({ queryKey: ["week"] });
  qc.invalidateQueries({ queryKey: keys.today });
}
