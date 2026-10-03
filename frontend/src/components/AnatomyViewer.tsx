import { useEffect, useRef, useState } from "react";
import type { OrganId, Patient } from "../api/client";
import { mountAnatomy, type AnatomyHandle, type AssetManifest } from "../anatomy/adapter";

// This is the handoff boundary for the 3D engineer. The app supplies interpreted
// measurements and selection context; the engineer owns geometry and rendering.
export interface AnatomyProps {
  patient_id: string;
  ranking_snapshot_id: string;
  indicator_policy_version: string;
  organs: Patient["organs"];
  focused_organ: OrganId | null;
  body_opacity: number;
  reduced_motion: boolean;
  onOrganSelect: (organ: OrganId) => void;
  onReady: () => void;
  onError: (code: string) => void;
}

const colors = { flagged: "#B25454", not_flagged: "#6F889C", unknown: "#ADB3BB" };

/** No anatomy is generated here. An optional engineer-supplied GLB is loaded
 * through the adapter, or the engineer can replace that adapter with their viewer.
 * The text cards remain usable before asset delivery and after rendering failures.
 */
export function AnatomyViewer(props: AnatomyProps) {
  const host = useRef<HTMLDivElement>(null);
  const latest = useRef(props); latest.current = props;
  const viewer = useRef<AnatomyHandle | null>(null);
  const [status, setStatus] = useState("Awaiting engineer-supplied anatomy asset");
  const [ready, setReady] = useState(false);
  useEffect(() => {
    const controller = new AbortController();
    let disposed = false;
    async function initialize() {
      try {
        const response = await fetch("/assets/anatomy/manifest.json", { signal: controller.signal });
        if (!response.ok) throw new Error("asset_manifest_unavailable");
        const manifest: AssetManifest = await response.json();
        if (!manifest.asset_url) return;
        setStatus("Loading engineer-supplied anatomy…");
        const handle = await mountAnatomy(host.current!, manifest, latest.current);
        if (disposed) { handle.dispose(); return; }
        viewer.current = handle; handle.update(latest.current); setReady(true); setStatus("Illustrative anatomy"); latest.current.onReady();
      } catch (error) {
        if (!disposed) { setStatus("Anatomy unavailable; recorded measurements remain below."); latest.current.onError((error as Error).message); }
      }
    }
    void initialize();
    return () => { disposed = true; controller.abort(); viewer.current?.dispose(); viewer.current = null; };
  }, []);
  useEffect(() => { viewer.current?.update(props); }, [props.organs, props.focused_organ, props.body_opacity]);
  return <section className="anatomy" aria-label={`Recorded organ indicators for ${props.patient_id}`}>
    <div className="section-title"><h2>Measurement indicators</h2><span className="tag">3D engineer handoff</span></div>
    <div ref={host} className={`canvas-host ${ready ? "" : "awaiting-asset"}`} aria-hidden="true">{!ready && <div><strong>3D integration ready</strong><p>The anatomy engineer can connect an asset or viewer here.</p></div>}</div>
    <p role="status" className="muted">{status}</p>
    <div className="organ-buttons">{(["heart", "kidney_left", "kidney_right"] as OrganId[]).map(organ => <button key={organ} aria-pressed={props.focused_organ === organ} onClick={() => props.onOrganSelect(organ)}><span className="dot" style={{ background: colors[props.organs[organ].state] }} />{organ.replace("_", " ")}<small>{props.organs[organ].value ?? "Unknown"} {props.organs[organ].unit}</small></button>)}</div>
    <button className="text-button" disabled={!ready} onClick={() => viewer.current?.resetCamera()}>Reset camera</button>
    <p className="muted">Coral: prototype threshold crossed · Blue: threshold not crossed · Gray: unknown. EF &lt; 35%; creatinine &gt; 1.5 mg/dL. Colors represent measurement indicators.</p>
  </section>;
}
