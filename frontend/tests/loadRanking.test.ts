import { afterEach, beforeEach, expect, it, vi } from "vitest";

// Simulate the real revisioned API contract. Auxiliary snapshot requests advance
// revisions just like backend commands, so stale displayed contexts fail tests.
function backend(mlReady = true) {
  let revision = 0;
  let generation = 1;
  const writes: string[] = [];
  const snapshots = new Map<string, ReturnType<typeof snapshot>>();
  function snapshot(method: string, id: string, version = revision) {
    const rows = ["HF-0001", "HF-0002"].map((patient_id, index) => ({
      patient_id, call_rank: index + 1, model_rank: index + 1,
      priority_band: "higher", workflow_state: "pending",
      score: {
        value: method === "oldest_first" ? 80 - index : method.startsWith("points") ? 6 - index : 0.8 - index / 10,
        kind: method.startsWith("points") ? "points" : "model_output", evidence: [],
      },
      facts: {
        age: 80 - index, anaemia: true, diabetes: false, high_blood_pressure: false,
        ejection_fraction: 30, serum_creatinine: 1.7, serum_sodium: 135,
        creatinine_phosphokinase: 200, platelets: 250000, sex: 1, smoking: false,
      },
    }));
    return { snapshot_id: id, cohort_id: "cohort", workflow_revision: version, method_id: method, rows, queue: rows };
  }
  const defaultMethod = mlReady ? "patient_risk" : "points_v1";
  snapshots.set("boot-1", snapshot(defaultMethod, "boot-1", 0));
  const fetch = vi.fn(async (url: string | URL | Request, options?: RequestInit) => {
    const path = String(url);
    let response: unknown;
    if (path.endsWith("/health")) {
      response = { voice: "configured", ml: mlReady ? "frozen_cache_ready" : "not_published" };
    } else if (path.endsWith("/cohorts/current")) {
      response = { cohort_id: "cohort", workflow_revision: revision, current_snapshot_id: `boot-${generation}` };
    } else if (path.endsWith("/ranking-snapshots") && options?.method === "POST") {
      const body = JSON.parse(options.body as string);
      if (body.expected_revision !== revision) {
        return new Response(JSON.stringify({ code: "revision_conflict", message: "Stale revision" }), { status: 409 });
      }
      writes.push(body.method_id);
      const created = snapshot(body.method_id, `snapshot-${++revision}`);
      snapshots.set(created.snapshot_id, created);
      response = { snapshot: created, revision };
    } else if (path.includes("/ranking-snapshots/")) {
      response = snapshots.get(path.split("/").at(-1)!);
      if (!response) return new Response("{}", { status: 404 });
    } else {
      throw new Error(`Unexpected request: ${path}`);
    }
    return new Response(JSON.stringify(response), { status: 200 });
  });
  return {
    fetch, writes, snapshots, revision: () => revision,
    externalChange: () => { revision++; },
    restart: () => {
      revision = 0;
      generation++;
      snapshots.clear();
      snapshots.set(`boot-${generation}`, snapshot(defaultMethod, `boot-${generation}`, 0));
    },
  };
}

beforeEach(() => vi.resetModules());
afterEach(() => vi.unstubAllGlobals());

it("loads independent organ scores and obtains the displayed ML snapshot after auxiliary writes", async () => {
  const server = backend();
  vi.stubGlobal("fetch", server.fetch);
  const { loadRanking } = await import("../src/api/loadRanking");
  const result = await loadRanking("model");
  expect(result.source).toBe("api");
  expect(result.method).toBe("patient_risk");
  expect(result.context?.method_id).toBe(result.method);
  expect(server.writes).toEqual(["heart_risk", "kidney_risk", "oldest_first", "patient_risk"]);
  const displayed = server.snapshots.get(result.context!.snapshot_id)!;
  expect(displayed.workflow_revision).toBe(server.revision());
  expect(result.patients.map((patient) => patient.patient_id)).toEqual(displayed.queue.map((row) => row.patient_id));
  expect(result.patients[0].organ_risk).toEqual({ heart: 0.8, kidney: 0.8 });
});

