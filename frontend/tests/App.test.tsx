// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import App from "../src/App";
import type { LoadedRanking, RankingContext } from "../src/api/loadRanking";
import type { Patient } from "../src/types/patient";

const loaders = vi.hoisted(() => ({ ranking: vi.fn(), report: vi.fn() }));
vi.mock("../src/api/loadRanking", () => ({ loadRanking: loaders.ranking }));
vi.mock("../src/api/loadCaseReport", () => ({ loadCaseReport: loaders.report }));
// Test the dashboard wiring without requiring WebGL or a provider connection.
// VoicePanel's real SDK lifecycle is covered separately in VoicePanel.sdk.test.
vi.mock("../src/components/AnatomyViewer", () => ({ default: () => <div>3D viewer</div> }));
vi.mock("../src/components/VoicePanel", () => ({
  default: ({ context, loading, patient }: { context: RankingContext | null; loading: boolean; patient: Patient }) =>
    <section aria-label="Follow-up assistant">{loading ? "Changing queue" : context?.snapshot_id ?? "Local preview"} · {patient.patient_id}</section>,
}));

function ranking(id: string, method: "patient_risk" | "oldest_first" = "patient_risk"): LoadedRanking {
  const indicator = { state: "not_flagged", value: 40, unit: "%", label: "Recorded measurement" } as const;
  const patient: Patient = {
    patient_id: id, rank: 1, oldest_rank: 2, priority_band: "higher",
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
  expect(screen.getByText("UCI cohort via API · frozen ML queue")).toBeTruthy();
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
  expect(screen.getByText("UCI cohort via API · oldest first")).toBeTruthy();
});
