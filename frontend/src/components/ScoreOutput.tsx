import type { Patient } from "../types/patient";

interface ScoreOutputProps {
  patient: Patient;
  totalPatients: number;
}

export default function ScoreOutput({
  patient,
  totalPatients,
}: ScoreOutputProps) {
  return (
    <>
      <div className="risk-score-card">
        <div className="risk-score-number">{patient.score}</div>
        <div className="risk-score-label">
          {patient.score_kind === "model_output" ? "Model score" : "Score"}
        </div>
        <div className={`risk-badge ${patient.priority_band}`}>
          {patient.priority_band}
        </div>
        <div className="risk-rank">
          Rank #{patient.rank} of {totalPatients}
        </div>
      </div>

      <div className="risk-evidence">
        <h3>Score Breakdown</h3>
        {patient.evidence.length > 0 ? (
          <div className="evidence-rows">
            {patient.evidence.map((item) => (
              <div key={item.id} className="evidence-row">
                <span className="ev-description">{item.description}</span>
                {item.points !== undefined && (
                  <span className="ev-points">+{item.points}</span>
                )}
              </div>
            ))}
            <div className="evidence-row total">
              <span className="ev-description">Total</span>
              <span className="ev-points">{patient.score}</span>
            </div>
          </div>
        ) : (
          <p className="no-evidence">No risk factors flagged</p>
        )}
      </div>
    </>
  );
}
