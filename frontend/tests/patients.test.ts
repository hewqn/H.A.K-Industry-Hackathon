import { afterEach, beforeEach, expect, it, vi } from "vitest";

beforeEach(() => vi.resetModules());
afterEach(() => vi.unstubAllGlobals());

it("sends baseline facts with current revision and retries a lost response with the identical command", async () => {
  const writes: string[] = [];
  vi.stubGlobal("fetch", vi.fn(async (url: string, options?: RequestInit) => {
    if (url.endsWith("/cohorts/current")) return new Response(JSON.stringify({ workflow_revision: 12 }));
    writes.push(options!.body as string);
    if (writes.length === 1) throw new TypeError("Connection lost after commit");
    return new Response(JSON.stringify({ patient_id: "HF-0300", revision: 13, sync_status: "pending_sync" }));
  }));
  const { savePatient } = await import("../src/api/patients");
  const facts = { age: 41, ejection_fraction: 60, serum_creatinine: 0.9, serum_sodium: 135,
    platelets: 250000, creatinine_phosphokinase: 200, anaemia: false, diabetes: false,
    high_blood_pressure: false, smoking: false, sex: false };
  const receipt = await savePatient(facts, "stable-patient-command");
  expect(receipt.patient_id).toBe("HF-0300");
  expect(writes).toHaveLength(2);
  expect(writes[1]).toBe(writes[0]);
  expect(JSON.parse(writes[0])).toEqual({ ...facts, expected_revision: 12, command_id: "stable-patient-command" });
});

it("sends DELETE with a reason and surfaces conflicts without a second write", async () => {
  const writes: RequestInit[] = [];
  vi.stubGlobal("fetch", vi.fn(async (url: string, options?: RequestInit) => {
    if (url.endsWith("/cohorts/current")) return new Response(JSON.stringify({ workflow_revision: 4 }));
    writes.push(options!);
    return new Response(JSON.stringify({ code: "revision_conflict", message: "Stale patient facts" }), { status: 409 });
  }));
  const { deletePatient, patientError } = await import("../src/api/patients");
  try {
    await deletePatient("HF-0300", "Duplicate entry", "stable-delete-command");
    throw new Error("Expected rejection");
  } catch (error) {
    expect(patientError(error)).toContain("Refresh the dashboard");
  }
  expect(writes).toHaveLength(1);
  expect(writes[0].method).toBe("DELETE");
  expect(JSON.parse(writes[0].body as string)).toEqual({ reason: "Duplicate entry", command_id: "stable-delete-command", expected_revision: 4 });
});

it("keeps benchmark sample size fixed when the operational cohort changes", async () => {
  vi.stubGlobal("fetch", vi.fn(async (url: string) => new Response(JSON.stringify(
    url.endsWith("/models") ? { reports: { benchmark: { metrics: {
      oldest_first: { n: 299, captured_outcomes: 18 }, points_v1: { captured_outcomes: 21 }, points_heart3: { captured_outcomes: 19 },
    }, overlap_count: 22, decision: "reject_candidate" } } } : { accepted_count: 320, missing_rows: 0 },
  ))));
  const { loadCaseReport } = await import("../src/api/loadCaseReport");
  const report = await loadCaseReport();
  expect(report?.kept).toBe(299);
  expect(report?.weight2Deaths).toBe(21);
});
