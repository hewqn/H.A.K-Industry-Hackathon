import { useEffect, useRef, useState, type FormEvent, type ReactNode } from "react";
import { deletePatient, patientError, savePatient, updatePatient, type PatientFacts } from "../api/patients";
import type { Patient } from "../types/patient";

const measurements = [
  ["age", "Age (years)", true],
  ["ejection_fraction", "Ejection fraction (%)", false],
  ["serum_creatinine", "Serum creatinine (mg/dL)", true],
  ["serum_sodium", "Serum sodium (mEq/L)", true],
  ["platelets", "Platelets (platelets/µL)", false],
  ["creatinine_phosphokinase", "Creatinine phosphokinase (mcg/L)", false],
] as const;
const flags = [
  ["anaemia", "Anaemia"], ["diabetes", "Diabetes"],
  ["high_blood_pressure", "High blood pressure"], ["smoking", "Smoking"],
  ["sex", "Recorded sex"],
] as const;

function Modal({ title, busy, onCancel, children }: {
  title: string; busy: boolean; onCancel: () => void; children: ReactNode;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => { if (dialog.current && !dialog.current.open) dialog.current.showModal(); }, []);
  return <dialog ref={dialog} className="patient-dialog" aria-label={title}
    onCancel={(event) => { event.preventDefault(); if (!busy) onCancel(); }}>
    <h2>{title}</h2>{children}
  </dialog>;
}

export default function PatientActions({ patient, enabled, loading, onBusy, onChanged }: {
  patient: Patient | null; enabled: boolean; loading: boolean;
  onBusy: (busy: boolean) => void;
  onChanged: (patientId?: string) => void;
}) {
  const [action, setAction] = useState<"add" | "edit" | "delete" | null>(null);
  const [targetId, setTargetId] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  // Retain this ID after network errors so an ambiguous save can be retried.
  const commandId = useRef(crypto.randomUUID());
  function open(next: "add" | "edit" | "delete") {
    setAction(next); setError(""); setNotice("");
    setTargetId(patient?.patient_id ?? ""); commandId.current = crypto.randomUUID();
  }

  function factsFromForm(data: FormData): PatientFacts | null {
    const facts: Record<string, number | boolean> = {};
    for (const [field, label, positive] of measurements) {
      const raw = data.get(field);
      if (raw == null || raw === "") { setError(`${label} is required.`); return null; }
      const value = Number(raw);
      if (!Number.isFinite(value) || value < 0 || (positive && value <= 0) ||
        (field === "ejection_fraction" && value > 100)) {
        setError(`${label} needs a finite ${positive ? "positive" : "nonnegative"} value.`);
        return null;
      }
      facts[field] = value;
    }
    for (const [field, label] of flags) {
      const value = data.get(field);
      if (value !== "0" && value !== "1") { setError(`${label} needs an explicit selection.`); return null; }
      facts[field] = value === "1";
    }
    return facts as PatientFacts;
  }
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    const data = new FormData(event.currentTarget);
    const facts = action === "delete" ? null : factsFromForm(data);
    if (action !== "delete" && facts == null) return;
    const reason = String(data.get("reason") ?? "").trim();
    if (action === "delete" && !reason) { setError("Enter a reason for deletion."); return; }
    setBusy(true); onBusy(true); setError("");
    try {
      const receipt = action === "add"
        ? await savePatient(facts as PatientFacts, commandId.current)
        : action === "edit"
          ? await updatePatient(targetId, facts as PatientFacts, commandId.current)
          : await deletePatient(targetId, reason, commandId.current);
      const verb = action === "add" ? "added and scored" : action === "edit" ? "updated" : "deleted";
      setNotice(`${receipt.patient_id} ${verb}. Dashboard refreshing.`);
      setAction(null);
      onChanged(action === "delete" ? undefined : receipt.patient_id);
    } catch (failure) {
      setError(patientError(failure));
      // Even a rejected command can reveal an outside revision change. Refresh
      // read models and end stale voice context while retaining entered fields.
      onChanged();
    } finally { setBusy(false); onBusy(false); }
  }
  return <div className="patient-actions">
    <div className="patient-action-buttons">
      <button className="btn btn-primary" disabled={!enabled || loading} onClick={() => open("add")}>Add patient</button>
      <button className="btn" disabled={!enabled || loading || !patient} onClick={() => open("edit")}>Edit patient</button>
      <button className="btn btn-danger" disabled={!enabled || loading || !patient} onClick={() => open("delete")}>Delete patient</button>
    </div>
    {!enabled && !loading && <small>Patient changes require the local API.</small>}
    {notice && <p role="status">{notice}</p>}
    {action && <Modal title={action === "add" ? "Add patient" : action === "edit" ? `Edit ${targetId}` : `Delete ${targetId}`} busy={busy} onCancel={() => setAction(null)}>
      <form onSubmit={submit} onChange={() => { commandId.current = crypto.randomUUID(); setError(""); }}>
        {action === "delete" ? <>
          <p>Remove {targetId} from the live cohort, predictions and call list? The audit history is retained.</p>
          <label>Reason for deletion<textarea name="reason" required maxLength={1000} disabled={busy} /></label>
        </> : <>
          <p>{action === "edit" ? "Change the recorded baseline measurements. The published models will rescore this patient." : "Enter the recorded baseline measurements. Saved patients use the published models; a points-only server uses rule scores."}</p>
          <fieldset disabled={busy} className="patient-form-grid">
            <legend>Baseline patient facts</legend>
            {measurements.map(([field, label]) => <label key={field}>
              {label}<input name={field} type="number" step="any" min="0"
                max={field === "ejection_fraction" ? 100 : undefined}
                defaultValue={action === "edit" ? patient?.facts[field] : undefined} required />
            </label>)}
            {flags.map(([field, label]) => <label key={field}>{label}
              <select name={field} defaultValue={action === "edit" ? (patient?.facts[field] ? "1" : "0") : ""} required>
                <option value="" disabled>Select</option>
                <option value="0">{field === "sex" ? "Female (0)" : "No"}</option>
                <option value="1">{field === "sex" ? "Male (1)" : "Yes"}</option>
              </select>
            </label>)}
          </fieldset>
        </>}
        {error && <p role="alert">{error}</p>}
        <div className="patient-dialog-buttons">
          <button type="button" disabled={busy} onClick={() => setAction(null)}>Cancel</button>
          <button type="submit" disabled={busy || loading}>
            {busy ? "Saving…" : action === "add" ? "Save patient" : action === "edit" ? "Save changes" : "Confirm deletion"}
          </button>
        </div>
      </form>
    </Modal>}
  </div>;
}
