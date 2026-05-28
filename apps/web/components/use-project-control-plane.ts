"use client";

import { useEffect, useRef, useState } from "react";
import { fetchPlannerHome } from "@/lib/api";
import type { PlannerControlPlaneSnapshot, PlannerHome } from "@/lib/types";

const FAST_INTERVAL_MS = 3500;
const IDLE_INTERVAL_MS = 10000;

function nextPollMs(snapshot: PlannerControlPlaneSnapshot | null) {
  if (!snapshot) return FAST_INTERVAL_MS;
  const hasUrgentItems =
    snapshot.autopilot.enabled ||
    snapshot.pendingDispatches.length > 0 ||
    snapshot.pendingQuestions.length > 0 ||
    snapshot.board.approvals.some((approval) => approval.status === "pending") ||
    snapshot.board.tasks.some((task) => ["running", "awaiting_approval", "review"].includes(task.status ?? ""));
  return hasUrgentItems ? FAST_INTERVAL_MS : IDLE_INTERVAL_MS;
}

function fromPlannerHome(home: PlannerHome): PlannerControlPlaneSnapshot {
  const missionBrief = home.controlPlane?.missionBrief
    ? {
        current: home.controlPlane.missionBrief.current ?? "",
        next: home.controlPlane.missionBrief.next ?? "",
        sourceSessionId: home.controlPlane.missionBrief.sourceSessionId ?? undefined,
        sourceRole: home.controlPlane.missionBrief.sourceRole ?? undefined,
        sourceStatus: home.controlPlane.missionBrief.sourceStatus ?? undefined,
        sourceUpdatedAt: home.controlPlane.missionBrief.sourceUpdatedAt ?? undefined,
      }
    : null;

  return {
    board: {
      board: home.planner.board ?? {},
      tasks: home.planner.tasks ?? [],
      approvals: home.planner.approvals ?? [],
      blockersPath: home.planner.files?.blockers ?? "research_plan/blockers.md",
      sessions: home.planner.sessions ?? [],
    },
    autopilot: home.autopilot ?? { enabled: false, autoApprove: false },
    goal: home.controlPlane?.goal ?? null,
    phase: home.controlPlane?.phase,
    nextAction: home.controlPlane?.nextAction,
    currentBlocker: home.controlPlane?.currentBlocker,
    projectReality: home.controlPlane?.projectReality ?? undefined,
    auditors: home.controlPlane?.auditors ?? undefined,
    closeoutCertificate: home.controlPlane?.closeoutCertificate ?? undefined,
    missionBrief: missionBrief ?? undefined,
    pendingDispatches: home.pendingDispatches ?? [],
    pendingQuestions: home.pendingQuestions ?? [],
    decisions: home.decisions ?? [],
    snapshot: home.controlPlane?.snapshot ?? undefined,
    refreshedAt: home.refreshedAt ?? Date.now(),
  };
}

export function useProjectControlPlane(slug: string, initialHome?: PlannerHome | null) {
  const initialSnapshot = initialHome ? fromPlannerHome(initialHome) : null;
  const [snapshot, setSnapshot] = useState<PlannerControlPlaneSnapshot | null>(initialSnapshot);
  const [loading, setLoading] = useState(!initialSnapshot);
  const [error, setError] = useState<string | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const snapshotRef = useRef<PlannerControlPlaneSnapshot | null>(initialSnapshot);
  const refreshRef = useRef<(() => Promise<void>) | null>(null);

  useEffect(() => {
    let active = true;

    async function load() {
      try {
        const next = fromPlannerHome(await fetchPlannerHome(slug));
        if (!active) return;
        snapshotRef.current = next;
        setSnapshot(next);
        setError(null);
      } catch (err) {
        if (!active) return;
        setError(err instanceof Error ? err.message : "Failed to load planner state");
      } finally {
        if (active) {
          setLoading(false);
          timerRef.current = setTimeout(load, nextPollMs(snapshotRef.current));
        }
      }
    }

    refreshRef.current = load;

    load();
    return () => {
      active = false;
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, [slug]);

  return {
    snapshot,
    loading,
    error,
    refresh: async () => {
      if (timerRef.current) clearTimeout(timerRef.current);
      await refreshRef.current?.();
    },
  };
}
