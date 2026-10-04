import ScoreOutput from "./ScoreOutput";
import type { Patient } from "../types/patient";

interface RiskViewProps {
  patient: Patient;
  patients: Patient[];
  heartWeight: number;
  onHeartWeightChange: (w: number) => void;
}

export default function RiskView({
  patient,
  heartWeight,
  onHeartWeightChange,
}: RiskViewProps) {
  return (
    <div className="risk-left">
      <div className="risk-header">
        <h2>Risk Assessment</h2>
        <p className="risk-subtitle">
          Patient {patient.patient_id.replace("HF-", "").replace(/^0+/, "")}
        </p>
      </div>

      <ScoreOutput patient={patient} />

      <div className="weight-control">
        <h3>Heart weight</h3>
        <p className="weight-desc">
          Extra points when ejection fraction is below 35%.
        </p>
        <div className="weight-buttons">
          {[2, 3].map((w) => (
            <button
              key={w}
              className={heartWeight === w ? "active" : ""}
              onClick={() => onHeartWeightChange(w)}
            >
              {w}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
