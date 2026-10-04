import { afterEach, describe, expect, it, vi } from "vitest";
import { createClientTools } from "../src/voice/clientTools";
import type { ActiveVoiceContext } from "../src/voice/clientTools";

afterEach(() => vi.unstubAllGlobals());

function setup() {
  let context: ActiveVoiceContext | null = { snapshot_id: "snapshot-one", cohort_id: "cohort", method_id: "points_v1", patient_id: "HF-0001", patient_ids: ["HF-0001", "HF-0002"] };
  const grant = { ...context, tool_token: "scoped-token", expires_at: Date.now() / 1000 + 300, max_duration_seconds: 300 };
  const select = vi.fn();
  const focus = vi.fn();
  const error = vi.fn();
  const tools = createClientTools({
    getContext: () => context, getGrant: () => grant,
    selectPatient: select, focusOrgan: focus, onBusy: vi.fn(), onError: error,
  });
  return { tools, select, focus, error, setContext: (value: ActiveVoiceContext | null) => { context = value; } };
}

describe("ElevenLabs client tool boundaries", () => {
  it("injects the trusted snapshot and scoped token instead of provider secrets", async () => {
    const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({ snapshot_id: "snapshot-one", cohort_id: "cohort", patient: { patient_id: "HF-0001" } }), { status: 200 }));
    vi.stubGlobal("fetch", fetch);
    const { tools } = setup();
    expect(JSON.parse(await tools.get_patient({})).ok).toBe(true);
    const [url, request] = fetch.mock.calls[0];
    expect(url).toBe("/api/v1/voice/tools/get_patient");
    expect(request.headers.Authorization).toBe("Bearer scoped-token");
    expect(JSON.parse(request.body)).toMatchObject({ snapshot_id: "snapshot-one", patient_id: "HF-0001", cohort_id: "cohort" });
  });

  it("rejects a different snapshot, unknown patient, and excessive queue limit before fetching", async () => {
    const fetch = vi.fn();
    vi.stubGlobal("fetch", fetch);
    const { tools } = setup();
    expect(JSON.parse(await tools.get_patient({ snapshot_id: "wrong" })).ok).toBe(false);
    expect(JSON.parse(await tools.get_patient({ patient_id: "HF-9999" })).ok).toBe(false);
    expect(JSON.parse(await tools.get_queue({ limit: 6 })).ok).toBe(false);
    expect(JSON.parse(await tools.get_patient({ sql: "SELECT *" })).ok).toBe(false);
    expect(fetch).not.toHaveBeenCalled();
  });

  it("rejects a mismatched evidence response", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ snapshot_id: "wrong", cohort_id: "cohort" }), { status: 200 })));
    const { tools } = setup();
    expect(JSON.parse(await tools.get_queue({}))).toMatchObject({ ok: false, code: "voice_context_mismatch" });
  });

  it("discard results if selection changes during retrieval", async () => {
    let resolve!: (response: Response) => void;
    vi.stubGlobal("fetch", vi.fn(() => new Promise<Response>((done) => { resolve = done; })));
    const { tools, setContext } = setup();
    const pending = tools.get_patient({});
    setContext(null);
    resolve(new Response(JSON.stringify({ patient: { patient_id: "HF-0001" } }), { status: 200 }));
    const value = JSON.parse(await pending);
    expect(value.ok).toBe(false);
    expect(value.code).toBe("stale_voice_context");
    expect(value.patient).toBeUndefined();
  });

  it("allows only known patients and the three supported organs", async () => {
    const { tools, select, focus } = setup();
    expect(JSON.parse(await tools.select_patient({ patient_id: "HF-0002" })).selected).toBe(true);
    expect(select).toHaveBeenCalledWith("HF-0002");
    expect(JSON.parse(await tools.focus_organ({ organ_id: "heart" })).focused).toBe(true);
    expect(focus).toHaveBeenCalledWith("heart");
    expect(JSON.parse(await tools.focus_organ({ organ_id: "brain" })).ok).toBe(false);
    expect(JSON.parse(await tools.select_patient({ patient_id: "HF-9999" })).ok).toBe(false);
    expect(focus).toHaveBeenCalledTimes(1);
    expect(select).toHaveBeenCalledTimes(1);
    expect(Object.keys(tools)).toHaveLength(7);
  });

  it("reports API failures visibly without inventing evidence", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ code: "voice_context_expired", message: "Reconnect." }), { status: 401 })));
    const { tools, error } = setup();
    expect(JSON.parse(await tools.explain_priority({}))).toMatchObject({ ok: false, code: "voice_context_expired" });
    expect(error).toHaveBeenCalledWith("Reconnect.");
  });
});
