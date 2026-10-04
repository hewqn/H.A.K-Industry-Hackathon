// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import App from "../src/App";
import type { LoadedRanking, RankingContext } from "../src/api/loadRanking";
import type { Patient } from "../src/types/patient";
import { riskEnvelope } from "./riskFixtures";

const loaders = vi.hoisted(() => ({ ranking: vi.fn(), report: vi.fn(), save: vi.fn(), remove: vi.fn(), viewer: vi.fn() }));
vi.mock("../src/api/loadRanking", () => ({ loadRanking: loaders.ranking }));
vi.mock("../src/api/patients", () => ({ savePatient: loaders.save, deletePatient: loaders.remove, patientError: () => "Save failed" }));
vi.mock("../src/api/loadCaseReport", () => ({ loadCaseReport: loaders.report }));
// Test the dashboard wiring without requiring WebGL or a provider connection.
// VoicePanel's real SDK lifecycle is covered separately in VoicePanel.sdk.test.
vi.mock("../src/components/AnatomyViewer", () => ({ default: (props: unknown) => { loaders.viewer(props); return <div>3D viewer</div>; } }));
vi.mock("../src/components/VoicePanel", () => ({
  default: ({ context, loading, patient }: { context: RankingContext | null; loading: boolean; patient: Patient }) =>
    <section aria-label="Follow-up assistant">{loading ? "Changing queue" : context?.snapshot_id ?? "Local preview"} · {patient.patient_id}</section>,
}));

function ranking(id: string, method: "patient_risk" | "oldest_first" = "patient_risk"): LoadedRanking {
  const indicator = { state: "not_flagged", value: 40, unit: "%", label: "Recorded measurement" } as const;
  const patient: Patient = {
    patient_id: id, rank: 1, oldest_rank: 2, priority_band: "higher",
    model_risks: riskEnvelope(), organ_risk: { heart: 0.2, kidney: 0.8 },
    score: 0.7, score_kind: method === "oldest_first" ? "age" : "model_output",
    facts: { age: 75, ejection_fraction: 40, serum_creatinine: 1, anaemia: false,
      diabetes: false, high_blood_pressure: false, creatinine_phosphokinase: 200,
      platelets: 250000, serum_sodium: 135, sex: 1, smoking: false },
    organs: { heart: indicator, kidney_left: indicator, kidney_right: indicator },
    evidence: [], workflow_state: "pending",
  };
  return {
    patients: [patient], source: "api", method,
    context: { snapshot_id: `snapshot-${id}`, cohort_id: "cohort", method_id: method },
  };
}

afterEach(() => { cleanup(); vi.resetAllMocks(); });

it("keeps the development case report, patient record, queue controls, and voice panel together", async () => {
  loaders.ranking.mockResolvedValue(ranking("HF-0001"));
  loaders.report.mockResolvedValue({ kept: 299, dropped: 0, oldestDeaths: 18, weight2Deaths: 21, weight3Deaths: 19, overlap: 22 });
  render(<App />);
  await waitFor(() => expect(screen.getByRole("region", { name: "Follow-up assistant" }).textContent).toContain("snapshot-HF-0001"));
  expect(screen.getByRole("region", { name: "Case result" }).textContent).toContain("299 records");
  expect(screen.getByRole("group", { name: "Call list mode" })).toBeTruthy();
  expect(screen.getByText("250,000")).toBeTruthy();
  expect(screen.getByText("3D viewer")).toBeTruthy();
  expect(screen.getByText("Patient cohort via API · frozen ML queue")).toBeTruthy();
});

it("disables stale voice context while switching modes and ignores an older ranking response", async () => {
  let resolveWeight!: (value: LoadedRanking) => void;
  loaders.ranking.mockImplementation((mode) => {
    if (mode === 3) return new Promise<LoadedRanking>((resolve) => { resolveWeight = resolve; });
    return Promise.resolve(ranking(mode === "oldest" ? "HF-0002" : "HF-0001", mode === "oldest" ? "oldest_first" : "patient_risk"));
  });
  loaders.report.mockResolvedValue(null);
  render(<App />);
  await waitFor(() => expect(screen.getByRole("region", { name: "Follow-up assistant" }).textContent).toContain("snapshot-HF-0001"));
  fireEvent.click(screen.getByRole("button", { name: "Heart weight 3" }));
  expect(screen.getByRole("region", { name: "Follow-up assistant" }).textContent).toContain("Changing queue");
  fireEvent.click(screen.getByRole("button", { name: "Oldest" }));
  await waitFor(() => expect(screen.getByRole("region", { name: "Follow-up assistant" }).textContent).toContain("snapshot-HF-0002"));
  await act(async () => resolveWeight(ranking("HF-0003")));
  expect(screen.getByRole("region", { name: "Follow-up assistant" }).textContent).toContain("snapshot-HF-0002");
  expect(screen.getByText("Patient cohort via API · oldest first")).toBeTruthy();
});

// JSDOM omits the browser's modal/focus implementation; exercise the real form.
Object.defineProperty(HTMLDialogElement.prototype, "showModal", { configurable: true, value: function () { this.setAttribute("open", ""); } });

function fillPatientForm() {
  const values = [
    ["Age (years)", "41"], ["Ejection fraction (%)", "60"],
    ["Serum creatinine (mg/dL)", "0.9"], ["Serum sodium (mEq/L)", "135"],
    ["Platelets (platelets/µL)", "250000"], ["Creatinine phosphokinase (mcg/L)", "200"],
  ];
  for (const [label, value] of values) fireEvent.change(screen.getByLabelText(label), { target: { value } });
  for (const label of ["Anaemia", "Diabetes", "High blood pressure", "Smoking", "Recorded sex"])
    fireEvent.change(screen.getByLabelText(label), { target: { value: "0" } });
}

