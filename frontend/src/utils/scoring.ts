import type { Patient, OrganIndicator, EvidenceItem } from "../types/patient";

interface RawRow {
  age: number;
  anaemia: number;
  creatinine_phosphokinase: number;
  diabetes: number;
  ejection_fraction: number;
  high_blood_pressure: number;
  platelets: number;
  serum_creatinine: number;
  serum_sodium: number;
  sex: number;
  smoking: number;
  time: number;
  DEATH_EVENT: number;
}

function buildOrganIndicators(row: RawRow): Record<string, OrganIndicator> {
  const efFlagged = row.ejection_fraction < 35;
  const crFlagged = row.serum_creatinine > 1.5;

  return {
    heart: {
      state: efFlagged ? "flagged" : "not_flagged",
      value: row.ejection_fraction,
      unit: "%",
      label: efFlagged
        ? `EF ${row.ejection_fraction}% is below 35%`
        : `EF ${row.ejection_fraction}% is 35% or higher`,
    },
    kidney_left: {
      state: crFlagged ? "flagged" : "not_flagged",
      value: row.serum_creatinine,
      unit: "mg/dL",
      label: crFlagged
        ? `Creatinine ${row.serum_creatinine} mg/dL is above 1.5`
        : `Creatinine ${row.serum_creatinine} mg/dL is 1.5 or lower`,
    },
    kidney_right: {
      state: crFlagged ? "flagged" : "not_flagged",
      value: row.serum_creatinine,
      unit: "mg/dL",
      label: crFlagged
        ? `Creatinine ${row.serum_creatinine} mg/dL is above 1.5`
        : `Creatinine ${row.serum_creatinine} mg/dL is 1.5 or lower`,
    },
  };
}

function buildEvidence(row: RawRow, heartWeight: number): EvidenceItem[] {
  const items: EvidenceItem[] = [];

  if (row.ejection_fraction < 35) {
    items.push({
      id: "ef_flag",
      field: "ejection_fraction",
      value: row.ejection_fraction,
      unit: "%",
      points: heartWeight,
      description: `Ejection fraction ${row.ejection_fraction}% is below 35%`,
    });
  }
  if (row.serum_creatinine > 1.5) {
    items.push({
      id: "cr_flag",
      field: "serum_creatinine",
      value: row.serum_creatinine,
      unit: "mg/dL",
      points: 2,
      description: `Serum creatinine ${row.serum_creatinine} mg/dL is above 1.5`,
    });
  }
  if (row.anaemia) {
    items.push({
      id: "anaemia_flag",
      field: "anaemia",
      value: true,
      points: 1,
      description: "Recorded anaemia",
    });
  }
  if (row.diabetes) {
    items.push({
      id: "diabetes_flag",
      field: "diabetes",
      value: true,
      points: 1,
      description: "Recorded diabetes",
    });
  }
  if (row.high_blood_pressure) {
    items.push({
      id: "bp_flag",
      field: "high_blood_pressure",
      value: true,
      points: 1,
      description: "Recorded high blood pressure",
    });
  }
  if (row.age >= 70) {
    items.push({
      id: "age_flag",
      field: "age",
      value: row.age,
      unit: "years",
      points: 1,
      description: `Age ${row.age} is 70 or older`,
    });
  }

  return items;
}

function computeScore(row: RawRow, heartWeight: number): number {
  let score = 0;
  if (row.ejection_fraction < 35) score += heartWeight;
  if (row.serum_creatinine > 1.5) score += 2;
  score += row.anaemia;
  score += row.diabetes;
  score += row.high_blood_pressure;
  if (row.age >= 70) score += 1;
  return score;
}

export async function loadDeathIndex(): Promise<Record<string, boolean>> {
  const text = await fetch("/data/heart_failure_clinical_records.csv").then((response) => {
    if (!response.ok) throw new Error("csv");
    return response.text();
  });
  const deaths: Record<string, boolean> = {};
  parseCSV(text).forEach((row, index) => {
    deaths[`HF-${String(index + 1).padStart(4, "0")}`] = row.DEATH_EVENT === 1;
  });
  return deaths;
}

export function parseCSV(text: string): RawRow[] {
  const lines = text.trim().split("\n");
  const headers = lines[0].split(",");
  return lines.slice(1).map((line) => {
    const values = line.split(",");
    const obj: Record<string, number> = {};
    headers.forEach((h, i) => {
      obj[h.trim()] = parseFloat(values[i]);
    });
    return obj as unknown as RawRow;
  });
}

export function rankPatients(
  rows: RawRow[],
  heartWeight: number = 2,
  capacity: number = 25
): Patient[] {
  const oldestRankByIdx = new Map(
    [...rows]
      .map((row, idx) => ({ idx, age: row.age }))
      .sort((a, b) => b.age - a.age || a.idx - b.idx)
      .map((item, rank) => [item.idx, rank + 1])
  );

  const scored = rows.map((row, idx) => {
    const score = computeScore(row, heartWeight);
    const patientId = `HF-${String(idx + 1).padStart(4, "0")}`;
    return { row, score, patientId, idx };
  });

  scored.sort((a, b) => {
    if (b.score !== a.score) return b.score - a.score;
    return b.row.age - a.row.age; // tie-break by age descending
  });

  return scored.map(({ row, score, patientId, idx }, rank) => {
    const priorityBand =
      rank < capacity ? "higher" : rank < capacity * 2 ? "elevated" : "lower";

    return {
      patient_id: patientId,
      rank: rank + 1,
      oldest_rank: oldestRankByIdx.get(idx) ?? rank + 1,
      priority_band: priorityBand,
      score,
      score_kind: "points",
      facts: {
        age: row.age,
        ejection_fraction: row.ejection_fraction,
        serum_creatinine: row.serum_creatinine,
        anaemia: row.anaemia === 1,
        diabetes: row.diabetes === 1,
        high_blood_pressure: row.high_blood_pressure === 1,
        creatinine_phosphokinase: row.creatinine_phosphokinase,
        platelets: row.platelets,
        serum_sodium: row.serum_sodium,
        sex: row.sex,
        smoking: row.smoking === 1,
      },
      organs: buildOrganIndicators(row) as Record<
        "heart" | "kidney_left" | "kidney_right",
        OrganIndicator
      >,
      evidence: buildEvidence(row, heartWeight),
      workflow_state: "pending",
    };
  });
}
