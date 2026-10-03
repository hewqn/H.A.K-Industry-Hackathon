import type { Patient, OrganId } from "../types/patient";

interface AnatomyViewProps {
  patient: Patient;
  totalPatients: number;
  focusedOrgan: OrganId | null;
  onOrganSelect: (organ: OrganId) => void;
}

export default function AnatomyView({
  patient,
  totalPatients,
  focusedOrgan,
  onOrganSelect,
}: AnatomyViewProps) {
  const { facts, organs } = patient;

  const organCards: { id: OrganId; label: string }[] = [
    { id: "heart", label: "Heart" },
    { id: "kidney_left", label: "Kidneys" },
  ];

  return (
    <div className="anatomy-info">
      <div className="info-header">
        <h2>
          Patient {patient.patient_id.replace("HF-", "").replace(/^0+/, "")}
        </h2>
        <p className="info-subtitle">
          Rank #{patient.rank} of {totalPatients}
        </p>
      </div>

      <div className="organ-cards">
        {organCards.map(({ id, label }) => {
          const indicator = organs[id];
          const isFocused = focusedOrgan === id;
          return (
            <button
              key={id}
              className={`organ-card ${indicator.state === "flagged" ? "flagged" : ""} ${isFocused ? "focused" : ""}`}
              onClick={() => onOrganSelect(id)}
            >
              <div className="organ-card-header">
                <span className="organ-name">{label}</span>
                {indicator.state === "flagged" && (
                  <span className="flag-badge">Over cutoff</span>
                )}
              </div>
              <div className="organ-card-value">
                {indicator.value !== null
                  ? `${indicator.value}${indicator.unit}`
                  : "—"}
              </div>
              <div className="organ-card-label">{indicator.label}</div>
            </button>
          );
        })}
      </div>

      <div className="measurements-section">
        <h3>Recorded Measurements</h3>
        <table className="data-table">
          <tbody>
            <tr>
              <td className="table-label">Age</td>
              <td className="table-value">{facts.age} years</td>
            </tr>
            <tr>
              <td className="table-label">Ejection Fraction</td>
              <td className="table-value">{facts.ejection_fraction}%</td>
            </tr>
            <tr>
              <td className="table-label">Serum Creatinine</td>
              <td className="table-value">{facts.serum_creatinine} mg/dL</td>
            </tr>
            <tr>
              <td className="table-label">Serum Sodium</td>
              <td className="table-value">{facts.serum_sodium} mEq/L</td>
            </tr>
            <tr>
              <td className="table-label">CPK</td>
              <td className="table-value">{facts.creatinine_phosphokinase} mcg/L</td>
            </tr>
            <tr>
              <td className="table-label">Platelets</td>
              <td className="table-value">
                {facts.platelets.toLocaleString()}
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <div className="conditions-section">
        <h3>Recorded Conditions</h3>
        <div className="condition-list">
          {facts.anaemia && <span className="cond-pill">Anaemia</span>}
          {facts.diabetes && <span className="cond-pill">Diabetes</span>}
          {facts.high_blood_pressure && (
            <span className="cond-pill">High Blood Pressure</span>
          )}
          {facts.smoking && <span className="cond-pill">Smoking</span>}
          {!facts.anaemia &&
            !facts.diabetes &&
            !facts.high_blood_pressure &&
            !facts.smoking && (
              <span className="cond-pill none">None recorded</span>
            )}
        </div>
      </div>
    </div>
  );
}
