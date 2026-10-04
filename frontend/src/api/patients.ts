import { api, ApiError } from "./client";
import type { Cohort } from "./client";
import type { components } from "./generated";
import { invalidateRanking, withRankingLock } from "./loadRanking";

export type PatientFacts = Omit<components["schemas"]["PatientCreateRequest"], "command_id" | "expected_revision">;
export type PatientReceipt = components["schemas"]["PatientMutationRead"];

/** Only baseline measurements enter ML. Labels and follow-up time are absent. */
export function savePatient(facts: PatientFacts, commandId: string): Promise<PatientReceipt> {
  return mutate("/patients", "POST", facts, commandId);
}

export function updatePatient(
  patientId: string,
  facts: PatientFacts,
  commandId: string,
): Promise<PatientReceipt> {
  return mutate(`/patients/${encodeURIComponent(patientId)}`, "PUT", facts, commandId);
}

export function deletePatient(patientId: string, reason: string, commandId: string): Promise<PatientReceipt> {
  return mutate(`/patients/${encodeURIComponent(patientId)}`, "DELETE", { reason }, commandId);
}

function mutate(path: string, method: string, facts: object, commandId: string) {
  return withRankingLock(async () => {
    const cohort = await api<Cohort>("/cohorts/current");
    const options = { method, body: JSON.stringify({
      ...facts, command_id: commandId, expected_revision: cohort.workflow_revision,
    }) };
    let receipt: PatientReceipt;
    try {
      receipt = await api<PatientReceipt>(path, options);
    } catch (error) {
      // One transport retry uses the identical command. A lost response must
      // never create two patients. Revision conflicts require a visible refresh.
      if (!(error instanceof TypeError)) throw error;
      receipt = await api<PatientReceipt>(path, options);
    }
    invalidateRanking();
    return receipt;
  });
}

export function patientError(error: unknown): string {
  if (error instanceof ApiError && error.status === 409)
    return "Patient data changed. Refresh the dashboard, then retry this action.";
  if (error instanceof ApiError && error.status === 422)
    return "Check all required measurements and use finite values within the indicated ranges.";
  if (error instanceof ApiError) return error.message;
  return "The API could not confirm this action. Retry without changing the form to reuse the same command.";
}
