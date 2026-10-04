// @vitest-environment jsdom
import { StrictMode } from "react";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { Conversation, TextConversation } from "@elevenlabs/react";
import { afterEach, expect, it, vi } from "vitest";
import VoicePanel from "../src/components/VoicePanel";
import type { Patient } from "../src/types/patient";

// Keep the real ElevenLabs provider and hooks: mocks cannot catch SDK controls
// that throw before a conversation exists. Rendering must never contact a provider.
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });

it("mounts and replaces an idle panel in StrictMode without calling session-only controls", () => {
  const fetch = vi.fn();
  vi.stubGlobal("fetch", fetch);
  const patient = { patient_id: "HF-0001" } as Patient;
  const props = {
    context: { snapshot_id: "snapshot-one", cohort_id: "cohort", method_id: "points_v1" },
    patient, patients: [patient], loading: false,
    onSelectPatient: vi.fn(), onFocusOrgan: vi.fn(),
  };
  const view = render(<StrictMode><VoicePanel key="one" {...props} /></StrictMode>);
  expect((screen.getByRole("button", { name: "Start text" }) as HTMLButtonElement).disabled).toBe(false);
  view.rerender(<StrictMode><VoicePanel key="two" {...props} /></StrictMode>);
  view.unmount();
  expect(fetch).not.toHaveBeenCalled();
});

it("connects and stops text with the real hooks without touching audio controls", async () => {
  const context = { snapshot_id: "snapshot-one", cohort_id: "cohort", method_id: "points_v1" };
  const patient = { patient_id: "HF-0001" } as Patient;
  const session = {
    ...context, patient_id: patient.patient_id, signed_url: "wss://api.elevenlabs.io/example",
    tool_token: "scoped-token", expires_at: Date.now() / 1000 + 300,
    max_duration_seconds: 300, text_only: true,
  };
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify(session), { status: 200 })));
  // Mock only connection establishment. Preserve the SDK's real text audio
  // methods, which throw if volume or microphone controls are used on text.
  const text = Object.create(TextConversation.prototype) as TextConversation;
  const volume = vi.spyOn(text, "setVolume");
  const microphone = vi.spyOn(text, "setMicMuted");
  vi.spyOn(Conversation, "startSession").mockImplementation(async (options) => {
    text.endSession = vi.fn(async () => {
      options.onStatusChange?.({ status: "disconnecting" });
      options.onDisconnect?.({ reason: "user" });
    });
    options.onConversationCreated?.(text);
    options.onStatusChange?.({ status: "connected" });
    options.onConnect?.({ conversationId: "local-test" });
    return text;
  });
  const props = { context, patient, patients: [patient], loading: false, onSelectPatient: vi.fn(), onFocusOrgan: vi.fn() };
  const view = render(<StrictMode><VoicePanel {...props} /></StrictMode>);
  fireEvent.click(screen.getByRole("button", { name: "Start text" }));
  await waitFor(() => expect(screen.getByRole("status").textContent).toBe("Text connected"));
  fireEvent.click(screen.getByRole("button", { name: "Stop" }));
  await waitFor(() => expect(screen.getByRole("status").textContent).toBe("Disconnected"));
  view.unmount();
  expect(volume).not.toHaveBeenCalled();
  expect(microphone).not.toHaveBeenCalled();
  expect(text.endSession).toHaveBeenCalled();
});
