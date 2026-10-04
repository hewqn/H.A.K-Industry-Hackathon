import { ConversationProvider, useConversation, useRawConversation } from "@elevenlabs/react";
import { useLayoutEffect, useMemo, useRef, useState } from "react";
import type { FormEvent } from "react";
import { ApiError, post } from "../api/client";
import type { VoiceContext, VoiceSession, Patient as ApiPatient } from "../api/client";
import type { RankingContext } from "../api/loadRanking";
import type { OrganId, Patient } from "../types/patient";
import { createClientTools, readEvidence } from "../voice/clientTools";
import type { ActiveVoiceContext, ReadTool } from "../voice/clientTools";
import "./VoicePanel.css";

interface Props {
  context: RankingContext | null;
  patient: Patient | null;
  patients: Patient[];
  loading: boolean;
  onSelectPatient: (id: string) => void;
  onFocusOrgan: (id: OrganId) => void;
}

interface TranscriptLine { role: "user" | "assistant" | "evidence"; text: string }

// The provider lives in this small panel, leaving the existing 3D architecture
// untouched. App keys this component by patient/snapshot to end stale playback.
export default function VoicePanel(props: Props) {
  return <ConversationProvider><VoiceControls {...props} /></ConversationProvider>;
}

function localFacts(patient: Patient): string {
  return `${patient.patient_id}: recorded ejection fraction ${patient.facts.ejection_fraction}%, serum creatinine ${patient.facts.serum_creatinine} mg/dL, age ${patient.facts.age} years. Local preview score ${patient.score} (${patient.score_kind}); this is not a clinical risk probability.`;
}

