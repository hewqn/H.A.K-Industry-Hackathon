import type { Patient } from "../types/patient";
import type { ColorMode } from "../utils/organColors";
import { heartScalePosition, kidneyScalePosition } from "../utils/organColors";

interface ColorLegendProps {
  mode: ColorMode;
  patient?: Patient | null;
  preview?: Patient | null;
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

export default function ColorLegend({
  mode,
  patient,
  preview,
}: ColorLegendProps) {
  const previewing =
    preview !== null &&
    preview !== undefined &&
    preview.patient_id !== patient?.patient_id;

  if (mode === "risk") {
    const heartRisk = patient?.organ_risk.heart ?? null;
    const kidneyRisk = patient?.organ_risk.kidney ?? null;
    const previewHeart = previewing ? preview.organ_risk.heart : null;
    const previewKidney = previewing ? preview.organ_risk.kidney : null;
    const fromModel = patient?.score_kind === "model_output";

    return (
      <div className="color-legend">
        <p className="color-legend-title">Risk colour</p>
        <div className="legend-row">
          <span className="legend-organ">Heart</span>
          <div className="legend-scale">
            <Scale
              swatch="risk-heat"
              position={heartRisk}
              label={
                heartRisk === null
                  ? null
                  : fromModel
                    ? heartRisk.toFixed(2)
                    : `${patient?.facts.ejection_fraction}%`
              }
              previewPosition={previewHeart}
              previewLabel={
                previewHeart === null
                  ? null
                  : preview.score_kind === "model_output"
                    ? previewHeart.toFixed(2)
                    : `${preview.facts.ejection_fraction}%`
              }
            />
            <div className="legend-ends">
              <span>Lower risk</span>
              <span>Higher risk</span>
            </div>
          </div>
        </div>
        <div className="legend-row">
          <span className="legend-organ">Kidneys</span>
          <div className="legend-scale">
            <Scale
              swatch="risk-heat"
              position={kidneyRisk}
              label={
                kidneyRisk === null
                  ? null
                  : fromModel
                    ? kidneyRisk.toFixed(2)
                    : String(patient?.facts.serum_creatinine)
              }
              previewPosition={previewKidney}
              previewLabel={
                previewKidney === null
                  ? null
                  : preview.score_kind === "model_output"
                    ? previewKidney.toFixed(2)
                    : String(preview.facts.serum_creatinine)
              }
            />
            <div className="legend-ends">
              <span>Lower risk</span>
              <span>Higher risk</span>
            </div>
          </div>
        </div>
      </div>
    );
  }

  const ef = patient?.facts.ejection_fraction ?? null;
  const cr = patient?.facts.serum_creatinine ?? null;
  const previewEf = previewing ? preview.facts.ejection_fraction : null;
  const previewCr = previewing ? preview.facts.serum_creatinine : null;

  return (
    <div className="color-legend">
      <p className="color-legend-title">Tissue colour</p>
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
