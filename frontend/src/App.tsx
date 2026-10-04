import { useState, useEffect } from "react";
import AnatomyViewer from "./components/AnatomyViewer";
import AnatomyView from "./components/AnatomyView";
import Top25Table from "./components/Top25Table";
import ColorLegend from "./components/ColorLegend";
import { loadRanking } from "./api/loadRanking";
import type { Patient, OrganId } from "./types/patient";
import type { ColorMode } from "./utils/organColors";
import "./App.css";

export default function App() {
  const [patients, setPatients] = useState<Patient[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [focusedOrgan, setFocusedOrgan] = useState<OrganId | null>(null);
  const [colorMode, setColorMode] = useState<ColorMode>("risk");
  const [heartWeight, setHeartWeight] = useState(2);
  const [previewId, setPreviewId] = useState<string | null>(null);
  const [applyColour, setApplyColour] = useState({ heart: true, kidney: true });
  const [source, setSource] = useState<"api" | "local">("local");

  useEffect(() => {
    let cancelled = false;

    loadRanking(heartWeight).then(({ patients: ranked, source: nextSource }) => {
      if (cancelled) return;
      setPatients(ranked);
      setSource(nextSource);
      setSelectedId((current) =>
        current && ranked.some((patient) => patient.patient_id === current)
          ? current
          : (ranked[0]?.patient_id ?? null),
      );
    });

    return () => {
      cancelled = true;
    };
  }, [heartWeight]);

  const selected = patients.find((p) => p.patient_id === selectedId) ?? null;
  const preview =
    patients.find((p) => p.patient_id === previewId && p.patient_id !== selectedId) ??
    null;

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
          patient={selected}
          preview={preview}
          base={!applyColour.heart && !applyColour.kidney}
        />
      </div>

      <main className="main-content">
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
                focusedOrgan={focusedOrgan}
                onOrganSelect={setFocusedOrgan}
                heartWeight={heartWeight}
                onHeartWeightChange={setHeartWeight}
              />
              <Top25Table
                patients={patients}
                selectedId={selected.patient_id}
                onSelect={setSelectedId}
                onPreview={setPreviewId}
              />
            </div>
          </div>
        ) : (
          <div className="empty">Select a patient to begin</div>
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
            ? "UCI cohort via API"
            : "UCI Heart Failure Clinical Records, CC BY 4.0"}
        </span>
      </footer>
    </div>
  );
}
