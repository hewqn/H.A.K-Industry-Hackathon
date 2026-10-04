import { api } from "./client";
import type { Models } from "./client";

export interface CaseReport {
  kept: number;
  dropped: number;
  oldestDeaths: number;
  weight2Deaths: number;
  weight3Deaths: number;
  overlap: number;
  keepWeight2: boolean;
}

interface CohortCounts {
  accepted_count?: number;
  missing_rows?: number;
}

export async function loadCaseReport(): Promise<CaseReport | null> {
  try {
    const [models, cohort] = await Promise.all([
      api<Models>("/models"),
      api<CohortCounts>("/cohorts/current"),
    ]);
    const metrics = models.reports.benchmark.metrics;
    return {
      // Evaluation remains tied to the original labelled cohort after live CRUD.
      kept: metrics.oldest_first.n,
      dropped: cohort.missing_rows ?? 0,
      oldestDeaths: metrics.oldest_first.captured_outcomes,
      weight2Deaths: metrics.points_v1.captured_outcomes,
      weight3Deaths: metrics.points_heart3.captured_outcomes,
      overlap: models.reports.benchmark.overlap_count,
      keepWeight2: models.reports.benchmark.decision === "reject_candidate",
    };
  } catch {
    return null;
  }
}
