// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor, act } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import VoicePanel from "../src/components/VoicePanel";
import type { Patient } from "../src/types/patient";

const sdk = vi.hoisted(() => ({
  startSession: vi.fn(), endSession: vi.fn(), setVolume: vi.fn(), sendUserMessage: vi.fn(), sendUserActivity: vi.fn(),
  callbacks: {} as Record<string, (...args: never[]) => void>, status: "disconnected",
  rawConversation: null as { type: string; setVolume: (options: { volume: number }) => void } | null,
}));
vi.mock("@elevenlabs/react", () => ({
  ConversationProvider: ({ children }: { children: React.ReactNode }) => children,
  useRawConversation: () => sdk.rawConversation,
  useConversation: (callbacks: typeof sdk.callbacks) => {
    sdk.callbacks = callbacks;
    return { ...sdk, isSpeaking: false };
  },
}));

const patient = {
  patient_id: "HF-0001", score: 6, score_kind: "points", evidence: [],
  facts: { ejection_fraction: 20, serum_creatinine: 1.9, age: 75 },
} as unknown as Patient;
const context = { snapshot_id: "snapshot-one", cohort_id: "cohort", method_id: "points_v1" };
const props = { context, patient, patients: [patient], loading: false, onSelectPatient: vi.fn(), onFocusOrgan: vi.fn() };
const session = { ...context, patient_id: "HF-0001", signed_url: "wss://api.elevenlabs.io/example", tool_token: "scoped-token", expires_at: Date.now() / 1000 + 300, max_duration_seconds: 300, text_only: true };

afterEach(() => { cleanup(); vi.clearAllMocks(); vi.unstubAllGlobals(); sdk.status = "disconnected"; sdk.rawConversation = null; });

it("starts a private text session without accessing the microphone", async () => {
  const microphone = vi.fn();
  Object.defineProperty(navigator, "mediaDevices", { configurable: true, value: { getUserMedia: microphone } });
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify(session), { status: 200 })));
  render(<VoicePanel {...props} />);
  fireEvent.click(screen.getByRole("button", { name: "Start text" }));
  await waitFor(() => expect(sdk.startSession).toHaveBeenCalled());
  expect(sdk.startSession.mock.calls[0][0]).toMatchObject({ signedUrl: session.signed_url, connectionType: "websocket", textOnly: true, dynamicVariables: { patient_id: "HF-0001", snapshot_id: "snapshot-one" } });
  expect(microphone).not.toHaveBeenCalled();
});

it("offers factual text after microphone denial", async () => {
  Object.defineProperty(navigator, "mediaDevices", { configurable: true, value: { getUserMedia: vi.fn().mockRejectedValue(new DOMException("Denied", "NotAllowedError")) } });
  render(<VoicePanel {...props} />);
  fireEvent.click(screen.getByRole("button", { name: "Start voice" }));
  await waitFor(() => expect(screen.getByRole("alert").textContent).toContain("Try Start text"));
  expect((screen.getByRole("button", { name: "Patient overview" }) as HTMLButtonElement).disabled).toBe(false);
  expect(sdk.startSession).not.toHaveBeenCalled();
});

it("stops and silences playback when context is replaced", () => {
  sdk.status = "connected";
  sdk.rawConversation = { type: "voice", setVolume: sdk.setVolume };
  const view = render(<VoicePanel key="one" {...props} />);
  view.rerender(<VoicePanel key="two" {...props} patient={{ ...patient, patient_id: "HF-0002" }} />);
  expect(sdk.endSession).toHaveBeenCalled();
  expect(sdk.setVolume).toHaveBeenCalledWith({ volume: 0 });
});

it("does not start a session after Stop cancels a pending credential request", async () => {
  let resolve!: (response: Response) => void;
  vi.stubGlobal("fetch", vi.fn(() => new Promise<Response>((done) => { resolve = done; })));
  render(<VoicePanel {...props} />);
  fireEvent.click(screen.getByRole("button", { name: "Start text" }));
  fireEvent.click(screen.getByRole("button", { name: "Stop" }));
  await act(async () => resolve(new Response(JSON.stringify(session), { status: 200 })));
  expect(sdk.startSession).not.toHaveBeenCalled();
});

it("labels local fallback and keeps numerical factual shortcuts available", () => {
  render(<VoicePanel {...props} context={null} />);
  expect((screen.getByRole("button", { name: "Start voice" }) as HTMLButtonElement).disabled).toBe(true);
  fireEvent.click(screen.getByRole("button", { name: "Patient overview" }));
  const transcript = screen.getByRole("log").textContent;
  expect(transcript).toContain("Local preview — not synchronized");
  expect(transcript).toContain("20%");
  expect(transcript).toContain("1.9 mg/dL");
});