function VoiceControls({ context, patient, patients, loading, onSelectPatient, onFocusOrgan }: Props) {
  const [lines, setLines] = useState<TranscriptLine[]>([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [starting, setStarting] = useState(false);
  const [textOnly, setTextOnly] = useState(false);
  const [muted, setMuted] = useState(false);
  const [quiet, setQuiet] = useState(false);
  const [message, setMessage] = useState("");
  const [notice, setNotice] = useState("");
  const alive = useRef(true);
  const epoch = useRef(0);
  const grant = useRef<VoiceContext | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const active = useRef<ActiveVoiceContext | null>(null);
  const rawConversation = useRawConversation();
  const playback = useRef(rawConversation);
  useLayoutEffect(() => {
    // Hold the latest instance for unmount cleanup without ending a session when
    // the SDK replaces its initial null instance with the connected conversation.
    playback.current = rawConversation;
  }, [rawConversation]);
  const available = !loading && context !== null;
  useLayoutEffect(() => {
    active.current = available && context ? { ...context, patient_id: patient?.patient_id ?? null, patient_ids: patients.map((item) => item.patient_id) } : null;
  }, [available, context, patient, patients]);

  const append = (role: TranscriptLine["role"], text: string) => {
    if (alive.current) setLines((previous) => [...previous.slice(-49), { role, text }]);
  };

  const options = useMemo(() => ({
    getContext: () => alive.current ? active.current : null,
    getGrant: () => alive.current ? grant.current : null,
    selectPatient: onSelectPatient,
    focusOrgan: onFocusOrgan,
    onBusy: (value: boolean) => { if (alive.current) setBusy(value); },
    onError: (value: string) => { if (alive.current) setError(value); },
  }), [onSelectPatient, onFocusOrgan]);
  // This factory only installs callbacks; refs are read when a tool runs.
  // oxlint-disable-next-line react/refs
  const tools = useMemo(() => createClientTools(options), [options]);

  const conversation = useConversation({
    // TextConversation rejects both audio controls. The SDK applies these
    // values only after a voice instance exists; never call them before start.
    micMuted: textOnly ? undefined : muted,
    volume: textOnly ? undefined : quiet ? 0 : 1,
    clientTools: tools,
    onMessage: ({ source, message: text }) => {
      if (grant.current) append(source === "user" ? "user" : "assistant", text);
    },
    onConnect: () => {
      if (!alive.current || !grant.current) return;
      setStarting(false);
      setNotice(textOnly ? "Text conversation connected." : "Voice connected. Microphone audio is sent to ElevenLabs.");
    },
    onDisconnect: () => {
      if (!alive.current) return;
      setStarting(false);
      grant.current = null;
      if (timer.current) clearTimeout(timer.current);
      timer.current = null;
    },
    onError: () => {
      if (!alive.current) return;
      setStarting(false);
      setError("Conversation failed. Check the private agent's permissions, text-mode override, and client-tool configuration. Factual shortcuts still work.");
    },
    onUnhandledClientToolCall: () => setError("The agent requested an unsupported tool. Check the seven client tools in ElevenLabs."),
  });
  const { endSession } = conversation;

  useLayoutEffect(() => {
    alive.current = true;
    return () => {
      // Synchronously silence old playback before the new patient's panel mounts.
      alive.current = false;
      epoch.current += 1;
      grant.current = null;
      if (timer.current) clearTimeout(timer.current);
      // StrictMode rehearses cleanup while idle, and text sessions have no audio.
      if (playback.current?.type === "voice") playback.current.setVolume({ volume: 0 });
      endSession();
    };
  }, [endSession]);

  function stop() {
    epoch.current += 1;
    grant.current = null;
    if (timer.current) clearTimeout(timer.current);
    timer.current = null;
    if (playback.current?.type === "voice") playback.current.setVolume({ volume: 0 });
    conversation.endSession();
    setStarting(false);
    setNotice("Conversation stopped. Reconnect to continue.");
  }

  async function start(asText: boolean) {
    const current = active.current;
    if (!current || starting || conversation.status === "connected") return;
    const attempt = ++epoch.current;
    setStarting(true);
    setTextOnly(asText);
    setError("");
    setMuted(false);
    setQuiet(false);
    setNotice(asText ? "Connecting text conversation…" : "Requesting microphone access…");
    try {
      if (!asText) {
        if (!navigator.mediaDevices?.getUserMedia) throw new Error("microphone_unavailable");
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        stream.getTracks().forEach((track) => track.stop());
      }
      if (!alive.current || epoch.current !== attempt) return;
      const session = await post<VoiceSession>("/voice/session", {
        snapshot_id: current.snapshot_id, patient_id: current.patient_id, text_only: asText,
      });
      if (!alive.current || epoch.current !== attempt) return;
      if (session.snapshot_id !== current.snapshot_id || session.patient_id !== current.patient_id) {
        throw new ApiError("voice_context_mismatch", "Session did not match the selected patient.", 409);
      }
      grant.current = session;
      // The SDK's hook starts asynchronously and reports failures through onError.
      // Explicit WebSocket transport matches the server's signed URL credential.
      conversation.startSession({
        signedUrl: session.signed_url,
        connectionType: "websocket",
        textOnly: asText,
        overrides: { conversation: { textOnly: asText } },
        dynamicVariables: {
          snapshot_id: session.snapshot_id, patient_id: session.patient_id ?? "",
          cohort_id: session.cohort_id, method_id: session.method_id,
        },
      });
      timer.current = setTimeout(() => {
        if (alive.current && epoch.current === attempt) {
          stop();
          setNotice("Session duration limit reached. Reconnect for a fresh session.");
        }
      }, Math.max(0, session.expires_at * 1000 - Date.now()));
    } catch (failure) {
      if (!alive.current || epoch.current !== attempt) return;
      setStarting(false);
      setError(failure instanceof ApiError ? failure.message : "Microphone or connection unavailable. Try Start text or use the factual shortcuts below.");
    }
  }

  async function shortcut(name: ReadTool) {
    setError("");
    const attempt = epoch.current;
    const current = active.current;
    if (!current) {
      if (!patient) return;
      const text = name === "get_queue"
        ? patients.slice(0, 3).map(localFacts).join("\n")
        : localFacts(patient) + (name === "explain_priority" ? ` ${patient.evidence.map((item) => item.description).join("; ")}.` : "");
      append("evidence", `Local preview — not synchronized with the backend. ${text}`);
      return;
    }
    setBusy(true);
    try {
      if (!grant.current || grant.current.expires_at * 1000 <= Date.now()) {
        const fresh = await post<VoiceContext>("/voice/context", { snapshot_id: current.snapshot_id, patient_id: current.patient_id });
        if (!alive.current || epoch.current !== attempt) return;
        grant.current = fresh;
      }
      const result = await readEvidence(options, name);
      if (!alive.current || epoch.current !== attempt) return;
      if (name === "get_queue") {
        append("evidence", result.briefing_text as string);
      } else if (name === "get_patient") {
        const read = result.patient as ApiPatient;
        append("evidence", `${read.summary.status === "template" ? "Factual template" : "Patient overview"}: ${read.summary.text}`);
      } else if (name === "explain_priority") {
        const read = result.patient as ApiPatient;
        append("evidence", `${read.patient_id}: ${read.score.value} ${read.score.label}, using ${read.method_id}. ${read.score.evidence.map((item) => `${item.predicate}${item.points !== null && item.points !== undefined ? ` (${item.points} points)` : ""}`).join("; ") || "No scoring predicates activated"}. ${read.override ? `Call order includes a clinician ${read.override.action}.` : ""} This is follow-up prioritization, not a clinical risk probability.`);
      }
    } catch (failure) {
      if (alive.current && epoch.current === attempt) setError(failure instanceof ApiError ? failure.message : "Evidence could not be retrieved. Use the visible patient measurements.");
    } finally {
      if (alive.current && epoch.current === attempt) setBusy(false);
    }
  }

  function send(event: FormEvent) {
    event.preventDefault();
    if (!message.trim() || conversation.status !== "connected") return;
    conversation.sendUserMessage(message.trim());
    // Text messages are not echoed by all agent event configurations.
    append("user", message.trim());
    setMessage("");
  }

  const connected = conversation.status === "connected";
  const connecting = starting || conversation.status === "connecting";
  const status = connecting ? "Connecting" : connected ? busy ? "Retrieving evidence" : textOnly ? "Text connected" : conversation.isSpeaking ? "Speaking" : muted ? "Microphone muted" : "Listening" : "Disconnected";

  return <section className="voice-panel" aria-label="Follow-up assistant">
    <div className="voice-heading"><h3>Follow-up assistant</h3><span role="status">{status}</span></div>
    <p className="voice-context">{patient?.patient_id ?? "No patient selected"} · {context && !loading ? "Current API snapshot" : "Local preview"}</p>
    <div className="voice-buttons">
      <button disabled={!available || connecting || connected} onClick={() => void start(false)}>Start voice</button>
      <button disabled={!available || connecting || connected} onClick={() => void start(true)}>Start text</button>
      <button disabled={!connected && !connecting} onClick={stop}>Stop</button>
      <button disabled={!connected || textOnly} aria-pressed={muted} onClick={() => setMuted(!muted)}>{muted ? "Unmute mic" : "Mute mic"}</button>
      <button disabled={!connected || textOnly} aria-pressed={quiet} onClick={() => setQuiet(!quiet)}>{quiet ? "Unmute audio" : "Mute audio"}</button>
      <button disabled={!available || connecting || connected} onClick={() => void start(textOnly)}>Reconnect</button>
    </div>
    {notice && <p className="voice-note">{notice}</p>}
    {!available && <p className="voice-note">Voice needs a matching API snapshot. Factual text shortcuts remain available.</p>}
    {error && <p role="alert" className="voice-error">{error}</p>}
    <div className="voice-buttons voice-shortcuts" aria-label="Factual text shortcuts">
      <button disabled={!patient || busy || loading} onClick={() => void shortcut("get_patient")}>Patient overview</button>
      <button disabled={!patient || busy || loading} onClick={() => void shortcut("explain_priority")}>Why prioritized?</button>
      <button disabled={!patients.length || busy || loading} onClick={() => void shortcut("get_queue")}>Brief queue</button>
    </div>
    <form className="voice-input" onSubmit={send}>
      <label htmlFor="assistant-message">Ask the assistant</label>
      <div><input id="assistant-message" value={message} maxLength={1000} disabled={!connected} placeholder="Start voice or text to ask a question" onChange={(event) => { setMessage(event.target.value); conversation.sendUserActivity(); }} /><button disabled={!connected || !message.trim()} type="submit">Send</button></div>
    </form>
    <details className="voice-transcript" open={lines.length > 0}>
      <summary>Transcript and factual summaries</summary>
      <div role="log" aria-live="polite" aria-label="Assistant transcript">
        {lines.length === 0 ? <p>No conversation yet. Changing patient or queue clears this transcript.</p> : lines.map((line, index) => <p key={index}><strong>{line.role === "user" ? "You" : line.role === "evidence" ? "Dashboard" : "Assistant"}: </strong>{line.text}</p>)}
      </div>
    </details>
  </section>;
}
