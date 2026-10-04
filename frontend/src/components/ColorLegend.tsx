import type { QueueMode } from "../api/loadRanking";
import type { Patient } from "../types/patient";
import type { ColorMode } from "../utils/organColors";
import {
  heartScalePosition,
  kidneyScalePosition,
  pointsCeiling,
  scoreScalePosition,
} from "../utils/organColors";

interface ColorLegendProps {
  mode: ColorMode;
  queueMode: QueueMode;
  patient?: Patient | null;
  preview?: Patient | null;
  base?: boolean;
}

function Scale({
  swatch,
  position,
  label,
  previewPosition,
  previewLabel,
}: {
  swatch: string;
  position: number | null;
  label: string | null;
  previewPosition: number | null;
  previewLabel: string | null;
}) {
  return (
    <div className="legend-track">
      <div className={`legend-swatch ${swatch}`} />
      {previewPosition !== null && previewLabel && (
        <span
          className="legend-pin preview"
          style={{ left: `${previewPosition * 100}%` }}
        >
          <span className="legend-pin-label">{previewLabel}</span>
          <span className="legend-pin-dot" />
        </span>
      )}
      {position !== null && label && (
        <span className="legend-pin" style={{ left: `${position * 100}%` }}>
          <span className="legend-pin-label">{label}</span>
          <span className="legend-pin-dot" />
        </span>
      )}
    </div>
  );
}

function heartWeightOf(queueMode: QueueMode): number {
  return typeof queueMode === "number" ? queueMode : 2;
}

function scoreLabel(patient: Patient): string | null {
  if (patient.score_kind === "points") return String(patient.score);
  if (patient.score_kind === "model_output") return patient.score.toFixed(3);
  return null;
}

function ScoreScale({
  queueMode,
  patient,
  compared,
}: {
  queueMode: QueueMode;
  patient?: Patient | null;
  compared: Patient | null;
}) {
  if (queueMode === "oldest" || patient == null || patient.score_kind === "age") {
    return null;
  }

  const weight = heartWeightOf(queueMode);
  const position = scoreScalePosition(patient.score, patient.score_kind, weight);
  const previewPosition =
    compared != null && compared.score_kind === patient.score_kind
      ? scoreScalePosition(compared.score, compared.score_kind, weight)
      : null;

  return (
    <div className="legend-row legend-score">
      <span className="legend-organ">
        {queueMode === "model" ? "Model" : "Score"}
      </span>
      <div className="legend-scale">
        <Scale
          swatch="risk-heat"
          position={position}
          label={patient != null ? scoreLabel(patient) : null}
          previewPosition={previewPosition}
          previewLabel={compared != null ? scoreLabel(compared) : null}
        />
        <div className="legend-ends">
          <span>Lower</span>
          <span>
            {queueMode === "model"
              ? "Higher model score"
              : `Higher · max ${pointsCeiling(weight)}`}
          </span>
        </div>
      </div>
    </div>
  );
}

export default function ColorLegend({
  mode,
  queueMode,
  patient,
  preview,
  base = false,
}: ColorLegendProps) {
  const compared =
    preview != null && preview.patient_id !== patient?.patient_id
      ? preview
      : null;

  if (mode === "risk") {
    return (
      <div className={`color-legend ${base ? "is-base" : ""}`}>
        {base && <p className="color-legend-title">Base model</p>}
        <ScoreScale queueMode={queueMode} patient={patient} compared={compared} />
        {queueMode === "oldest" && (
          <p className="legend-empty">Oldest first ranks by age.</p>
        )}
      </div>
    );
  }

  const ef = patient?.facts.ejection_fraction ?? null;
  const cr = patient?.facts.serum_creatinine ?? null;
  const previewEf = compared?.facts.ejection_fraction ?? null;
  const previewCr = compared?.facts.serum_creatinine ?? null;

  return (
    <div className={`color-legend ${base ? "is-base" : ""}`}>
      {base && <p className="color-legend-title">Base model</p>}
      <ScoreScale queueMode={queueMode} patient={patient} compared={compared} />
      <div className="legend-row">
        <span className="legend-organ">Heart</span>
        <div className="legend-scale">
          <Scale
            swatch="anatomy-heart"
            position={ef === null ? null : heartScalePosition(ef)}
            label={ef === null ? null : `${ef}%`}
            previewPosition={
              previewEf === null ? null : heartScalePosition(previewEf)
            }
            previewLabel={previewEf === null ? null : `${previewEf}%`}
          />
          <div className="legend-ends">
            <span>Higher EF</span>
            <span>Lower EF</span>
          </div>
        </div>
      </div>
      <div className="legend-row">
        <span className="legend-organ">Kidneys</span>
        <div className="legend-scale">
          <Scale
            swatch="anatomy-kidney"
            position={cr === null ? null : kidneyScalePosition(cr)}
            label={cr === null ? null : String(cr)}
            previewPosition={
              previewCr === null ? null : kidneyScalePosition(previewCr)
            }
            previewLabel={previewCr === null ? null : String(previewCr)}
          />
          <div className="legend-ends">
            <span>Lower Cr</span>
            <span>Higher Cr</span>
          </div>
        </div>
      </div>
    </div>
  );
}
