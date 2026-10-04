import { api } from "./client";
import { loadRanking } from "./loadRanking";
import { loadDeathIndex } from "../utils/scoring";
import type { Patient } from "../types/patient";

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

function top25Ids(patients: Patient[]): string[] {
  return patients.slice(0, 25).map((patient) => patient.patient_id);
}

function captured(ids: string[], deaths: Record<string, boolean>): number {
  return ids.filter((id) => deaths[id] === true).length;
}

export async function loadCaseReport(): Promise<CaseReport | null> {
  try {
    const [cohort, oldest, weight2, weight3, deaths] = await Promise.all([
      api<CohortCounts>("/cohorts/current"),
      loadRanking("oldest"),
      loadRanking(2),
      loadRanking(3),
      loadDeathIndex(),
    ]);
    const oldestIds = top25Ids(oldest.patients);
    const weight2Ids = top25Ids(weight2.patients);
    const weight3Ids = top25Ids(weight3.patients);
    const oldestDeaths = captured(oldestIds, deaths);
    const weight2Deaths = captured(weight2Ids, deaths);
    const weight3Deaths = captured(weight3Ids, deaths);
    return {
      kept: cohort.accepted_count ?? 0,
      dropped: cohort.missing_rows ?? 0,
      oldestDeaths,
      weight2Deaths,
      weight3Deaths,
      overlap: weight2Ids.filter((id) => weight3Ids.includes(id)).length,
      keepWeight2: weight2Deaths > oldestDeaths,
    };
  } catch {
    return null;
  }
}
