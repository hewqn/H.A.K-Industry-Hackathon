import { useState, useEffect } from "react";
import AnatomyViewer from "./components/AnatomyViewer";
import AnatomyView, { PatientRecord } from "./components/AnatomyView";
import Top25Table from "./components/Top25Table";
import ColorLegend from "./components/ColorLegend";
import CaseReport from "./components/CaseReport";
import VoicePanel from "./components/VoicePanel";
import { loadRanking, type QueueMode, type RankingContext } from "./api/loadRanking";
import { loadCaseReport, type CaseReport as CaseReportData } from "./api/loadCaseReport";
import type { Patient, OrganId } from "./types/patient";
import {
  scoreScalePosition,
  type ColorMode,
} from "./utils/organColors";
import "./App.css";

export default function App() {
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
  // Switching modes immediately disables and ends the old voice session, before
  // the next ranking arrives. A cancelled response cannot restore its context.
  const rankingLoading = loadedMode !== queueMode;

  useEffect(() => {
    let cancelled = false;

    loadRanking(queueMode).then(({ patients: ranked, source: nextSource, method: nextMethod, context }) => {
      if (cancelled) return;
      setPatients(ranked);
      setSource(nextSource);
      setMethod(nextMethod);
      setRankingContext(context);
      setLoadedMode(queueMode);
      setRankingError("");
      setSelectedId((current) =>
        current && ranked.some((patient) => patient.patient_id === current)
          ? current
          : (ranked[0]?.patient_id ?? null),
      );
      setPreviewId(null);
    }).catch(() => {
      if (cancelled) return;
      setPatients([]);
      setRankingContext(null);
      setLoadedMode(queueMode);
      setRankingError("Patient data could not be loaded. Check the API or bundled CSV.");
    });

    return () => {
      cancelled = true;
    };
  }, [queueMode]);

  useEffect(() => {
    let cancelled = false;
    loadCaseReport().then((report) => {
      if (!cancelled) setCaseReport(report);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  const selected = patients.find((p) => p.patient_id === selectedId) ?? null;
  const preview =
    patients.find((p) => p.patient_id === previewId && p.patient_id !== selectedId) ??
    null;
  const rankingHeat =
    selected == null ||
    queueMode === "oldest" ||
    selected.score_kind === "age"
      ? undefined
      : (() => {
          const heat = scoreScalePosition(
            selected.score,
            selected.score_kind,
            typeof queueMode === "number" ? queueMode : 2,
          );
          return { heart: heat, kidney: heat };
        })();

  return (
    <div className="app">
      <nav className="topnav">
        <div className="topnav-left">
          <span className="logo">H.A.K The Heart Failure</span>
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
                organRisk={
                  colorMode === "risk" ? rankingHeat : selected.organ_risk
                }
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
          (rankingLoading || !rankingError) && <div className="empty">Loading the call list</div>
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
              ? "UCI cohort via API · frozen ML queue"
              : method === "oldest_first"
                ? "UCI cohort via API · oldest first"
              : method === "combined_w2"
                ? "UCI cohort via API · ML + heart weight 2"
                : method === "combined_w3"
                  ? "UCI cohort via API · ML + heart weight 3"
              : method === "points_v1"
                ? "UCI cohort via API · heart weight 2"
                : method === "points_heart3"
                  ? "UCI cohort via API · heart weight 3"
                  : "UCI cohort via API"
            : "UCI Heart Failure Clinical Records, CC BY 4.0"}
        </span>
      </footer>
    </div>
  );
}
