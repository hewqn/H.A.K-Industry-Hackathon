import { useState, useEffect } from "react";
import AnatomyViewer from "./components/AnatomyViewer";
import RiskView from "./components/RiskView";
import AnatomyView from "./components/AnatomyView";
import Top25Table from "./components/Top25Table";
import ColorLegend from "./components/ColorLegend";
import { parseCSV, rankPatients } from "./utils/scoring";
import type { Patient, OrganId } from "./types/patient";
import "./App.css";

type ViewMode = "anatomy" | "risk";

export default function App() {
  const [patients, setPatients] = useState<Patient[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [focusedOrgan, setFocusedOrgan] = useState<OrganId | null>(null);
  const [viewMode, setViewMode] = useState<ViewMode>("anatomy");
  const [heartWeight, setHeartWeight] = useState(2);
  const [previewId, setPreviewId] = useState<string | null>(null);

  useEffect(() => {
    fetch("/data/heart_failure_clinical_records.csv")
      .then((r) => r.text())
      .then((text) => {
        const rows = parseCSV(text);
        const ranked = rankPatients(rows, heartWeight, 25);
        setPatients(ranked);
        if (ranked.length > 0 && !selectedId) {
          setSelectedId(ranked[0].patient_id);
        }
      });
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
        <div className="topnav-right">
          <div className="view-toggle">
            <button
              className={viewMode === "anatomy" ? "active" : ""}
              onClick={() => setViewMode("anatomy")}
            >
              Anatomy
            </button>
            <button
              className={viewMode === "risk" ? "active" : ""}
              onClick={() => setViewMode("risk")}
            >
              Risk Assessment
            </button>
          </div>
        </div>
      </nav>

      <div className="legend-strip">
        <ColorLegend mode={viewMode} patient={selected} preview={preview} />
      </div>

      <main className="main-content">
        {selected ? (
          <div className="workspace">
            <div className="organ-viewer">
              <AnatomyViewer
                organs={selected.organs}
                focusedOrgan={focusedOrgan}
                onOrganSelect={setFocusedOrgan}
                colorMode={viewMode === "risk" ? "risk" : "anatomy"}
                organRisk={selected.organ_risk}
              />
            </div>
            <div className="workspace-side">
              <div className="workspace-views">
                <div
                  className={`view-layer ${viewMode === "anatomy" ? "active" : ""}`}
                >
                  <AnatomyView
                    key={selected.patient_id}
                    patient={selected}
                    totalPatients={patients.length}
                    focusedOrgan={focusedOrgan}
                    onOrganSelect={setFocusedOrgan}
                  />
                </div>
                <div
                  className={`view-layer ${viewMode === "risk" ? "active" : ""}`}
                >
                  <RiskView
                    patient={selected}
                    patients={patients}
                    heartWeight={heartWeight}
                    onHeartWeightChange={setHeartWeight}
                  />
                </div>
              </div>
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
        <span>UCI Heart Failure Clinical Records, CC BY 4.0</span>
      </footer>
    </div>
  );
}
