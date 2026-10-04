import { api, ApiError } from "../api/client";
import type { VoiceContext } from "../api/client";
import type { RankingContext } from "../api/loadRanking";
import type { OrganId } from "../types/patient";

export interface ActiveVoiceContext extends RankingContext {
  patient_id: string | null;
  patient_ids: readonly string[];
}

export const READ_TOOLS = ["get_queue", "get_patient", "explain_priority", "get_comparison", "preview_heart_weight"] as const;
export type ReadTool = typeof READ_TOOLS[number];

interface ToolOptions {
  // Refs provide the latest UI selection, not a closure captured at session start.
  getContext: () => ActiveVoiceContext | null;
  getGrant: () => VoiceContext | null;
  selectPatient: (id: string) => void;
  focusOrgan: (id: OrganId) => void;
  onBusy: (busy: boolean) => void;
  onError: (message: string) => void;
}

type Parameters = Record<string, unknown>;
const ORGANS: readonly string[] = ["heart", "kidney_left", "kidney_right"];

function requireContext(options: ToolOptions, parameters: Parameters) {
  const context = options.getContext();
  const grant = options.getGrant();
  if (!context || !grant || context.snapshot_id !== grant.snapshot_id || grant.expires_at * 1000 <= Date.now()) {
    throw new ApiError("stale_voice_context", "Reconnect for the current queue.", 409);
  }
  // Parameters are untrusted. Omitted context is injected by the application;
  // supplied conflicting context is rejected rather than silently substituted.
  for (const field of ["snapshot_id", "cohort_id"] as const) {
    if (parameters[field] !== undefined && parameters[field] !== context[field]) {
      throw new ApiError("voice_context_mismatch", "The request refers to another queue.", 409);
    }
  }
  return { context, grant };
}

export async function readEvidence(options: ToolOptions, name: ReadTool, parameters: Parameters = {}) {
  if (Object.keys(parameters).some((key) => !["snapshot_id", "cohort_id", "patient_id", "limit", "report_id"].includes(key))) {
    throw new ApiError("voice_argument_denied", "Unsupported tool argument.", 422);
  }
  const { context, grant } = requireContext(options, parameters);
  const patientId = parameters.patient_id ?? context.patient_id;
  if (patientId !== null && (typeof patientId !== "string" || !context.patient_ids.includes(patientId))) {
    throw new ApiError("patient_not_in_snapshot", "Patient is not in the displayed snapshot.", 404);
  }
  const limit = parameters.limit ?? 3;
  if (!Number.isInteger(limit) || (limit as number) < 1 || (limit as number) > 5) {
    throw new ApiError("invalid_limit", "Queue briefings are limited to one to five patients.", 422);
  }
  if (parameters.report_id !== undefined && parameters.report_id !== "case-benchmark-v1") {
    throw new ApiError("report_not_available", "That report is not available.", 404);
  }
  const value = await api<Record<string, unknown>>(`/voice/tools/${name}`, {
    method: "POST",
    headers: { Authorization: `Bearer ${grant.tool_token}` },
    body: JSON.stringify({
      snapshot_id: context.snapshot_id, cohort_id: context.cohort_id,
      patient_id: patientId, limit, report_id: "case-benchmark-v1",
    }),
    signal: AbortSignal.timeout(12000),
  });
  const latest = options.getContext();
  if (!latest || latest.snapshot_id !== context.snapshot_id || latest.patient_id !== context.patient_id || options.getGrant()?.tool_token !== grant.tool_token) {
    throw new ApiError("stale_voice_context", "The selection changed while retrieving evidence.", 409);
  }
  if (value.snapshot_id !== context.snapshot_id || value.cohort_id !== context.cohort_id) {
    throw new ApiError("voice_context_mismatch", "Retrieved evidence belongs to another queue.", 409);
  }
  return value;
}

export function createClientTools(options: ToolOptions) {
  let pending = 0;
  // Tool results are JSON strings, as expected by ElevenLabs. Failures must not
  // look like successful patient facts, and must remain visible on the dashboard.
  const wrap = (action: (parameters: Parameters) => unknown | Promise<unknown>) => async (parameters: Parameters = {}) => {
    options.onBusy(++pending > 0);
    try {
      return JSON.stringify({ ok: true, ...await action(parameters) as object });
    } catch (error) {
      const message = error instanceof ApiError ? error.message : "Evidence is unavailable. Use the visible factual summary.";
      options.onError(message);
      return JSON.stringify({ ok: false, code: error instanceof ApiError ? error.code : "tool_failed", message });
    } finally {
      options.onBusy(--pending > 0);
    }
  };
  return {
    get_queue: wrap((parameters) => readEvidence(options, "get_queue", parameters)),
    get_patient: wrap((parameters) => readEvidence(options, "get_patient", parameters)),
    explain_priority: wrap((parameters) => readEvidence(options, "explain_priority", parameters)),
    get_comparison: wrap((parameters) => readEvidence(options, "get_comparison", parameters)),
    preview_heart_weight: wrap((parameters) => readEvidence(options, "preview_heart_weight", parameters)),
    select_patient: wrap((parameters) => {
      const { context } = requireContext(options, parameters);
      const id = parameters.patient_id;
      if (typeof id !== "string" || !context.patient_ids.includes(id)) {
        throw new ApiError("patient_not_in_snapshot", "Choose a patient in the displayed snapshot.", 404);
      }
      options.selectPatient(id);
      return { patient_id: id, snapshot_id: context.snapshot_id, selected: true };
    }),
    focus_organ: wrap((parameters) => {
      const { context } = requireContext(options, parameters);
      if (!context.patient_id) throw new ApiError("patient_context_required", "Select a patient first.", 422);
      const id = parameters.organ_id;
      if (typeof id !== "string" || !ORGANS.includes(id)) {
        throw new ApiError("organ_not_allowed", "Choose heart, kidney_left, or kidney_right.", 422);
      }
      options.focusOrgan(id as OrganId);
      return { patient_id: context.patient_id, snapshot_id: context.snapshot_id, organ_id: id, focused: true };
    }),
  };
}
