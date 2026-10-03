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
  onOrganSelect: (organ: OrganId) => void;
  colorMode?: ColorMode;
  organRisk?: { heart: number; kidney: number };
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
}: {
  url: string;
  organId: OrganKey;
  indicator: OrganIndicator;
  colorMode: ColorMode;
  riskScore: number;
  focused: boolean;
  expanded: boolean;
  hidden: boolean;
  onSelect: () => void;
  onToggleExpand: () => void;
  label: string;
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
          <hemisphereLight args={["#f8f9fb", "#eef0f4", 0.8]} />
          <ambientLight intensity={0.65} />
          <directionalLight position={[3, 5, 6]} intensity={1.2} />
          <directionalLight position={[-4, 1, 2]} intensity={0.28} />

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

        {expanded ? (
          <button
            type="button"
            className="viewport-close"
            onClick={onToggleExpand}
          >
            Close
            <span className="viewport-close-key">Esc</span>
          </button>
        ) : (
          <button
            type="button"
            className="viewport-expand"
            onClick={onToggleExpand}
            aria-label={`Expand ${label}`}
            title="Full screen"
          >
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
              <path d="M6 3H3v3M10 3h3v3M3 10v3h3M13 10v3h-3" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </button>
        )}
      </div>
    </div>
  );
}

export default function AnatomyViewer({
  organs,
  focusedOrgan,
  onOrganSelect,
  colorMode = "anatomy",
  organRisk = { heart: 0, kidney: 0 },
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
        riskScore={organRisk.heart}
        focused={focusedOrgan === "heart"}
        expanded={expanded === "heart"}
        hidden={expanded === "kidney"}
        onSelect={() => onOrganSelect("heart")}
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
        riskScore={organRisk.kidney}
        focused={focusedOrgan === "kidney_left" || focusedOrgan === "kidney_right"}
        expanded={expanded === "kidney"}
        hidden={expanded === "heart"}
        onSelect={() => onOrganSelect("kidney_left")}
        onToggleExpand={() =>
          setExpanded((current) => (current === "kidney" ? null : "kidney"))
        }
        label="Kidneys"
      />
    </div>
  );
}
