import { Canvas, useThree } from "@react-three/fiber";
import { OrbitControls } from "@react-three/drei";
import { Suspense, useCallback, useEffect, useLayoutEffect, useState } from "react";
import type { OrbitControls as OrbitControlsImpl } from "three-stdlib";
import OrganModel from "./OrganModel";
import type { OrganId, OrganIndicator } from "../types/patient";
import type { ColorMode } from "../utils/organColors";

type OrganKey = "heart" | "kidney";

interface AnatomyViewerProps {
  organs: Record<OrganId, OrganIndicator>;
  focusedOrgan: OrganId | null;
  onOrganSelect: (organ: OrganId | null) => void;
  colorMode?: ColorMode;
  organRisk?: { heart: number; kidney: number };
  applyColour?: { heart: boolean; kidney: boolean };
  onApplyColourChange?: (organ: OrganKey, on: boolean) => void;
}

function FrameOrgan({ distance }: { distance: number }) {
  const { camera, controls, invalidate } = useThree();

  useLayoutEffect(() => {
    camera.position.set(0, 0, distance);
    camera.up.set(0, 1, 0);
    camera.lookAt(0, 0, 0);
    camera.updateProjectionMatrix();

    const orbit = controls as OrbitControlsImpl | null;
    if (orbit) {
      orbit.target.set(0, 0, 0);
      orbit.update();
    }
    invalidate();
  }, [camera, controls, distance, invalidate]);

  return null;
}

function OrganCanvas({
  url,
  organId,
  indicator,
  colorMode,
  riskScore,
  focused,
  expanded,
  hidden,
  onSelect,
  onToggleExpand,
  label,
  applyColour,
  onApplyColourChange,
}: {
  url: string;
  organId: OrganKey;
  indicator: OrganIndicator;
  colorMode: ColorMode;
  riskScore?: number;
  focused: boolean;
  expanded: boolean;
  hidden: boolean;
  onSelect: () => void;
  onToggleExpand: () => void;
  label: string;
  applyColour: boolean;
  onApplyColourChange: (on: boolean) => void;
}) {
  const [ready, setReady] = useState(false);
  const distance = expanded ? 1.75 : 2.15;
  const markReady = useCallback(() => setReady(true), []);

  useEffect(() => {
    setReady(false);
  }, [expanded, url]);

  return (
    <div className={`organ-slot ${hidden ? "hidden" : ""}`}>
      <div
        className={`organ-viewport ${focused ? "focused" : ""} ${expanded ? "expanded" : ""}`}
      >
        <label className="organ-colour-check">
          <input
            type="checkbox"
            checked={applyColour}
            onChange={(event) => onApplyColourChange(event.target.checked)}
          />
          Show Tint
        </label>
        {!ready && (
          <div className="organ-loader" role="status" aria-live="polite">
            <span className="organ-spinner" />
            <span>Loading {label.toLowerCase()}</span>
          </div>
        )}
        <Canvas
          key={`${organId}-${expanded ? "full" : "split"}`}
          camera={{ position: [0, 0, distance], fov: 32 }}
          dpr={[1, 1.5]}
          gl={{ antialias: true, alpha: true }}
        >
          <color attach="background" args={["#f8f9fb"]} />
          <hemisphereLight args={["#f3efe9", "#d4cfc8", 0.5]} />
          <ambientLight intensity={0.36} />
          <directionalLight position={[3, 5, 6]} intensity={0.88} />
          <directionalLight position={[-4, 1, 2]} intensity={0.2} />

          <Suspense fallback={null}>
            <OrganModel
              url={url}
              organId={organId}
              indicator={indicator}
              colorMode={colorMode}
              riskScore={riskScore}
              position={[0, 0, 0]}
              scale={1}
              onClick={onSelect}
              focused={focused}
              onReady={markReady}
              baseCompare={!applyColour}
            />
          </Suspense>

          <OrbitControls
            enablePan={false}
            target={[0, 0, 0]}
            minDistance={1.1}
            maxDistance={5}
            makeDefault
          />
          <FrameOrgan distance={distance} />
        </Canvas>

        {/* Visible labels identify the existing geometry without relying on tint. */}
        <span className="viewport-organ-label">{label}</span>

        <button
          type="button"
          className="viewport-expand"
          onClick={onToggleExpand}
          aria-label={expanded ? `Minimize ${label}` : `Expand ${label}`}
          title={expanded ? "Minimize" : "Expand"}
        >
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
            <path
              d={
                expanded
                  ? "M3 6h3V3M13 6h-3V3M3 10h3v3M13 10h-3v3"
                  : "M6 3H3v3M10 3h3v3M3 10v3h3M13 10v3h-3"
              }
              stroke="currentColor"
              strokeWidth="1.6"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        </button>
      </div>
    </div>
  );
}

export default function AnatomyViewer({
  organs,
  focusedOrgan,
  onOrganSelect,
  colorMode = "anatomy",
  organRisk,
  applyColour = { heart: true, kidney: true },
  onApplyColourChange,
}: AnatomyViewerProps) {
  const [expanded, setExpanded] = useState<OrganKey | null>(null);

  useEffect(() => {
    if (!expanded) return;

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setExpanded(null);
    };
    window.addEventListener("keydown", onKeyDown);
    document.body.style.overflow = "hidden";

    return () => {
      window.removeEventListener("keydown", onKeyDown);
      document.body.style.overflow = "";
    };
  }, [expanded]);

  return (
    <div className={`anatomy-canvas ${expanded ? "has-expanded" : ""}`}>
      <OrganCanvas
        url="/models/human_heart.glb"
        organId="heart"
        indicator={organs.heart}
        colorMode={colorMode}
        riskScore={organRisk?.heart}
        focused={focusedOrgan === "heart"}
        expanded={expanded === "heart"}
        hidden={expanded === "kidney"}
        applyColour={applyColour.heart}
        onApplyColourChange={(on) => onApplyColourChange?.("heart", on)}
        onSelect={() =>
          onOrganSelect(focusedOrgan === "heart" ? null : "heart")
        }
        onToggleExpand={() =>
          setExpanded((current) => (current === "heart" ? null : "heart"))
        }
        label="Heart"
      />
      <OrganCanvas
        url="/models/human_kidney.glb"
        organId="kidney"
        indicator={organs.kidney_left}
        colorMode={colorMode}
        riskScore={organRisk?.kidney}
        focused={focusedOrgan === "kidney_left" || focusedOrgan === "kidney_right"}
        expanded={expanded === "kidney"}
        hidden={expanded === "heart"}
        applyColour={applyColour.kidney}
        onApplyColourChange={(on) => onApplyColourChange?.("kidney", on)}
        onSelect={() =>
          onOrganSelect(
            focusedOrgan === "kidney_left" || focusedOrgan === "kidney_right"
              ? null
              : "kidney_left"
          )
        }
        onToggleExpand={() =>
          setExpanded((current) => (current === "kidney" ? null : "kidney"))
        }
        label="Kidneys"
      />
    </div>
  );
}
