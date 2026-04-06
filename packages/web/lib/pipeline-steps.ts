/**
 * Step count from pipeline YAML stored as parsedSpec (Convex pipelineConfigs).
 */
export function countPipelineStepsFromSpec(parsedSpec: unknown): number | undefined {
  if (parsedSpec == null || typeof parsedSpec !== "object") return undefined;
  const steps = (parsedSpec as { steps?: unknown }).steps;
  if (!Array.isArray(steps)) return undefined;
  return steps.length;
}

/**
 * Done / total for hydration UI. Prefer pipeline step count; Convex `stepResults` may only
 * list steps that have started or finished, so its length is not always the true total.
 */
export function hydrationStepProgress(
  stepResults: { status: string }[],
  pipelineStepTotal: number | undefined,
): { done: number; total: number } {
  const done = stepResults.filter((s) => s.status === "done").length;
  const recorded = stepResults.length;
  if (pipelineStepTotal !== undefined && pipelineStepTotal > 0) {
    return { done, total: Math.max(pipelineStepTotal, recorded, done) };
  }
  return { done, total: Math.max(recorded, done) };
}