it("keeps browser-combined ordering separate from backend voice context", async () => {
  const server = backend();
  vi.stubGlobal("fetch", server.fetch);
  const { loadRanking } = await import("../src/api/loadRanking");
  for (const weight of [2, 3] as const) {
    const result = await loadRanking(weight);
    expect(result.method).toBe(`combined_w${weight}`);
    expect(result.source).toBe("api");
    expect(result.patients[0].score_kind).toBe("combined");
    expect(result.patients[0].model_rank).toBe(1);
    expect(result.context).toBeNull();
  }
});

it("retains points and oldest snapshots when ML is unavailable", async () => {
  const server = backend(false);
  vi.stubGlobal("fetch", server.fetch);
  const { loadRanking } = await import("../src/api/loadRanking");
  for (const [mode, method] of [["model", "points_v1"], [3, "points_heart3"], ["oldest", "oldest_first"]] as const) {
    const result = await loadRanking(mode);
    expect(result.method).toBe(method);
    expect(result.context?.method_id).toBe(method);
    expect(server.snapshots.get(result.context!.snapshot_id)!.workflow_revision).toBe(server.revision());
    expect(result.patients[0].score_kind).toBe(mode === "oldest" ? "age" : "points");
  }
});

it("deduplicates startup loads and refreshes caches after external changes and restarts", async () => {
  const server = backend();
  vi.stubGlobal("fetch", server.fetch);
  const { loadRanking } = await import("../src/api/loadRanking");
  const pending = loadRanking("model");
  expect(loadRanking("model")).toBe(pending);
  const first = await pending;
  const cached = await loadRanking("model");
  expect(cached.context).toEqual(first.context);
  expect(server.writes).toHaveLength(4);
  server.externalChange();
  const refreshed = await loadRanking("model");
  expect(refreshed.context?.snapshot_id).not.toBe(first.context?.snapshot_id);
  expect(server.snapshots.get(refreshed.context!.snapshot_id)!.workflow_revision).toBe(server.revision());
  server.restart();
  const restarted = await loadRanking("oldest");
  expect(restarted.source).toBe("api");
  expect(restarted.method).toBe("oldest_first");
  expect(server.snapshots.get(restarted.context!.snapshot_id)!.workflow_revision).toBe(server.revision());
});

it("serializes rapid mode switches without revision conflicts", async () => {
  const server = backend();
  vi.stubGlobal("fetch", server.fetch);
  const { loadRanking } = await import("../src/api/loadRanking");
  const [model, oldest] = await Promise.all([loadRanking("model"), loadRanking("oldest")]);
  expect(model.source).toBe("api");
  expect(oldest.source).toBe("api");
  expect(oldest.context?.method_id).toBe("oldest_first");
  expect(server.snapshots.get(oldest.context!.snapshot_id)!.workflow_revision).toBe(server.revision());
});

it("uses a bounded oldest-first local list when the API is unavailable", async () => {
  const headers = "age,anaemia,creatinine_phosphokinase,diabetes,ejection_fraction,high_blood_pressure,platelets,serum_creatinine,serum_sodium,sex,smoking,time,DEATH_EVENT";
  const rows = Array.from({ length: 30 }, (_, index) => `${40 + index},0,200,0,50,0,250000,1,135,1,0,10,0`);
  vi.stubGlobal("fetch", vi.fn(async (url: string) => {
    if (!url.startsWith("/data/")) throw new Error("API offline");
    return new Response([headers, ...rows].join("\n"));
  }));
  const { loadRanking } = await import("../src/api/loadRanking");
  const result = await loadRanking("oldest");
  expect(result.source).toBe("local");
  expect(result.context).toBeNull();
  expect(result.method).toBe("oldest_local");
  expect(result.patients).toHaveLength(25);
  expect(result.patients[0].facts.age).toBe(69);
  expect(result.patients[0].score_kind).toBe("age");
  expect(result.patients.at(-1)!.facts.age).toBe(45);
});
