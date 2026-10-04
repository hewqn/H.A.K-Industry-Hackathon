import type { Patient } from "../types/patient";
import { parseCSV, rankPatients } from "../utils/scoring";
import { ApiError, api, command, post, type Health } from "./client";

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

const WEIGHT_METHODS = {
  2: "points_v1",
  3: "points_heart3",
} as const;

export type RankingMethod =
  | "patient_risk"
  | "oldest_first"
  | "points_v1"
  | "points_heart3";

export type QueueMode = "model" | "oldest" | 2 | 3;

const snapshotCache = new Map<string, Snapshot>();
const snapshotInflight = new Map<string, Promise<Snapshot>>();
let oldestRankCache: Record<string, number> | null = null;
let organRiskCache: { heart: Record<string, number>; kidney: Record<string, number> } | null =
  null;

function asFlag(value: boolean | number): boolean {
  return value === true || value === 1;
}

function asSex(value: boolean | number): number {
  return value === true || value === 1 ? 1 : 0;
}

function maxPointsCeiling(weight: number): number {
  return weight + 2 + 1 + 1 + 1 + 1;
}

function computePointsFromFacts(
  facts: ApiFacts,
  weight: number,
): { points: number; evidence: Patient["evidence"] } {
  const items: Patient["evidence"] = [];
  let points = 0;
  const ef = facts.ejection_fraction;
  const cr = facts.serum_creatinine;

  if (ef < 35) {
    points += weight;
    items.push({
      id: "ef_flag",
      field: "ejection_fraction",
      value: ef,
      unit: "%",
      points: weight,
      description: `EF ${ef}% is below 35%`,
    });
  }
  if (cr > 1.5) {
    points += 2;
    items.push({
      id: "cr_flag",
      field: "serum_creatinine",
      value: cr,
      unit: "mg/dL",
      points: 2,
      description: `Cr ${cr} is above 1.5`,
    });
  }
  if (asFlag(facts.anaemia)) {
    points += 1;
    items.push({ id: "anaemia_flag", field: "anaemia", value: true, points: 1, description: "Recorded anaemia" });
  }
  if (asFlag(facts.diabetes)) {
    points += 1;
    items.push({ id: "diabetes_flag", field: "diabetes", value: true, points: 1, description: "Recorded diabetes" });
  }
  if (asFlag(facts.high_blood_pressure)) {
    points += 1;
    items.push({ id: "bp_flag", field: "high_blood_pressure", value: true, points: 1, description: "Recorded high blood pressure" });
  }
  if (facts.age >= 70) {
    points += 1;
    items.push({ id: "age_flag", field: "age", value: facts.age, unit: "years", points: 1, description: `Age ${facts.age} is 70 or older` });
  }

  return { points, evidence: items };
}

