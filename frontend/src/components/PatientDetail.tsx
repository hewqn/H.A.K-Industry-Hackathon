import type { Patient, OrganId } from "../types/patient";

interface PatientDetailProps {
  patient: Patient;
  focusedOrgan: OrganId | null;
}

export default function PatientDetail({ patient, focusedOrgan }: PatientDetailProps) {
  const { facts, evidence, organs } = patient;

  return (
    <div className="patient-detail">
      <div className="detail-header">
        <h2>{patient.patient_id}</h2>
        <span className={`priority-badge ${patient.priority_band}`}>
          {patient.priority_band} priority
        </span>
      </div>

      <div className="detail-score">
        <div className="score-value">{patient.score}</div>
        <div className="score-label">{patient.score_kind} score</div>
        <div className="score-rank">Rank #{patient.rank} of queue</div>
      </div>

      <div className="detail-section">
        <h3>Recorded Measurements</h3>
        <div className="measurements-grid">
          <div className={`measurement ${organs.heart.state === "flagged" ? "flagged" : ""}`}>
            <span className="measure-label">Ejection Fraction</span>
            <span className="measure-value">{facts.ejection_fraction}%</span>
            <span className="measure-threshold">
              {organs.heart.state === "flagged" ? "Below 35%" : "35% or higher"}
            </span>
          </div>
          <div className={`measurement ${organs.kidney_left.state === "flagged" ? "flagged" : ""}`}>
            <span className="measure-label">Serum Creatinine</span>
            <span className="measure-value">{facts.serum_creatinine} mg/dL</span>
            <span className="measure-threshold">
              {organs.kidney_left.state === "flagged" ? "Above 1.5" : "1.5 or lower"}
            </span>
          </div>
          <div className="measurement">
            <span className="measure-label">Age</span>
            <span className="measure-value">{facts.age} years</span>
          </div>
          <div className="measurement">
            <span className="measure-label">Serum Sodium</span>
            <span className="measure-value">{facts.serum_sodium} mEq/L</span>
          </div>
          <div className="measurement">
            <span className="measure-label">CPK</span>
            <span className="measure-value">{facts.creatinine_phosphokinase} mcg/L</span>
          </div>
          <div className="measurement">
            <span className="measure-label">Platelets</span>
            <span className="measure-value">{(facts.platelets / 1000).toFixed(0)}k</span>
          </div>
        </div>
      </div>

      <div className="detail-section">
        <h3>Recorded Conditions</h3>
        <div className="conditions">
          {facts.anaemia && <span className="condition-tag">Anaemia</span>}
          {facts.diabetes && <span className="condition-tag">Diabetes</span>}
          {facts.high_blood_pressure && <span className="condition-tag">High Blood Pressure</span>}
          {facts.smoking && <span className="condition-tag">Smoking</span>}
          {!facts.anaemia && !facts.diabetes && !facts.high_blood_pressure && !facts.smoking && (
            <span className="condition-tag none">No recorded conditions</span>
          )}
        </div>
      </div>

      <div className="detail-section">
        <h3>Priority Evidence</h3>
        <div className="evidence-list">
          {evidence.map((e) => (
            <div key={e.id} className="evidence-item">
              <span className="evidence-desc">{e.description}</span>
              {e.points !== undefined && (
                <span className="evidence-points">+{e.points} pts</span>
              )}
            </div>
          ))}
        </div>
      </div>

      {focusedOrgan && (
        <div className="detail-section organ-focus">
          <h3>
            {focusedOrgan === "heart" ? "Heart" : "Kidney"}
          </h3>
          <p className="organ-label">
            {organs[focusedOrgan].label}
          </p>
          <p className="organ-value">
            {organs[focusedOrgan].value !== null
              ? `${organs[focusedOrgan].value}${organs[focusedOrgan].unit}`
              : "No data available"}
          </p>
        </div>
      )}

      {patient.summary && (
        <div className="detail-section">
          <h3>Summary</h3>
          <p className="patient-summary">{patient.summary}</p>
        </div>
      )}
    </div>
  );
}
