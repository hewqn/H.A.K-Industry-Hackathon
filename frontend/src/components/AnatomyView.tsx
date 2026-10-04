import ScoreOutput from "./ScoreOutput";
import type { QueueMode } from "../api/loadRanking";
import type { Patient, OrganId } from "../types/patient";

interface AnatomyViewProps {
  patient: Patient;
  queueMode: QueueMode;
  onQueueModeChange: (mode: QueueMode) => void;
}

export default function AnatomyView({
  patient,
  queueMode,
  onQueueModeChange,
}: AnatomyViewProps) {
  return (
    <div className="anatomy-info">
      <header className="patient-head">
        <h2>
          Patient {patient.patient_id.replace("HF-", "").replace(/^0+/, "")}
        </h2>
        <ScoreOutput patient={patient} />
      </header>

      <section className="weight-control">
        <div>
          <h3>Heart weight</h3>
          <p className="weight-desc">
            {queueMode === "model"
              ? "Model ranks the call list."
              : queueMode === "oldest"
                ? "Oldest first. The baseline to beat."
                : `EF below 35% is worth ${queueMode} points.`}
          </p>
        </div>
        <div className="weight-buttons" role="group" aria-label="Heart weight">
          <button
            className={queueMode === "oldest" ? "active" : ""}
            onClick={() => onQueueModeChange("oldest")}
          >
            Oldest
          </button>
          {([2, 3] as const).map((w) => (
            <button
              key={w}
              className={queueMode === w ? "active" : ""}
              onClick={() => onQueueModeChange(w)}
              aria-label={`Heart weight ${w}`}
            >
              {w}
            </button>
          ))}
          <button
            className={queueMode === "model" ? "active" : ""}
            onClick={() => onQueueModeChange("model")}
          >
            Model
          </button>
        </div>
      </section>
    </div>
  );
}

export function PatientRecord({
  patient,
  focusedOrgan,
  onOrganSelect,
}: {
  patient: Patient;
  focusedOrgan: OrganId | null;
  onOrganSelect: (organ: OrganId | null) => void;
}) {
  const { facts, organs } = patient;
  const organCards: { id: OrganId; label: string; flag: string }[] = [
    { id: "heart", label: "Heart", flag: "EF < 35%" },
    { id: "kidney_left", label: "Kidneys", flag: "Cr > 1.5" },
  ];

  return (
    <div className="patient-record-block">
      <section className="organ-cards">
        {organCards.map(({ id, label, flag }) => {
          const indicator = organs[id];
          const isFocused = focusedOrgan === id;
          return (
            <button
              key={id}
              className={`organ-card ${isFocused ? "focused" : ""}`}
              onClick={() => onOrganSelect(isFocused ? null : id)}
            >
              <span className="organ-name">{label}</span>
              <span className="organ-card-value">
                {indicator.value !== null
                  ? `${indicator.value}${indicator.unit}`
                  : "—"}
              </span>
              {indicator.state === "flagged" && (
                <span className="flag-badge">{flag}</span>
              )}
            </button>
          );
        })}
      </section>
      <section className="patient-record">
        <div className="facts-grid">
          <div>
            <span>Age</span>
            <b>{facts.age} yr</b>
          </div>
          <div>
            <span>Sex</span>
            <b>{facts.sex === 1 ? "Male" : "Female"}</b>
          </div>
          <div>
            <span>Sodium</span>
            <b>{facts.serum_sodium}</b>
          </div>
          <div>
            <span>CPK</span>
            <b>{facts.creatinine_phosphokinase}</b>
          </div>
          <div>
            <span>Platelets</span>
            <b>{facts.platelets.toLocaleString()}</b>
          </div>
        </div>
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
      </section>
    </div>
  );
}
