import type { AnatomyProps } from "../components/AnatomyViewer";
import type { OrganId } from "../api/client";

// The 3D engineer supplies geometry/viewer implementation. No anatomy is generated.
export interface AssetManifest {
  asset_url: string | null;
  nodes: Record<"body" | OrganId, string>;
  orientation: string;
  license: string | null;
  attribution: string | null;
}
export interface AnatomyHandle {
  update: (props: AnatomyProps) => void;
  resetCamera: () => void;
  dispose: () => void;
}

/** TODO(3D ENGINEER, VIZ-01/VIZ-02): mount an engineer-supplied Three.js viewer.
 * Load a local GLB via GLTFLoader or supply your own viewer under this interface.
 * Map body/heart/kidneys from the manifest, clone shared organ materials, normalize
 * bounds, and initialize camera/lighting. update() changes indicator colors/focus
 * without reloading geometry or resetting camera. Both kidneys share creatinine.
 * Implement resize, capped DPR, offscreen pause, rotation/zoom/reset, organ callbacks,
 * reduced motion, late-load cancellation, and dispose() of owned GPU resources.
 * Missing assets/WebGL must leave the React text cards usable. See assets README.
 */
export async function mountAnatomy(_host: HTMLElement, _manifest: AssetManifest, _initial: AnatomyProps): Promise<AnatomyHandle> {
  // Fail explicitly until implemented. asset_url=null means this is never called.
  throw new Error("engineer_viewer_implementation_pending");
}
