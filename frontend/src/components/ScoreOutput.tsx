import type { EvidenceItem, Patient } from "../types/patient";

interface ScoreOutputProps {
  patient: Patient;
}

function evidenceLabel(item: EvidenceItem): string {
  switch (item.field) {
    case "ejection_fraction":
      return `EF ${item.value}${item.unit} < 35`;
    case "serum_creatinine":
      return `Cr ${item.value} > 1.5`;
    case "anaemia":
      return "Anaemia";
    case "diabetes":
      return "Diabetes";
    case "high_blood_pressure":
      return "High BP";
    case "age":
      return `Age ${item.value}`;
    default:
      return item.description;
  }
}

export default function ScoreOutput({
  patient,
}: ScoreOutputProps) {
  return (
    <div className="score-strip">
      <div className="score-strip-head">
        <span className="risk-score-number">{patient.score}</span>
        <span className="risk-score-label">
          {patient.score_kind === "model_output" ? "Model" : "Score"}
        </span>
      </div>
      {patient.evidence.length > 0 ? (
        <div className="evidence-chips">
          {patient.evidence.map((item) => (
            <span
              key={item.id}
              className="evidence-chip"
              title={item.description}
            >
              {evidenceLabel(item)}
              {item.points !== undefined && <b>+{item.points}</b>}
            </span>
          ))}
        </div>
      ) : (
        <p className="no-evidence">No factors flagged</p>
      )}
    </div>
  );
}
