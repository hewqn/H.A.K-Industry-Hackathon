import type { Patient } from "../types/patient";
import { heartRiskFromData, kidneyScalePosition } from "../utils/organColors";
import { parseCSV, rankPatients } from "../utils/scoring";
import { api, command, post } from "./client";

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
  snapshot_id: string;
  cohort_id: string;
  method_id: string;
  rows: ApiRow[];
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

export function apiMethodForWeight(heartWeight: number): "points_v1" | "points_heart3" | null {
  if (heartWeight === 2) return "points_v1";
  if (heartWeight === 3) return "points_heart3";
  return null;
}

// Retain the exact snapshot shown on screen for every voice evidence request.
export interface RankingContext {
  snapshot_id: string;
  cohort_id: string;
  method_id: string;
}

export interface LoadedRanking {
  patients: Patient[];
  source: "api" | "local";
  context: RankingContext | null;
}

function fromSnapshot(snapshot: Snapshot, heartWeight: number): LoadedRanking {
  return {
    patients: snapshot.rows.map((row) => adaptRow(row, heartWeight)),
    source: "api",
    context: {
      snapshot_id: snapshot.snapshot_id,
      cohort_id: snapshot.cohort_id,
      method_id: snapshot.method_id,
    },
  };
}

async function rankFromApi(heartWeight: number): Promise<LoadedRanking> {
  const methodId = apiMethodForWeight(heartWeight);
  if (!methodId) throw new Error("api_method_unavailable");

  await api("/health", { signal: AbortSignal.timeout(2000) });
  const cohort = await api<Cohort>("/cohorts/current");

  if (methodId === "points_v1" && cohort.current_snapshot_id) {
    const existing = await api<Snapshot>(
      `/ranking-snapshots/${cohort.current_snapshot_id}`,
    );
    if (existing.method_id === "points_v1") {
      return fromSnapshot(existing, heartWeight);
    }
  }

  const mutation = await post<Mutation>("/ranking-snapshots", {
    ...command(cohort.workflow_revision ?? 0),
    cohort_id: cohort.cohort_id,
    method_id: methodId,
    capacity: 25,
    mode: "operational",
  });
  return fromSnapshot(mutation.snapshot, heartWeight);
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

export async function loadRanking(heartWeight: number): Promise<LoadedRanking> {
  try {
    const result = await rankFromApi(heartWeight);
    if (result.patients.length === 0) throw new Error("empty");
    return result;
  } catch {
    const patients = await rankFromCsv(heartWeight);
    return { patients, source: "local", context: null };
  }
}
