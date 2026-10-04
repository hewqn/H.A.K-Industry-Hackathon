# Anatomy engineer handoff

No 3D models have been created. `asset_url: null` intentionally activates usable text
cards. The engineer owns anatomy geometry, materials, camera/lighting refinement, and
the visual quality of their asset or viewer. This file replaces an empty placeholder.

Two integration choices:

1. Add a licensed, self-contained `anatomy.glb` here, map the four semantic nodes in
   `manifest.json`, record license/attribution, and set `asset_url` to
   `/assets/anatomy/anatomy.glb`, then implement `mountAnatomy` in the adapter.
   Nodes may be groups of mesh primitives; the adapter is a typed TODO, not a viewer.
2. Replace `src/anatomy/adapter.ts` with a module implementing `AnatomyHandle`, or
   supply a React component accepting `AnatomyProps`. Preserve the external contract.

Contract: Y-up, front +Z; body + heart + two independently recolorable kidneys; target
≤5 MB and ≤100k triangles. Clone shared materials before changing independent organ
colors. Embedded textures only; no runtime external hosts. Use opaque organs inside
the transparent body (default opacity .15), inspect depth sorting, and preserve camera
position across patient updates. Do not derive organ shape/size/beat rate from records.

The backend already provides `flagged`, `not_flagged`, and `unknown` indicators. Both
kidneys share serum-creatinine evidence. The viewer must not calculate thresholds,
read the CSV, select a ranking method, or maintain a separate selected patient.

Verify rotation, constrained zoom, reset, resize, organ selection, absent nodes,
unsupported WebGL, late asset completion after unmount, reduced motion, ≤1.5 DPR,
offscreen pause, and resource disposal. Supply a preview image and license evidence.
Record actual FPS/load times before marking VIZ-01/VIZ-02 complete.
