import type { Patient } from "../types/patient";
import { heartRiskFromData, kidneyScalePosition } from "../utils/organColors";
import { parseCSV, rankPatients } from "../utils/scoring";
import { api, command, post, type Health } from "./client";

interface ApiScore {
  value: number;
  kind: string;
  evidence?: {
    id: string;
    field: string;
    value: number | boolean;
    unit?: string | null;
    predicate?: string;
    points?: number | null;
    scale?: string;
  }[];
}

interface ApiFacts {
  age: number;
  anaemia: boolean;
  creatinine_phosphokinase: number;
  diabetes: boolean;
  ejection_fraction: number;
  high_blood_pressure: boolean;
  platelets: number;
  serum_creatinine: number;
  serum_sodium: number;
  sex: boolean | number;
  smoking: boolean;
}

interface ApiRow {
  patient_id: string;
  model_rank: number;
  call_rank: number;
  priority_band: Patient["priority_band"];
  score: ApiScore;
  facts: ApiFacts;
  workflow_state?: Patient["workflow_state"];
}

interface Snapshot {
  method_id: string;
  rows?: ApiRow[];
  queue?: ApiRow[];
}

interface Cohort {
  cohort_id: string;
  current_snapshot_id?: string | null;
  workflow_revision?: number;
}

interface Mutation {
  snapshot: Snapshot;
}

function asFlag(value: boolean | number): boolean {
  return value === true || value === 1;
}

function asSex(value: boolean | number): number {
  return value === true || value === 1 ? 1 : 0;
}

function adaptRow(row: ApiRow, heartWeight: number): Patient {
  const facts = row.facts;
  const ef = facts.ejection_fraction;
  const cr = facts.serum_creatinine;
  const efFlagged = ef < 35;
  const crFlagged = cr > 1.5;

  return {
    patient_id: row.patient_id,
    rank: row.call_rank,
    oldest_rank: row.model_rank,
    priority_band: row.priority_band,
    score: row.score.value,
    score_kind: row.score.kind === "model_output" ? "model_output" : "points",
    organ_risk: {
      heart: heartRiskFromData(ef, heartWeight),
      kidney: kidneyScalePosition(cr),
    },
    facts: {
      age: facts.age,
      ejection_fraction: ef,
      serum_creatinine: cr,
      anaemia: asFlag(facts.anaemia),
      diabetes: asFlag(facts.diabetes),
      high_blood_pressure: asFlag(facts.high_blood_pressure),
      creatinine_phosphokinase: facts.creatinine_phosphokinase,
      platelets: facts.platelets,
      serum_sodium: facts.serum_sodium,
      sex: asSex(facts.sex),
      smoking: asFlag(facts.smoking),
    },
    organs: {
      heart: {
        state: efFlagged ? "flagged" : "not_flagged",
        value: ef,
        unit: "%",
        label: efFlagged
          ? `EF ${ef}% is below 35%`
          : `EF ${ef}% is 35% or higher`,
      },
      kidney_left: {
        state: crFlagged ? "flagged" : "not_flagged",
        value: cr,
        unit: "mg/dL",
        label: crFlagged
          ? `Creatinine ${cr} mg/dL is above 1.5`
          : `Creatinine ${cr} mg/dL is 1.5 or lower`,
      },
      kidney_right: {
        state: crFlagged ? "flagged" : "not_flagged",
        value: cr,
        unit: "mg/dL",
        label: crFlagged
          ? `Creatinine ${cr} mg/dL is above 1.5`
          : `Creatinine ${cr} mg/dL is 1.5 or lower`,
      },
    },
    evidence: (row.score.evidence ?? [])
      .filter((item) => item.scale !== "measurement")
      .map((item) => ({
        id: item.id,
        field: item.field,
        value: item.value,
        unit: item.unit ?? undefined,
        points: item.points ?? undefined,
        description: item.predicate ?? item.field,
      })),
    workflow_state: row.workflow_state ?? "pending",
  };
}

export type RankingMethod = "patient_risk" | "points_v1" | "points_heart3";

export function apiMethodForWeight(
  heartWeight: number,
  mlReady: boolean,
): RankingMethod | null {
  if (heartWeight === 2) return mlReady ? "patient_risk" : "points_v1";
  if (heartWeight === 3) return "points_heart3";
  return null;
}

function fromSnapshot(snapshot: Snapshot, heartWeight: number): Patient[] {
  return (snapshot.queue ?? snapshot.rows ?? []).map((row) =>
    adaptRow(row, heartWeight),
  );
}

async function rankFromApi(
  heartWeight: number,
): Promise<{ patients: Patient[]; method: RankingMethod }> {
  const health = await api<Health>("/health", { signal: AbortSignal.timeout(2000) });
  const methodId = apiMethodForWeight(heartWeight, health.ml === "frozen_cache_ready");
  if (!methodId) throw new Error("api_method_unavailable");

  const cohort = await api<Cohort>("/cohorts/current");

  if (cohort.current_snapshot_id) {
    const existing = await api<Snapshot>(
      `/ranking-snapshots/${cohort.current_snapshot_id}`,
    );
    if (existing.method_id === methodId) {
      return { patients: fromSnapshot(existing, heartWeight), method: methodId };
    }
  }

  const mutation = await post<Mutation>("/ranking-snapshots", {
    ...command(cohort.workflow_revision ?? 0),
    cohort_id: cohort.cohort_id,
    method_id: methodId,
    capacity: 25,
    mode: "operational",
  });
  return {
    patients: fromSnapshot(mutation.snapshot, heartWeight),
    method: methodId,
  };
}

async function rankFromCsv(heartWeight: number): Promise<Patient[]> {
  const text = await fetch("/data/heart_failure_clinical_records.csv").then(
    (response) => {
      if (!response.ok) throw new Error("csv");
      return response.text();
    },
  );
  return rankPatients(parseCSV(text), heartWeight, 25);
}

export async function loadRanking(heartWeight: number): Promise<{
  patients: Patient[];
  source: "api" | "local";
  method: string;
}> {
  try {
    const { patients, method } = await rankFromApi(heartWeight);
    if (patients.length === 0) throw new Error("empty");
    return { patients, source: "api", method };
  } catch {
    const patients = await rankFromCsv(heartWeight);
    return { patients, source: "local", method: "points_local" };
  }
}
