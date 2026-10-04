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
import InterfaceIcon from "./components/InterfaceIcon";
import WorkspaceTabs, { type WorkspaceTab } from "./components/WorkspaceTabs";
import { FieldGuide, ProgramOverview } from "./components/ProjectGuide";
import "./App.css";

export default function App() {
  const [activeTab, setActiveTab] = useState<WorkspaceTab>("dashboard");
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

  useEffect(() => {
    const title = activeTab === "dashboard" ? "Patient review" : activeTab === "guide" ? "Field guide" : "About the program";
    document.title = `${title} · H.A.K`;
  }, [activeTab]);

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
      <a className="skip-link" href="#main-content">Skip to main content</a>
      <header className="app-header">
        <div className="header-inner">
          <div className="brand">
            <span className="brand-mark"><InterfaceIcon name="pulse" /></span>
            <div><span className="brand-name">H.A.K</span><span className="brand-description">Heart failure follow-up</span></div>
          </div>
          <div className="header-status">
            {admin && <span className="admin-badge">Admin</span>}
            <span className="prototype-tag">Research prototype</span>
            <span className={`connection-status ${rankingError ? "is-error" : source === "api" ? "is-connected" : "is-local"}`}>
              <span className="status-dot" />
              {rankingLoading ? "Refreshing data" : rankingError ? "Data unavailable" : source === "api" ? "API data" : "Local CSV preview"}
            </span>
            <button className="button-secondary logout-button" onClick={() => { logout(); setSignedIn(false); setAdmin(false); }}>Log out</button>
          </div>
        </div>
        <div className="navigation-inner"><WorkspaceTabs active={activeTab} onChange={setActiveTab} /></div>
      </header>

      <main id="main-content" className="main-content" tabIndex={-1}>
        {/* Keep the workspace mounted: educational tabs never reset patient,
            camera, form, ranking, transcript or provider-session state. */}
        <section id="panel-dashboard" role="tabpanel" tabIndex={0} aria-labelledby="tab-dashboard" hidden={activeTab !== "dashboard"}>
          <div className="page-heading">
            <div><p className="eyebrow">Follow-up workspace</p><h1>Patient review</h1>
              <p className="page-description">Prioritize follow-up. Inspect the measurements. Understand the evidence.</p>
            </div>
            <div className="cohort-summary" aria-label="Current list summary">
              <div><strong>{Math.min(patients.length, 25)}</strong><span>in the call list</span></div>
              <div><strong>{patients.length}</strong><span>{source === "api" ? "eligible records" : "preview records"}</span></div>
            </div>
          </div>

          <div className="patient-toolbar">
            <label className="patient-picker">Select patient
              <select aria-label="Select patient from cohort" value={selectedId ?? ""} disabled={rankingLoading}
                onChange={(event) => { setSelectedId(event.target.value); setFocusedOrgan(null); }}>
                {!selectedId && <option value="">No patients</option>}
                {patients.map((patient) => <option key={patient.patient_id} value={patient.patient_id}>
                  {patient.patient_id} · rank {patient.rank}{patient.rank > 25 ? " · outside Top 25" : ""}
                </option>)}
              </select>
            </label>
            <button className="button-secondary refresh-button" disabled={rankingLoading} onClick={() => refreshPatients()}>
              <InterfaceIcon name="refresh" />Refresh patients
            </button>
            {admin && (
              <PatientActions patient={selected} enabled={source === "api" && !rankingError} loading={rankingLoading}
                onBusy={setMutationBusy} onChanged={refreshPatients} />
            )}
          </div>

          {!rankingLoading && rankingError && <p role="alert" className="workspace-error">{rankingError}</p>}
          {/* Preserve the original colour controls even before a patient loads. */}
          {!selected && <section className="empty-visual-settings" aria-label="Visualization settings">
            <div><p className="eyebrow">Visualization settings</p><div className="view-toggle" role="group" aria-label="How organs are coloured">
              <button className={colorMode === "risk" ? "active" : ""} aria-pressed={colorMode === "risk"} onClick={() => setColorMode("risk")}>Risk Score</button>
              <button className={colorMode === "anatomy" ? "active" : ""} aria-pressed={colorMode === "anatomy"} onClick={() => setColorMode("anatomy")}>Tissue State</button>
            </div></div>
            <ColorLegend mode={colorMode} queueMode={queueMode} patient={selected} preview={preview} base={!applyColour.heart && !applyColour.kidney} />
          </section>}
          {selected ? <>
            <AnatomyView key={selected.patient_id} patient={selected} queueMode={queueMode} onQueueModeChange={setQueueMode} />
            {selected.rank > 25 && <p className="patient-queue-note">This patient is outside the current Top 25 (rank {selected.rank}).</p>}
            <div className="workspace" aria-busy={rankingLoading}>
              <div className="queue-column">
                <Top25Table patients={patients} selectedId={selected.patient_id} onSelect={setSelectedId} onPreview={setPreviewId} />
                {caseReport && <CaseReport report={caseReport} />}
              </div>
              <section className="anatomy-region" aria-label="Anatomical view">
                <div className="panel-heading"><div><p className="eyebrow">Patient visualization</p><h2>Anatomical view</h2></div><InterfaceIcon name="layers" /></div>
                <div className="view-toggle" role="group" aria-label="How organs are coloured">
                  <button className={colorMode === "risk" ? "active" : ""} aria-pressed={colorMode === "risk"} onClick={() => setColorMode("risk")}>Risk Score</button>
                  <button className={colorMode === "anatomy" ? "active" : ""} aria-pressed={colorMode === "anatomy"} onClick={() => setColorMode("anatomy")}>Tissue State</button>
                </div>
                <ColorLegend mode={colorMode} queueMode={queueMode} patient={selected} preview={preview} base={!applyColour.heart && !applyColour.kidney} />
                <div className="organ-viewer">
                  <AnatomyViewer organs={selected.organs} focusedOrgan={focusedOrgan} onOrganSelect={setFocusedOrgan}
                    colorMode={colorMode} organRisk={selected.organ_risk} applyColour={applyColour}
                    onApplyColourChange={(organ, on) => setApplyColour((current) => ({ ...current, [organ]: on }))} />
                </div>
                <p className="viewer-caption">Drag to rotate · Scroll to zoom · Select an organ to focus</p>
              </section>
              <div className="patient-detail-column">
                <ModelRiskPanel patient={selected} />
                <PatientRecord patient={selected} focusedOrgan={focusedOrgan} onOrganSelect={setFocusedOrgan} />
              </div>
              <div className="assistant-region">
                <VoicePanel key={`${rankingLoading ? "loading" : rankingContext?.snapshot_id ?? "local"}:${selectedId}:${queueMode}`}
                  context={rankingContext} patient={selected} patients={patients} loading={rankingLoading}
                  onSelectPatient={setSelectedId} onFocusOrgan={setFocusedOrgan} />
              </div>
            </div>
          </> : !rankingError && <div className="empty">
            <span className="empty-icon"><InterfaceIcon name="queue" /></span>
            <p>{rankingLoading ? "Loading the call list" : "No eligible patients. Add a patient to begin."}</p>
          </div>}
        </section>
        <section id="panel-guide" role="tabpanel" tabIndex={0} aria-labelledby="tab-guide" hidden={activeTab !== "guide"}><FieldGuide /></section>
        <section id="panel-about" role="tabpanel" tabIndex={0} aria-labelledby="tab-about" hidden={activeTab !== "about"}><ProgramOverview /></section>
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
