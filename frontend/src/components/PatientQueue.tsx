import type { Patient } from "../types/patient";

interface PatientQueueProps {
  patients: Patient[];
  selectedId: string | null;
  onSelect: (id: string) => void;
}

function priorityColor(band: string): string {
  switch (band) {
    case "higher": return "#e74c3c";
    case "elevated": return "#e67e22";
    default: return "#27ae60";
  }
}

export default function PatientQueue({
  patients,
  selectedId,
  onSelect,
}: PatientQueueProps) {
  return (
    <div className="patient-queue">
      <div className="queue-header">
        <h2>Follow-Up Queue</h2>
        <span className="queue-count">{patients.length} patients</span>
      </div>
      <div className="queue-list">
        {patients.map((p) => (
          <div
            key={p.patient_id}
            className={`queue-item ${selectedId === p.patient_id ? "selected" : ""}`}
            onClick={() => onSelect(p.patient_id)}
          >
            <div className="queue-rank">#{p.rank}</div>
            <div className="queue-info">
              <div className="queue-id">{p.patient_id}</div>
              <div className="queue-metrics">
                <span>EF: {p.facts.ejection_fraction}%</span>
                <span>Cr: {p.facts.serum_creatinine} mg/dL</span>
                <span>Age: {p.facts.age}</span>
              </div>
            </div>
            <div className="queue-score">
              <div
                className="priority-dot"
                style={{ background: priorityColor(p.priority_band) }}
              />
              <span>{p.score} pts</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
