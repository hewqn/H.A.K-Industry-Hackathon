import type { Patient } from "../types/patient";
import InterfaceIcon from "./InterfaceIcon";

interface Top25TableProps {
  patients: Patient[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  onPreview?: (id: string | null) => void;
}

function patientNumber(id: string): string {
  return id.replace("HF-", "").replace(/^0+/, "");
}

function moveLabel(currentRank: number, compareRank?: number): string | null {
  if (compareRank == null) return null;
  const delta = compareRank - currentRank;
  if (delta === 0) return "0";
  return delta > 0 ? `+${delta}` : String(delta);
}

function ColumnGroup({ showMove }: { showMove: boolean }) {
  return (
    <colgroup>
      <col className="col-id" />
      <col className="col-patient" />
      <col className="col-ef" />
      <col className="col-cr" />
      <col className="col-age" />
      <col className="col-score" />
      {showMove && <col className="col-move" />}
    </colgroup>
  );
}

export default function Top25Table({
  patients,
  selectedId,
  onSelect,
  onPreview,
}: Top25TableProps) {
  const top25 = patients.slice(0, 25);
  const isCombined = top25.some((p) => p.score_kind === "combined");
  const showMove = isCombined
    ? top25.some((p) => p.model_rank != null)
    : top25.some(
        (p) => p.score_kind === "points" && p.oldest_rank != null,
      );
  const moveHeader = isCombined ? "vs Model" : "vs Oldest";

  return (
    <aside className="queue-panel" aria-label="Top 25 call list">
      <div className="panel-heading"><div><p className="eyebrow">Current call order</p><h3>Top 25 <span className="count-badge">{top25.length}</span></h3></div><InterfaceIcon name="queue" /></div>
      <p className="queue-description">Select a record to review its measurements and evidence.</p>
      <div className="queue-table-box">
        <div className="queue-table-wrap">
          {/* One table keeps column headers associated with the scrollable rows.
              Native patient buttons preserve keyboard selection and row clicks. */}
          <table className="queue-table">
            <caption className="sr-only">First 25 patients in the active call order. EF is a percentage, Cr is mg/dL and Age is years.</caption>
            <ColumnGroup showMove={showMove} />
            <thead>
              <tr>
                <th scope="col">Rank</th>
                <th scope="col">Patient</th>
                <th scope="col" title="Ejection fraction (%)">EF</th>
                <th scope="col" title="Serum creatinine (mg/dL)">Cr</th>
                <th scope="col" title="Age (years)">Age</th>
                <th scope="col">Score</th>
                {showMove && <th scope="col">{moveHeader}</th>}
              </tr>
            </thead>
            <tbody>
              {top25.map((patient, index) => {
                const selected = patient.patient_id === selectedId;
                const currentRank = index + 1;
                const move = showMove
                  ? moveLabel(
                      currentRank,
                      isCombined ? patient.model_rank : patient.oldest_rank,
                    )
                  : null;
                const rose = move != null && move.startsWith("+");
                const fell = move != null && move.startsWith("-");
                return (
                  <tr
                    key={patient.patient_id}
                    className={selected ? "highlight" : ""}
                    onClick={() => onSelect(patient.patient_id)}
                    onMouseEnter={() => onPreview?.(patient.patient_id)}
                    onMouseLeave={() => onPreview?.(null)}
                  >
                    <td className="rank-cell">{currentRank}</td>
                    <td><button className="queue-patient-button" aria-pressed={selected}
                      aria-label={`Select patient ${patientNumber(patient.patient_id)}`}>
                      <span>Patient {patientNumber(patient.patient_id)}</span><small>{patient.patient_id}</small>
                    </button></td>
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
                    <td className="score-cell">
                      {patient.score_kind === "combined"
                        ? patient.combined_score?.toFixed(3) ?? "—"
                        : patient.score_kind === "model_output"
                        ? patient.score.toFixed(3)
                        : patient.score_kind === "age"
                          ? "—"
                          : patient.score}
                    </td>
                    {showMove && (
                      <td
                        className={
                          rose ? "move-up" : fell ? "move-down" : "move-same"
                        }
                      >
                        {move ?? "—"}
                      </td>
                    )}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </aside>
  );
}
