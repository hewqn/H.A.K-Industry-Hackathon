import type { EvidenceItem, Patient } from "../types/patient";

interface ScoreOutputProps {
  patient: Patient;
}

function evidenceLabel(item: EvidenceItem): string {
  switch (item.field) {
    case "ejection_fraction":
      return `EF ${item.value}${item.unit ?? "%"}`;
    case "serum_creatinine":
      return `Cr ${item.value}`;
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
        {patient.score_kind === "model_output" && <span className="score-metric">
          <span className="risk-score-number">{patient.score.toFixed(3)}</span>
          <span className="risk-score-label">Patient ML score</span>
        </span>}
        {patient.score_kind === "combined" && <span className="score-metric" title="Patient ML score + rule points divided by the points ceiling">
          <span className="risk-score-number">{patient.combined_score?.toFixed(3) ?? "—"}</span>
          <span className="risk-score-label">Combined score</span>
        </span>}
        {(patient.score_kind === "points" || patient.score_kind === "combined") && (
          <span className="score-metric">
            <span className="risk-score-number">{patient.score}</span>
            <span className="risk-score-label">{patient.score_kind === "combined" ? "Pts" : "Score"}</span>
          </span>
        )}
      </div>
      {(patient.score_kind === "points" || patient.score_kind === "combined") && patient.evidence.length > 0 ? (
        <div className="evidence-chips">
          {patient.evidence
            .filter((item) => item.points != null)
            .map((item) => (
              <span
                key={item.id}
                className="evidence-chip"
                title={item.description}
              >
                {evidenceLabel(item)}
                <b>+{item.points}</b>
              </span>
            ))}
        </div>
      ) : null}
    </div>
  );
}
