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
    <aside className="queue-panel">
      <h3>Top 25</h3>
      <div className="queue-table-box">
        <div className="queue-table-head-wrap">
          <table className="queue-table">
            <ColumnGroup showMove={showMove} />
            <thead>
              <tr>
                <th>ID</th>
                <th>Patient</th>
                <th>EF</th>
                <th>Cr</th>
                <th>Age</th>
                <th>Score</th>
                {showMove && <th>{moveHeader}</th>}
              </tr>
            </thead>
          </table>
        </div>
        <div className="queue-table-wrap">
          <table className="queue-table">
            <ColumnGroup showMove={showMove} />
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
                    <td className="rank-cell">{currentRank}</td>
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
