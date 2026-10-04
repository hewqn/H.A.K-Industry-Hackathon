import type { Patient } from "../types/patient";

/** Shared snapshot outputs, including the classifier threshold (not a band cutoff). */
export default function ModelRiskPanel({ patient }: { patient: Patient }) {
  const risks = patient.model_risks;
  if (!risks) return <section className="model-risk-panel"><p>ML outputs unavailable. The current list uses its displayed ordering method.</p></section>;
  return <section className="model-risk-panel" aria-label="ML outputs">
    <h3>ML outputs</h3>
    <div className="risk-output-grid">
      {([ ["heart_risk", "Heart"], ["kidney_risk", "Kidneys"], ["patient_risk", "Patient"] ] as const).map(([task, label]) => {
        const risk = risks[task];
        return <div key={task}>
          <span>{label}</span><strong>{risk.score.toFixed(3)}</strong>
          <span>{risk.band} band</span>
          <small>{risk.classification_positive ? "Positive" : "Negative"} at {risk.classification_threshold.toFixed(3)}</small>
        </div>;
      })}
    </div>
    <p>Uncalibrated recorded-outcome proxies. Organ models are not diagnoses; scores are not validated death probabilities.</p>
    <details><summary>Model versions and evidence</summary>
      <p>Bundle: {risks.bundle_id}</p>
      {(["heart_risk", "kidney_risk", "patient_risk"] as const).map((task) => {
        const risk = risks[task];
        return <div key={task}>
          <h4>{task}</h4><p>{risk.model_family} · {risk.model_version} · {risk.prediction_provenance}</p>
          <p>{risk.explanation_method === "linear_log_odds" ? "Scaled linear log-odds contributions" : "Recorded model inputs; no local attribution"}</p>
          <ul>{risk.evidence.map((item) => <li key={item.id}>{item.field}: {String(item.value)} {item.unit}
            {item.contribution == null ? "" : ` · log-odds ${item.contribution.toFixed(3)}`}</li>)}</ul>
          {risk.intercept != null && <p>Log-odds intercept: {risk.intercept.toFixed(3)}</p>}
        </div>;
      })}
    </details>
  </section>;
}