function adaptRow(
  row: ApiRow,
  organRisk?: Patient["organ_risk"],
  oldestRank?: number,
  methodId?: string,
): Patient {
  const facts = row.facts;
  const ef = facts.ejection_fraction;
  const cr = facts.serum_creatinine;
  const efFlagged = ef < 35;
  const crFlagged = cr > 1.5;
  const scoreKind: Patient["score_kind"] =
    methodId === "oldest_first"
      ? "age"
      : row.score.kind === "model_output"
        ? "model_output"
        : "points";

  return {
    patient_id: row.patient_id,
    rank: row.call_rank,
    oldest_rank: oldestRank ?? row.model_rank,
    priority_band: row.priority_band,
    score: row.score.value,
    score_kind: scoreKind,
    organ_risk: organRisk,
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

export function apiMethodForQueue(mode: QueueMode, mlReady: boolean): RankingMethod {
  if (mode === "model") return mlReady ? "patient_risk" : "points_v1";
  if (mode === "oldest") return "oldest_first";
  if (mode === 2 || mode === 3) return WEIGHT_METHODS[mode];
  return "points_v1";
}

function scoreIndex(snapshot: Snapshot): Record<string, number> {
  const scores: Record<string, number> = {};
  for (const row of snapshot.rows ?? snapshot.queue ?? []) {
    scores[row.patient_id] = row.score.value;
  }
  return scores;
}

function rankIndex(snapshot: Snapshot): Record<string, number> {
  const ranks: Record<string, number> = {};
  for (const row of snapshot.rows ?? snapshot.queue ?? []) {
    ranks[row.patient_id] = row.call_rank;
  }
  return ranks;
}

function organRiskFor(
  patientId: string,
  organRisks: { heart: Record<string, number>; kidney: Record<string, number> },
): Patient["organ_risk"] {
  const heart = organRisks.heart[patientId];
  const kidney = organRisks.kidney[patientId];
  if (heart == null || kidney == null) return undefined;
  return { heart, kidney };
}

function fromSnapshot(
  snapshot: Snapshot,
  organRisks: { heart: Record<string, number>; kidney: Record<string, number> } = {
    heart: {},
    kidney: {},
  },
  oldestRanks: Record<string, number> = {},
): Patient[] {
  return (snapshot.queue ?? snapshot.rows ?? []).map((row) =>
    adaptRow(
      row,
      organRiskFor(row.patient_id, organRisks),
      oldestRanks[row.patient_id],
      snapshot.method_id,
    ),
  );
}

async function postSnapshot(methodId: string, cohort: Cohort): Promise<Snapshot> {
  const body = (revision: number) => ({
    ...command(revision),
    cohort_id: cohort.cohort_id,
    method_id: methodId,
    capacity: 25,
    mode: "operational" as const,
  });

  try {
    const mutation = await post<Mutation>("/ranking-snapshots", body(cohort.workflow_revision ?? 0));
    return mutation.snapshot;
  } catch (error) {
    if (!(error instanceof ApiError) || error.status !== 409) throw error;
    const fresh = await api<Cohort>("/cohorts/current");
    const mutation = await post<Mutation>(
      "/ranking-snapshots",
      body(fresh.workflow_revision ?? 0),
    );
    return mutation.snapshot;
  }
}

async function loadSnapshotUncached(methodId: string): Promise<Snapshot> {
  const cohort = await api<Cohort>("/cohorts/current");
  if (cohort.current_snapshot_id) {
    const existing = await api<Snapshot>(
      `/ranking-snapshots/${cohort.current_snapshot_id}`,
    );
    snapshotCache.set(existing.method_id, existing);
    if (existing.method_id === methodId) return existing;
  }
  const created = await postSnapshot(methodId, cohort);
  snapshotCache.set(methodId, created);
  return created;
}

function loadSnapshot(methodId: string): Promise<Snapshot> {
  const cached = snapshotCache.get(methodId);
  if (cached) return Promise.resolve(cached);
  const pending = snapshotInflight.get(methodId);
  if (pending) return pending;
  const request = loadSnapshotUncached(methodId).finally(() => {
    snapshotInflight.delete(methodId);
  });
  snapshotInflight.set(methodId, request);
  return request;
}

async function loadOrganRisks(
  mlReady: boolean,
): Promise<{ heart: Record<string, number>; kidney: Record<string, number> }> {
  if (!mlReady) return { heart: {}, kidney: {} };
  if (organRiskCache) return organRiskCache;
  const heart = await loadSnapshot("heart_risk");
  const kidney = await loadSnapshot("kidney_risk");
  organRiskCache = { heart: scoreIndex(heart), kidney: scoreIndex(kidney) };
  return organRiskCache;
}

async function loadOldestRanks(): Promise<Record<string, number>> {
  if (oldestRankCache) return oldestRankCache;
  const snapshot = await loadSnapshot("oldest_first");
  oldestRankCache = rankIndex(snapshot);
  return oldestRankCache;
}

async function rankFromApi(
  mode: QueueMode,
): Promise<{ patients: Patient[]; method: RankingMethod }> {
  const health = await api<Health>("/health", { signal: AbortSignal.timeout(2000) });
  const mlReady = health.ml === "frozen_cache_ready";

  if ((mode === 2 || mode === 3) && mlReady) {
    const weight = mode;
    const ceiling = maxPointsCeiling(weight);
    const [mlSnapshot, organRisks, oldestRanks] = await Promise.all([
      loadSnapshot("patient_risk"),
      loadOrganRisks(true),
      loadOldestRanks(),
    ]);
    const allRows = mlSnapshot.rows ?? mlSnapshot.queue ?? [];

    const combined = allRows.map((row) => {
      const mlScore = row.score.value;
      const { points, evidence } = computePointsFromFacts(row.facts, weight);
      return { row, mlScore, points, evidence, combined: mlScore + points / ceiling, mlRank: row.call_rank };
    });
    combined.sort((a, b) => b.combined - a.combined);

    return {
      patients: combined.slice(0, 25).map((item, idx) => {
        const base = adaptRow(
          item.row,
          organRiskFor(item.row.patient_id, organRisks),
          oldestRanks[item.row.patient_id],
          "patient_risk",
        );
        return {
          ...base,
          rank: idx + 1,
          score: item.points,
          score_kind: "combined" as const,
          evidence: item.evidence,
          model_rank: item.mlRank,
        };
      }),
      method: `combined_w${weight}` as unknown as RankingMethod,
    };
  }

  const methodId = apiMethodForQueue(mode, mlReady);
  const [snapshot, organRisks, oldestRanks] = await Promise.all([
    loadSnapshot(methodId),
    loadOrganRisks(mlReady),
    loadOldestRanks(),
  ]);
  return {
    patients: fromSnapshot(snapshot, organRisks, oldestRanks),
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

export async function loadRanking(mode: QueueMode): Promise<{
  patients: Patient[];
  source: "api" | "local";
  method: string;
}> {
  try {
    const { patients, method } = await rankFromApi(mode);
    if (patients.length === 0) throw new Error("empty");
    return { patients, source: "api", method };
  } catch {
    snapshotCache.clear();
    snapshotInflight.clear();
    oldestRankCache = null;
    organRiskCache = null;
    const patients = await rankFromCsv(mode === 3 ? 3 : 2);
    return {
      patients,
      source: "local",
      method: "points_local",
    };
  }
}