it("uses independent heart and kidney scores in every queue mode", async () => {
  loaders.ranking.mockResolvedValue(ranking("HF-0001"));
  loaders.report.mockResolvedValue(null);
  render(<App />);
  await screen.findByRole("region", { name: "ML outputs" });
  expect(loaders.viewer.mock.lastCall?.[0].organRisk).toEqual({ heart: 0.2, kidney: 0.8 });
  expect(screen.getByText("Heart ML")).toBeTruthy();
  expect(screen.getByText("Kidney ML")).toBeTruthy();
  for (const label of ["Heart weight 3", "Oldest"]) {
    fireEvent.click(screen.getByRole("button", { name: label }));
    await waitFor(() => expect(screen.getByRole("region", { name: "Follow-up assistant" }).textContent).not.toContain("Changing queue"));
    expect(loaders.viewer.mock.lastCall?.[0].organRisk).toEqual({ heart: 0.2, kidney: 0.8 });
  }
});

it("submits only baseline facts, ends stale voice context, and selects a new patient outside Top 25", async () => {
  let resolveSave!: (value: { patient_id: string }) => void;
  const initial = ranking("HF-0001");
  const added = ranking("HF-0300");
  added.patients[0].rank = 30;
  loaders.ranking.mockResolvedValueOnce(initial).mockResolvedValue({ ...added, patients: [...initial.patients, ...added.patients] });
  loaders.report.mockResolvedValue(null);
  loaders.save.mockImplementation(() => new Promise((resolve) => { resolveSave = resolve; }));
  render(<App />);
  await screen.findByRole("region", { name: "ML outputs" });
  fireEvent.click(screen.getByRole("button", { name: "Add patient" }));
  fillPatientForm();
  fireEvent.click(screen.getByRole("button", { name: "Save patient" }));
  expect(screen.getByRole("region", { name: "Follow-up assistant" }).textContent).toContain("Changing queue");
  expect(loaders.save).toHaveBeenCalledWith({ age: 41, ejection_fraction: 60,
    serum_creatinine: 0.9, serum_sodium: 135, platelets: 250000, creatinine_phosphokinase: 200,
    anaemia: false, diabetes: false, high_blood_pressure: false, smoking: false, sex: false }, expect.any(String));
  await act(async () => resolveSave({ patient_id: "HF-0300" }));
  await waitFor(() => expect(screen.getByRole("region", { name: "Follow-up assistant" }).textContent).toContain("HF-0300"));
  expect(screen.getByText("This patient is outside the current Top 25 (rank 30).")).toBeTruthy();
  expect(loaders.ranking).toHaveBeenLastCalledWith("model", { forceFresh: true, requireApi: true });
  expect(screen.queryByRole("dialog")).toBeNull();
});

it("requires deletion confirmation and refreshes selection after deletion", async () => {
  loaders.ranking.mockResolvedValueOnce(ranking("HF-0001")).mockResolvedValue(ranking("HF-0002"));
  loaders.report.mockResolvedValue(null);
  loaders.remove.mockResolvedValue({ patient_id: "HF-0001" });
  render(<App />);
  await screen.findByRole("region", { name: "ML outputs" });
  fireEvent.click(screen.getByRole("button", { name: "Delete patient" }));
  fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
  expect(loaders.remove).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "Delete patient" }));
  fireEvent.change(screen.getByLabelText("Reason for deletion"), { target: { value: "Duplicate demo entry" } });
  fireEvent.click(screen.getByRole("button", { name: "Confirm deletion" }));
  await waitFor(() => expect(screen.getByRole("region", { name: "Follow-up assistant" }).textContent).toContain("HF-0002"));
  expect(loaders.remove).toHaveBeenCalledWith("HF-0001", "Duplicate demo entry", expect.any(String));
});

it("retains entered values and shows failed saves without removing a patient", async () => {
  loaders.ranking.mockResolvedValue(ranking("HF-0001"));
  loaders.report.mockResolvedValue(null);
  loaders.save.mockRejectedValue(new Error("Inference failed"));
  render(<App />);
  await screen.findByRole("region", { name: "ML outputs" });
  fireEvent.click(screen.getByRole("button", { name: "Add patient" }));
  fillPatientForm();
  fireEvent.click(screen.getByRole("button", { name: "Save patient" }));
  await screen.findByRole("alert");
  expect(screen.getByRole("alert").textContent).toBe("Save failed");
  expect((screen.getByLabelText("Age (years)") as HTMLInputElement).value).toBe("41");
  expect(screen.getByRole("dialog", { name: "Add patient" })).toBeTruthy();
  expect(screen.getByRole("region", { name: "Follow-up assistant" }).textContent).toContain("HF-0001");
});

it("allows adding to an empty API cohort and disables CRUD in local CSV preview", async () => {
  loaders.ranking.mockResolvedValue({ ...ranking("HF-0001"), patients: [] });
  loaders.report.mockResolvedValue(null);
  const view = render(<App />);
  await screen.findByText("No eligible patients. Add a patient to begin.");
  expect((screen.getByRole("button", { name: "Add patient" }) as HTMLButtonElement).disabled).toBe(false);
  expect((screen.getByRole("button", { name: "Delete patient" }) as HTMLButtonElement).disabled).toBe(true);
  view.unmount();
  loaders.ranking.mockResolvedValue({ ...ranking("HF-0001"), source: "local", context: null });
  render(<App />);
  await screen.findByText("Patient changes require the local API.");
  expect((screen.getByRole("button", { name: "Add patient" }) as HTMLButtonElement).disabled).toBe(true);
});
