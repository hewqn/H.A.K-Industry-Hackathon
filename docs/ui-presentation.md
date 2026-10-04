# Dashboard presentation

This change on `ui_modernization` refreshes the existing React interface and adds
Field guide and About the program tabs. It does not change the backend, API
contracts, published models, inference, ranking or clinical indicator policies.

## Design and reading order

- A restrained navy/teal palette, consistent spacing and tabular numbers make
  measurements and scores easier to compare. Amber identifies an existing rule
  flag or relative label; wording remains present alongside colour.
- The patient selection toolbar and selected-record summary precede the queue,
  anatomy and evidence panels. The assistant sits beneath the review panels.
- Desktop uses three columns. Smaller screens use two columns and then a single
  reading column. Tables scroll within their own containers rather than widening
  the entire page. The existing organ expansion still uses the full viewport.
- All eleven input labels/units remain visible in the forms. Numeric formatting,
  rule points, model thresholds, model evidence and historical counts are retained.
- Native patient selection buttons keep the queue's table semantics. Column
  headers remain associated with rows in one table with a sticky header.
- Keyboard users have a skip link, visible focus, labelled landmarks and tab/panel
  relationships. Arrow keys, Home and End move among tabs; Enter/Space activates a
  focused tab through the native button. Each panel is keyboard focusable.
- Reduced-motion and forced-colour styles are included. Decorative SVG icons do
  not replace text labels. No external font, new UI dependency or generated 3D
  asset is introduced.

## Explanation tabs

The Field guide documents all baseline inputs, units, binary encodings, three ML
outputs, classifier thresholds, relative bands, queue bands, comparison ranks,
workflow metadata, evidence, provenance, versions, score types, assistant states,
anatomy controls and the original points benchmark. It distinguishes score from
probability, classification from diagnosis and call order from clinical urgency.
It also explains unavailable values and evaluator-only outcome/follow-up fields.

About the program describes the purpose, data-to-review flow, existing review
actions, what the prototype demonstrates and the limits of its public dataset.

All tab panels stay mounted. Opening reference content does not clear patient
selection, ordering, colour mode, camera, transcript, or provider-session state.
Existing patient/queue changes still use their original lifecycle and refresh rules.
Only navigation state and browser document titles are new application state.

The guide's current family/feature descriptions match the frozen publication.
If the team publishes a different selection or changes the dataset contract,
update `frontend/src/components/ProjectGuide.tsx` alongside that change. The live
ML output/evidence panel always reads its values from the existing patient object.

## Sources

Design choices were informed by [NHS accessibility design guidance](https://service-manual.nhs.uk/accessibility/design)
and [WCAG 2.2](https://www.w3.org/TR/WCAG22/), particularly labels, contrast, keyboard
focus, semantic structure and not relying on colour alone. This is not a claim
of a completed accessibility certification.

Medical definitions link from the Field guide to the
[AHA ejection fraction explanation](https://www.heart.org/en/health-topics/heart-failure/diagnosing-heart-failure/ejection-fraction-heart-failure-measurement),
MedlinePlus pages for [creatinine](https://medlineplus.gov/lab-tests/creatinine-test/),
[sodium](https://medlineplus.gov/lab-tests/sodium-blood-test/),
[platelets](https://medlineplus.gov/lab-tests/platelet-tests/),
and [creatine kinase](https://medlineplus.gov/lab-tests/creatine-kinase/),
plus the [UCI source dataset](https://archive.ics.uci.edu/dataset/519/heart+failure+clinical+records).
Project thresholds and model semantics come from the existing contracts and
`docs/ml-dashboard-audit.md`, rather than new clinical recommendations.

## Verification

- All **37 frontend tests** passed, including existing patient add/delete, ranking,
  independent organ-output wiring and ElevenLabs SDK tests.
- New tests verify all eleven guide entries, score/scope explanations, tab keyboard
  navigation, one visible main heading and patient/mode/viewer/assistant preservation.
- TypeScript, production build and whitespace checks passed. Frontend lint retains
  only the existing AnatomyViewer state-in-effect warning. Vite retains its existing
  large-bundle warning; bundling/architecture are outside this presentation change.
- The original application loading/refresh and patient mutation logic was compared
  directly with HEAD. API, scoring, ML, VoicePanel lifecycle, OrganModel and model
  assets have no changes. AnatomyViewer adds only a visible organ label.
- The checked foreground/background pairs have contrast ratios from **5.61:1 to
  14.07:1**: main/secondary text, primary/danger buttons, risk-band labels, explanatory
  callouts and the keyboard focus colour. This checks those pairs, not every rendered
  state or a complete WCAG audit.

Native browser automation failed to start and the in-app browser was unavailable,
so rendered layout, WebGL sizing and microphone/speaker acceptance were not visually
verified here. Before the demo, review the three tabs at desktop and phone widths;
check table scrolling, keyboard focus, organ expansion/Escape and modal form sizing
in the running app. No live cohort writes or paid agent calls were made for this UI work.
