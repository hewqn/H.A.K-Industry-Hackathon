import { useEffect, useState } from "react";
import { api, type Cohort, type Models, type OrganId, type Patient, type Snapshot } from "./api/client";
import { AnatomyViewer } from "./components/AnatomyViewer";

/** Frontend owner's working layout and selection example, not the completed product.
 * TODO(FRONTEND): method/capacity controls, full-cohort search, workflow forms,
 * comparisons/history screens, CSV handoff, voice controls/transcript, and responsive QA.
 * Numerical logic belongs to the API. Keep one patient/snapshot state for every panel.
 */
export function App() {
  const [cohort, setCohort] = useState<Cohort | null>(null);
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [models, setModels] = useState<Models | null>(null);
  const [patientId, setPatientId] = useState("");
  const [patient, setPatient] = useState<Patient | null>(null);
  const [organ, setOrgan] = useState<OrganId | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    const controller = new AbortController();
    async function load() {
      try {
        const current = await api<Cohort>("/cohorts/current", { signal: controller.signal });
        const [ranking, methods] = await Promise.all([
          api<Snapshot>(`/ranking-snapshots/${current.current_snapshot_id}`, { signal: controller.signal }),
          api<Models>("/models", { signal: controller.signal }),
        ]);
        if (!controller.signal.aborted) { setCohort(current); setSnapshot(ranking); setModels(methods); setPatientId(ranking.queue[0].patient_id); }
      } catch (error) { if (!controller.signal.aborted) setError((error as Error).message); }
    }
    void load(); return () => controller.abort();
  }, []);
  useEffect(() => {
    setPatient(null); setOrgan(null);
    if (!snapshot || !patientId) return;
    const controller = new AbortController();
    api<Patient>(`/patients/${patientId}?snapshot_id=${snapshot.snapshot_id}`, { signal: controller.signal }).then(value => {
      // Cancel and check context before applying a delayed patient/summary response.
      if (!controller.signal.aborted && value.patient_id === patientId && value.ranking_snapshot_id === snapshot.snapshot_id) setPatient(value);
    }).catch(error => { if (!controller.signal.aborted) setError((error as Error).message); });
    return () => controller.abort();
  }, [patientId, snapshot]);

  return <div className="app-shell">
    <header><div><p className="eyebrow">Biomedical · Case 2 · Team development scaffold</p><h1>Heart-failure follow-up</h1><p>Frozen model scores and shared patient contract.</p></div><div className="mode-tag">{models?.supervised_status === "ready" ? "Frozen ML cache ready" : "Points starter"}<small>Database, voice, and final 3D integrations are pending.</small></div></header>
    {error && <p className="error-banner" role="alert">{error}. Start the API with <code>make api</code>.</p>}
    {cohort && snapshot ? <><section className="toolbar"><div><strong>{cohort.accepted_count}</strong> accepted · {cohort.missing_rows} missing rows</div><div>Method: {snapshot.method_id}<small>Capacity: {snapshot.capacity} · {snapshot.tie_policy}</small></div><div className="snapshot-time">Snapshot {snapshot.snapshot_id.slice(0, 8)}<small>Preview only; not durable</small></div></section>
      <main className="workspace"><aside className="patient-list"><h2>Default top 25</h2><div className="queue-scroll">{snapshot.queue.map(row => <button key={row.patient_id} className={`patient-row ${patientId === row.patient_id ? "selected" : ""}`} onClick={() => setPatientId(row.patient_id)}><span className="rank">{row.call_rank}</span><span><strong>{row.patient_id}</strong><small>{row.score.value.toFixed(row.score.kind === "points" ? 0 : 3)} {row.score.kind === "points" ? "points" : "model score"} · {row.priority_band} priority</small><small>EF {row.facts.ejection_fraction}% · Cr {row.facts.serum_creatinine} mg/dL</small><small>{row.reason}</small></span></button>)}</div></aside>
        {patient ? <><AnatomyViewer patient_id={patient.patient_id} ranking_snapshot_id={patient.ranking_snapshot_id} indicator_policy_version={patient.indicator_policy_version} organs={patient.organs} model_risks={patient.model_risks ?? null} focused_organ={organ} body_opacity={.15} reduced_motion={window.matchMedia("(prefers-reduced-motion: reduce)").matches} onOrganSelect={setOrgan} onReady={() => {}} onError={() => {}} />
          <section className="patient-detail"><h2>{patient.patient_id}</h2><p>Method rank {patient.model_rank} · call rank {patient.call_rank ?? "outside queue"}</p><h3>Recorded measurements</h3><p>EF {patient.facts.ejection_fraction}% · serum creatinine {patient.facts.serum_creatinine} mg/dL · age {patient.facts.age}</p>{organ && <p className="focused-organ">{organ.replace("_", " ")}: {patient.organs[organ].label}</p>}<h3>Why this priority?</h3><ul>{patient.score.evidence.map(item => <li key={item.id}>{item.predicate}{item.points != null ? ` · +${item.points} points` : item.contribution != null ? ` · ${item.contribution.toFixed(3)} log-odds contribution` : " · recorded model input"}</li>)}</ul>{patient.model_risks && <><h3>Model outputs</h3><p>Uncalibrated recorded-outcome proxies. Bands are relative model scores.</p><ul>{(["heart_risk", "kidney_risk", "patient_risk"] as const).map(task => { const estimate = patient.model_risks![task]; return <li key={task}><strong>{task.replaceAll("_", " ")}</strong>: {estimate.score.toFixed(3)} · {estimate.band} band · {estimate.classification_positive ? "above" : "below"} model cutoff ({estimate.classification_threshold.toFixed(3)})<small>{estimate.model_family.replaceAll("_", " ")} · {estimate.prediction_provenance.replaceAll("_", " ")}</small></li>; })}</ul></>}<h3>Factual overview · template</h3><p>{patient.summary.text}</p><details><summary>Frontend/API integration TODOs</summary><p>Connect workflow forms after backend persistence passes its tests. Add voice session controls and transcript. Extend method/capacity controls using versioned snapshots. See docs/development.md.</p></details></section>
        </> : <p role="status">Loading selected patient…</p>}
      </main>
      {models && <section className="comparison-page"><h2>Descriptive benchmark reference</h2><p>Fixed historical cohort, N=299, K=25. Supervised reports and selections are available from the frozen model bundle when published.</p><div className="metric-cards">{Object.entries(models.reports.benchmark.metrics).map(([method, value]) => <article key={method}><h4>{method}</h4><strong>{value.captured_outcomes}/25</strong><p>Recorded outcomes captured</p></article>)}</div>{models.supervised_status === "ready" && <><h3>Frozen model selections</h3><ul>{Object.entries(models.selected_models).map(([task, model]) => <li key={task}>{task.replaceAll("_", " ")}: {model.family.replaceAll("_", " ")} · cutoff {model.classification_threshold.toFixed(3)}</li>)}</ul></>}<p>Heart-only revision: {models.reports.benchmark.decision.replaceAll("_", " ")} · overlap {models.reports.benchmark.overlap_count}/25.</p></section>}
    </> : <p role="status">Loading local cohort…</p>}
    <footer>Public historical records · Follow-up prioritization prototype · No diagnoses or treatment recommendations</footer>
  </div>;
}
