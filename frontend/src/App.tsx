import { useState, useEffect } from "react";
import AnatomyViewer from "./components/AnatomyViewer";
import AnatomyView, { PatientRecord } from "./components/AnatomyView";
import Top25Table from "./components/Top25Table";
import ColorLegend from "./components/ColorLegend";
import CaseReport from "./components/CaseReport";
import VoicePanel from "./components/VoicePanel";
import PatientActions from "./components/PatientActions";
import ModelRiskPanel from "./components/ModelRiskPanel";
import LoginPage from "./components/LoginPage";
import { isAdmin, isLoggedIn, logout, restoreSession } from "./auth";
import { loadRanking, type QueueMode, type RankingContext } from "./api/loadRanking";
import { loadCaseReport, type CaseReport as CaseReportData } from "./api/loadCaseReport";
import { loadDeathIndex } from "./utils/scoring";
import type { Patient, OrganId } from "./types/patient";
import { type ColorMode } from "./utils/organColors";
import "./App.css";

export default function App() {
  const [signedIn, setSignedIn] = useState(isLoggedIn());
  const [admin, setAdmin] = useState(isAdmin());
  const [deaths, setDeaths] = useState<Record<string, boolean>>({});
  const [patients, setPatients] = useState<Patient[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [focusedOrgan, setFocusedOrgan] = useState<OrganId | null>(null);
  const [colorMode, setColorMode] = useState<ColorMode>("risk");
  const [queueMode, setQueueMode] = useState<QueueMode>("model");
  const [caseReport, setCaseReport] = useState<CaseReportData | null>(null);
  const [previewId, setPreviewId] = useState<string | null>(null);
  const [applyColour, setApplyColour] = useState({ heart: true, kidney: true });
  const [source, setSource] = useState<"api" | "local">("local");
  const [method, setMethod] = useState("points_local");
  const [rankingContext, setRankingContext] = useState<RankingContext | null>(null);
  const [loadedMode, setLoadedMode] = useState<QueueMode | null>(null);
  const [rankingError, setRankingError] = useState("");
  const [dataVersion, setDataVersion] = useState(0);
  const [loadedVersion, setLoadedVersion] = useState(-1);
  const [mutationBusy, setMutationBusy] = useState(false);
  // Switching modes immediately disables and ends the old voice session, before
  // the next ranking arrives. A cancelled response cannot restore its context.
  const rankingLoading = mutationBusy || loadedMode !== queueMode || loadedVersion !== dataVersion;
  const [sessionReady, setSessionReady] = useState(!isLoggedIn());

  useEffect(() => {
    let cancelled = false;
    restoreSession().then((session) => {
      if (cancelled) return;
      setSignedIn(session.signedIn);
      setAdmin(session.admin);
      setSessionReady(true);
    });
    const lost = () => {
      logout();
      setSignedIn(false);
      setAdmin(false);
    };
    window.addEventListener("hak-auth-lost", lost);
    return () => {
      cancelled = true;
      window.removeEventListener("hak-auth-lost", lost);
    };
  }, []);

  useEffect(() => {
    let cancelled = false;

    loadRanking(queueMode, { forceFresh: dataVersion > 0, requireApi: dataVersion > 0 }).then(({ patients: ranked, source: nextSource, method: nextMethod, context }) => {
      if (cancelled) return;
      setPatients(
        ranked.map((patient) => ({
          ...patient,
          later_death: patient.patient_id in deaths ? deaths[patient.patient_id] : null,
        })),
      );
      setSource(nextSource);
      setMethod(nextMethod);
      setRankingContext(context);
      setLoadedMode(queueMode);
      setLoadedVersion(dataVersion);
      setRankingError("");
      setSelectedId((current) => {
        if (queueMode !== loadedMode) return ranked[0]?.patient_id ?? null;
        if (current && ranked.some((patient) => patient.patient_id === current)) {
          return current;
        }
        return ranked[0]?.patient_id ?? null;
      });
      setPreviewId(null);
    }).catch(() => {
      if (cancelled) return;
      setPatients([]);
      setRankingContext(null);
      setLoadedMode(queueMode);
      setLoadedVersion(dataVersion);
      setRankingError("Patient data could not be refreshed. Check the API and use Refresh patients.");
    });

    return () => {
      cancelled = true;
    };
  }, [queueMode, dataVersion, deaths]);

  useEffect(() => {
    let cancelled = false;
    loadDeathIndex().then((index) => {
      if (!cancelled) setDeaths(index);
    }).catch(() => {
      if (!cancelled) setDeaths({});
    });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    loadCaseReport().then((report) => {
      if (!cancelled) setCaseReport(report);
    });
    return () => {
      cancelled = true;
    };
  }, [dataVersion]);

  const selected = patients.find((p) => p.patient_id === selectedId) ?? null;
  const preview =
    patients.find((p) => p.patient_id === previewId && p.patient_id !== selectedId) ??
    null;

  function refreshPatients(patientId?: string) {
    if (patientId) setSelectedId(patientId);
    setFocusedOrgan(null);
    setPreviewId(null);
    setRankingContext(null);
    setDataVersion((version) => version + 1);
  }

  if (!sessionReady) {
    return <div className="empty">Checking session</div>;
  }

  if (!signedIn) {
    return <LoginPage onLoggedIn={() => { setSignedIn(true); setAdmin(isAdmin()); }} />;
  }

  return (
    <div className="app">
      <nav className="topnav">
        <div className="topnav-left">
          <span className="logo">H.A.K The Heart Failure</span>
          {admin && <span className="admin-badge">Admin</span>}
          <button className="btn logout-button" onClick={() => { logout(); setSignedIn(false); setAdmin(false); }}>Log out</button>
        </div>
        <div className="patient-toolbar">
          <label>Patient
            <select aria-label="Select patient from cohort" value={selectedId ?? ""} disabled={rankingLoading}
              onChange={(event) => { setSelectedId(event.target.value); setFocusedOrgan(null); }}>
              {!selectedId && <option value="">No patients</option>}
              {patients.map((patient) => <option key={patient.patient_id} value={patient.patient_id}>
                {patient.patient_id} · rank {patient.rank}{patient.rank > 25 ? " · outside Top 25" : ""}
              </option>)}
            </select>
          </label>
          <button className="btn" disabled={rankingLoading} onClick={() => refreshPatients()}>Refresh</button>
          {admin && (
            <PatientActions patient={selected} enabled={source === "api" && !rankingError} loading={rankingLoading}
              onBusy={setMutationBusy} onChanged={refreshPatients} />
          )}
        </div>
      </nav>

      <div className="legend-strip">
        <div className="view-toggle" role="group" aria-label="How organs are coloured">
          <button
            className={colorMode === "risk" ? "active" : ""}
            onClick={() => setColorMode("risk")}
          >
            Risk Score
          </button>
          <button
            className={colorMode === "anatomy" ? "active" : ""}
            onClick={() => setColorMode("anatomy")}
          >
            Tissue State
          </button>
        </div>
        <ColorLegend
          mode={colorMode}
          queueMode={queueMode}
          patient={selected}
          preview={preview}
          base={!applyColour.heart && !applyColour.kidney}
        />
      </div>

      <main className="main-content">
        {!rankingLoading && rankingError && <p role="alert">{rankingError}</p>}
        {selected ? (
          <div className="workspace">
            <div className="organ-viewer">
              <AnatomyViewer
                organs={selected.organs}
                focusedOrgan={focusedOrgan}
                onOrganSelect={setFocusedOrgan}
                colorMode={colorMode}
                organRisk={selected.organ_risk}
                applyColour={applyColour}
                onApplyColourChange={(organ, on) =>
                  setApplyColour((current) => ({ ...current, [organ]: on }))
                }
              />
            </div>
            <div className="workspace-side">
              <AnatomyView
                key={selected.patient_id}
                patient={selected}
                queueMode={queueMode}
                onQueueModeChange={setQueueMode}
              />
              <ModelRiskPanel patient={selected} />
              {selected.rank > 25 && <p className="patient-queue-note">This patient is outside the current Top 25 (rank {selected.rank}).</p>}
              {caseReport && <CaseReport report={caseReport} />}
              <VoicePanel
                key={`${rankingLoading ? "loading" : rankingContext?.snapshot_id ?? "local"}:${selectedId}:${queueMode}`}
                context={rankingContext}
                patient={selected}
                patients={patients}
                loading={rankingLoading}
                onSelectPatient={setSelectedId}
                onFocusOrgan={setFocusedOrgan}
              />
              <Top25Table
                patients={patients}
                selectedId={selected.patient_id}
                onSelect={setSelectedId}
                onPreview={setPreviewId}
              />
              <PatientRecord
                patient={selected}
                focusedOrgan={focusedOrgan}
                onOrganSelect={setFocusedOrgan}
              />
            </div>
          </div>
        ) : (
          !rankingError && <div className="empty">{rankingLoading ? "Loading the call list" : "No eligible patients. Add a patient to begin."}</div>
        )}
      </main>

      <footer className="app-footer">
        <span>
          3D models: Heart by{" "}
          <a
            href="https://sketchfab.com/3d-models/human-heart-bc51630b88b94f5fb6bdaef1488041c3"
            target="_blank"
            rel="noreferrer"
          >
            sammite
          </a>
          , Kidneys by{" "}
          <a
            href="https://sketchfab.com/3d-models/human-kidney-e1476ceb1e3b4412af5418eee9c5ed08"
            target="_blank"
            rel="noreferrer"
          >
            neshallads
          </a>{" "}
          on Sketchfab
        </span>
        <span>
          {source === "api"
            ? method === "patient_risk"
              ? "Patient cohort via API · frozen ML queue"
              : method === "oldest_first"
                ? "Patient cohort via API · oldest first"
              : method === "combined_w2"
                ? "Patient cohort via API · ML + heart weight 2"
                : method === "combined_w3"
                  ? "Patient cohort via API · ML + heart weight 3"
              : method === "points_v1"
                ? "Patient cohort via API · heart weight 2"
                : method === "points_heart3"
                  ? "Patient cohort via API · heart weight 3"
                  : "Patient cohort via API"
            : "UCI Heart Failure Clinical Records, CC BY 4.0"}
        </span>
      </footer>
    </div>
  );
}
