import type { Patient } from "../types/patient";

interface Top25TableProps {
  patients: Patient[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  onPreview?: (id: string | null) => void;
}

function patientNumber(id: string): string {
  return id.replace("HF-", "").replace(/^0+/, "");
}

export default function Top25Table({
  patients,
  selectedId,
  onSelect,
  onPreview,
}: Top25TableProps) {
  const top25 = patients.slice(0, 25);

  return (
    <aside className="queue-panel">
      <h3>Top 25</h3>
      <div className="queue-table-wrap">
        <table className="queue-table">
          <thead>
            <tr>
              <th>#</th>
              <th>Patient</th>
              <th>EF</th>
              <th>Cr</th>
              <th>Age</th>
              <th>Score</th>
            </tr>
          </thead>
          <tbody>
            {top25.map((patient, index) => {
              const selected = patient.patient_id === selectedId;
              return (
                <tr
                  key={patient.patient_id}
                  className={selected ? "highlight" : ""}
                  onClick={() => onSelect(patient.patient_id)}
                  onMouseEnter={() => onPreview?.(patient.patient_id)}
                  onMouseLeave={() => onPreview?.(null)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" || event.key === " ") {
                      event.preventDefault();
                      onSelect(patient.patient_id);
                    }
                  }}
                  tabIndex={0}
                  role="button"
                  aria-pressed={selected}
                  aria-label={`Select patient ${patientNumber(patient.patient_id)}`}
                >
                  <td className="rank-cell">{index + 1}</td>
                  <td>Patient {patientNumber(patient.patient_id)}</td>
                  <td
                    className={
                      patient.facts.ejection_fraction < 35 ? "warn" : ""
                    }
                  >
                    {patient.facts.ejection_fraction}%
                  </td>
                  <td
                    className={
                      patient.facts.serum_creatinine > 1.5 ? "warn" : ""
                    }
                  >
                    {patient.facts.serum_creatinine}
                  </td>
                  <td>{patient.facts.age}</td>
                  <td className="score-cell">{patient.score}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </aside>
  );
}
