import type { ReactNode } from "react";
import InterfaceIcon from "./InterfaceIcon";

// Educational copy only. Keep labels and units aligned with PatientActions and
// the shared API contract; this module never calculates scores or calls an API.
const fields = [
  { label: "Age", key: "age", type: "Number · years", meaning: "Recorded age at baseline. Age also determines the Oldest queue and adds one rule point at 70 years or older." },
  { label: "Ejection fraction (EF)", key: "ejection_fraction", type: "Number · %", meaning: "The percentage of blood pumped out of the left ventricle with each contraction. Used by the heart model, heart measurement card and Tissue State view." },
  { label: "Serum creatinine (Cr)", key: "serum_creatinine", type: "Number · mg/dL", meaning: "A blood measurement of creatinine, a waste product associated with muscle metabolism and kidney filtration. Used by the kidney model, kidney measurement card and Tissue State view." },
  { label: "Serum sodium", key: "serum_sodium", type: "Number · mEq/L", meaning: "Blood sodium concentration. Sodium is an electrolyte involved in fluid balance, nerve function and muscle function." },
  { label: "Platelets", key: "platelets", type: "Number · platelets/µL", meaning: "The recorded platelet count per microlitre of blood. Platelets help blood clot. A displayed value such as 250,000 is a count, not a score." },
  { label: "Creatinine phosphokinase (CPK / CK)", key: "creatinine_phosphokinase", type: "Number · mcg/L", meaning: "The dataset's recorded creatine kinase measurement. CK is an enzyme found in muscle, including the heart; total CK is not heart-specific. The form retains the source dataset's mcg/L unit contract." },
  { label: "Anaemia", key: "anaemia", type: "Binary · No / Yes", meaning: "Recorded flag for a reduction in red blood cells or haemoglobin. This flag contains no haemoglobin measurement, cause or severity." },
  { label: "Diabetes", key: "diabetes", type: "Binary · No / Yes", meaning: "Whether diabetes was recorded. This flag contains no glucose measurement, diabetes type or disease severity." },
  { label: "High blood pressure", key: "high_blood_pressure", type: "Binary · No / Yes", meaning: "Whether high blood pressure was recorded. This flag is not a systolic or diastolic blood pressure reading." },
  { label: "Smoking", key: "smoking", type: "Binary · No / Yes", meaning: "The recorded smoking flag. It does not describe quantity, duration or a complete smoking history." },
  { label: "Recorded sex", key: "sex", type: "Binary · 0 / 1", meaning: "The original dataset encoding: 0 = female, 1 = male. This source field does not represent a complete patient identity or gender history." },
] as const;

function ReadingHeader({ eyebrow, title, children }: { eyebrow: string; title: string; children: ReactNode }) {
  return <div className="reading-heading"><p className="eyebrow">{eyebrow}</p><h1>{title}</h1><p className="page-description">{children}</p></div>;
}

function GuideSection({ id, number, title, children }: { id: string; number: string; title: string; children: ReactNode }) {
  return <section className="guide-section" id={id} aria-labelledby={`${id}-title`}>
    <div className="guide-section-heading"><span className="section-number">{number}</span><h2 id={`${id}-title`}>{title}</h2></div>
    {children}
  </section>;
}

export function FieldGuide() {
  return <div className="reading-page">
    <ReadingHeader eyebrow="Reference for the review workspace" title="Field guide">
      What the measurements, scores and labels mean — and how to read them together.
    </ReadingHeader>
    <div className="reading-layout">
      <nav className="reading-nav" aria-label="Field guide contents">
        <p className="eyebrow">In this guide</p>
        <a href="#guide-measurements">01 · Patient measurements</a>
        <a href="#guide-models">02 · Model outputs</a>
        <a href="#guide-queue">03 · Queue and rule points</a>
        <a href="#guide-visuals">04 · Anatomy and colours</a>
        <a href="#guide-evidence">05 · Evidence and versions</a>
        <a href="#guide-assistant">06 · Assistant and data states</a>
        <a href="#guide-benchmark">07 · Historical benchmark</a>
        <a href="#guide-sources">Definition sources</a>
      </nav>
      <div className="reading-body">
        <div className="guide-callout"><InterfaceIcon name="info" /><p><strong>Three different concepts.</strong> A model score is a continuous output. A classification compares it with a model threshold. Queue priority describes position in a limited call list. Their labels are not interchangeable.</p></div>
        <GuideSection id="guide-measurements" number="01" title="Patient measurements">
          <p>These eleven baseline fields are the inputs shown on the dashboard and collected by Add patient. Numeric values may contain decimals. Every binary field requires an explicit selection; the source encodes No as 0 and Yes as 1.</p>
          <div className="reference-table-wrap"><table className="reference-table">
            <caption className="sr-only">All eleven patient input fields, their types, units and meanings</caption>
            <thead><tr><th scope="col">Field</th><th scope="col">Value type / unit</th><th scope="col">Meaning in this project</th></tr></thead>
            <tbody>{fields.map((field) => <tr key={field.key}><th scope="row">{field.label}<code>{field.key}</code></th><td>{field.type}</td><td>{field.meaning}</td></tr>)}</tbody>
          </table></div>
          <p className="guide-footnote">Use the units shown in the form. The source's platelet unit, kiloplatelets/mL, is numerically equivalent to platelets/µL. Numeric inputs must be finite and nonnegative; age, creatinine and sodium must be positive, and EF cannot exceed 100%. These are input validation rules, not clinical reference ranges. “None recorded” means the four condition flags are No; it does not establish that a patient is healthy.</p>
          <p className="guide-footnote"><code>time</code> (source follow-up duration) and <code>DEATH_EVENT</code> (recorded outcome) are reserved for evaluation. They are not patient-entry fields, model predictors or ordinary assistant context.</p>
        </GuideSection>
        <GuideSection id="guide-models" number="02" title="Model outputs">
          <div className="guide-card-grid three">
            <article className="guide-mini-card"><span className="guide-card-icon"><InterfaceIcon name="heart" /></span><h3>Heart risk</h3><code>heart_risk</code><p>Heart-feature outcome proxy. The current published random forest uses EF, age, high blood pressure, diabetes, smoking and anaemia.</p></article>
            <article className="guide-mini-card"><span className="guide-card-icon"><InterfaceIcon name="layers" /></span><h3>Kidney risk</h3><code>kidney_risk</code><p>Kidney-feature outcome proxy. The current published random forest uses creatinine, age, recorded sex, diabetes, high blood pressure and smoking.</p></article>
            <article className="guide-mini-card"><span className="guide-card-icon"><InterfaceIcon name="user" /></span><h3>Patient risk</h3><code>patient_risk</code><p>Whole-patient outcome proxy. The current published logistic regression uses all eleven fields. Model mode orders the queue by this score; it does not average the organ scores.</p></article>
          </div>
          <dl className="definition-list">
            <div><dt>Score <code>score</code></dt><dd>A decimal from 0 to 1, displayed to three decimal places. Higher means a higher model output for the source's recorded death outcome. A score of 0.700 is not a validated 70% death probability.</dd></div>
            <div><dt>Relative band <code>band</code></dt><dd><strong>lower / middle / higher</strong> compare the score with frozen cutoffs derived from development out-of-fold score thirds. These are relative model bands, not disease stages or queue-priority bands.</dd></div>
            <div><dt>Classification <code>classification_positive</code></dt><dd><strong>Positive</strong> means the full-precision score is at or above <code>classification_threshold</code>; otherwise it is <strong>Negative</strong>. This is a prediction of the recorded outcome target, not a current heart or kidney diagnosis. The displayed threshold is rounded; it is separate from band cutoffs.</dd></div>
            <div><dt>Calibration <code>calibration_status</code></dt><dd><code>not_calibrated</code> means the outputs have not been validated as individual probabilities. The dataset has no organ-specific outcomes and no fixed prediction horizon for these scores.</dd></div>
          </dl>
        </GuideSection>
        <GuideSection id="guide-queue" number="03" title="Queue and rule points">
          <dl className="definition-list">
            <div><dt>Patient ID <code>patient_id</code></dt><dd>A synthetic identifier such as <code>HF-0001</code>; “Patient 1” is its short display label. It is not a name, health number or clinical identity.</dd></div>
            <div><dt>Rank <code>rank / call_rank</code></dt><dd>Position in the current call order; 1 is first. Top 25 shows the first 25 eligible records, or fewer if the cohort is smaller. The patient picker can also select eligible records outside that list.</dd></div>
            <div><dt>Queue priority <code>priority_band</code></dt><dd><strong>higher</strong> = ranks 1–25; <strong>elevated</strong> = ranks 26–75; <strong>lower</strong> = remaining ranks. These bands describe resource-based queue position, not clinical urgency.</dd></div>
            <div><dt>Comparison rank <code>model_rank / oldest_rank</code></dt><dd>The reference ordering used by “vs Model” or “vs Oldest”. A positive move means a patient moved up that many positions in the current list; a negative move means down. Zero means unchanged. The model reference is the underlying score order and can differ from call order when a manual pin is active.</dd></div>
            <div><dt>Workflow <code>workflow_state</code></dt><dd><code>pending</code> = awaiting review; <code>reviewed</code> = reviewed; <code>contacted</code> = contact recorded; <code>needs_clinician_review</code> = escalation recorded. These are workflow metadata, independent of scores and diagnoses. The dashboard displays the current value.</dd></div>
          </dl>
          <div className="reference-table-wrap"><table className="reference-table compact">
            <caption>How the call list modes use values</caption><thead><tr><th scope="col">Mode</th><th scope="col">Value shown</th><th scope="col">Ordering</th></tr></thead><tbody>
              <tr><th scope="row">Model</th><td>Patient ML score · 0–1</td><td>Descending frozen <code>patient_risk</code> score. If ML is unavailable, the interface explicitly uses rule points.</td></tr>
              <tr><th scope="row">Weight 2 / Weight 3</th><td>Combined score · 0–2, with rule points shown separately</td><td>Patient ML score + points ÷ (heart weight + 6). Without ML, rule points alone determine order.</td></tr>
              <tr><th scope="row">Oldest</th><td>Age · years; Score column displays —</td><td>Descending recorded age. This is a comparison baseline, not an ML score.</td></tr>
            </tbody></table></div>
          <p><strong>Rule points:</strong> EF below 35% adds the selected heart weight (2 or 3); creatinine above 1.5 mg/dL adds 2; anaemia, diabetes, high blood pressure and age at least 70 each add 1. The maximum is 8 for Weight 2 or 9 for Weight 3. Smoking, recorded sex, sodium, platelets and CPK do not add rule points.</p>
          <p className="guide-footnote">Rule evidence chips show the activated condition and its added points. Model feature selection and point rules are separate. Existing manual pins can place a patient ahead of automatic ordering; contacted and deferred records are excluded from the eligible list.</p>
        </GuideSection>
        <GuideSection id="guide-visuals" number="04" title="Anatomy and colours">
          <dl className="definition-list">
            <div><dt>Risk Score view</dt><dd>Heart tint uses <code>heart_risk.score</code>; both kidney meshes use <code>kidney_risk.score</code>. Green-to-red colour shows lower-to-higher continuous model output. Read the numeric score and its label alongside the colour; it is not a disease severity scale.</dd></div>
            <div><dt>Tissue State view</dt><dd>Heart tint reflects recorded EF and kidney tint reflects recorded creatinine. This is a schematic measurement view of the same generic 3D models, not patient imaging or a simulation of tissue damage.</dd></div>
            <div><dt>Measurement flags <code>organs.*.state</code></dt><dd><code>flagged</code> means EF &lt; 35% or creatinine &gt; 1.5 mg/dL under the project's indicator policy; <code>not_flagged</code> means the rule is not activated; <code>unknown</code> means unavailable. These prototype thresholds are not a complete clinical assessment.</dd></div>
            <div><dt>Viewer controls</dt><dd><strong>Show Tint</strong> toggles each organ's overlay. Drag to rotate, scroll to zoom, and select an organ or its measurement card to focus. Expand opens that organ; Minimize or Escape returns to the split view. Queue-row hover adds a comparison marker to the legend without changing the selected patient.</dd></div>
          </dl>
        </GuideSection>
        <GuideSection id="guide-evidence" number="05" title="Evidence and model versions">
          <p>Open <strong>Model versions and evidence</strong> to inspect the actual fields and metadata supplied with the selected patient's outputs.</p>
          <dl className="definition-list">
            <div><dt>Family and version <code>model_family / model_version</code></dt><dd>The classifier family and identifier of its frozen fitted version. <code>random_forest</code> combines decision trees; <code>logistic_regression</code> uses a fitted linear decision function. <code>gradient_boosting</code> is an experimental family supported by the contract. The visible output identifies the published family actually used.</dd></div>
            <div><dt>Bundle <code>bundle_id</code></dt><dd>The identifier of the publication containing all three models, preprocessing, thresholds and metadata. Adding a patient runs inference through this publication; it does not train new models.</dd></div>
            <div><dt>Prediction origin <code>prediction_provenance</code></dt><dd><code>development_in_sample</code> = scored by models fitted on the development cohort; <code>held_out_test</code> = originally reserved test record; <code>new_patient_inference</code> = new or updated baseline facts scored by frozen models. In-sample predictions are not independent validation.</dd></div>
            <div><dt>Evidence items <code>evidence</code></dt><dd>Each item has an <code>id</code>, input <code>field</code>, recorded <code>value</code>, optional <code>unit</code>, and descriptive <code>predicate</code>. Rule evidence can include added <code>points</code>. ML evidence has a <code>scale</code> of <code>log_odds</code> or <code>recorded_measurement</code>.</dd></div>
            <div><dt>Explanation <code>explanation_method</code></dt><dd><code>linear_log_odds</code> provides scaled-input contributions and the logistic intercept. Positive contributions increase the model's log-odds; negative contributions decrease them. They are not percentage points or proof of causation. <code>recorded_features_no_local_attribution</code> lists the forest's inputs without assigning individual feature contributions.</dd></div>
            <div><dt>Contribution and intercept</dt><dd><code>contribution</code> is an input's additive effect in the logistic model's log-odds scale. <code>intercept</code> is that model's baseline fitted term. Missing contributions for forests mean attribution is not supplied, not that an input has no effect.</dd></div>
          </dl>
          <p className="guide-footnote">The score type <code>score_kind</code> identifies <code>model_output</code>, <code>points</code>, <code>combined</code> or <code>age</code>. A dash (—) denotes missing or inapplicable information; it does not mean zero. Numbers shown to three decimals are rounded for reading.</p>
        </GuideSection>
        <GuideSection id="guide-assistant" number="06" title="Assistant and data states">
          <dl className="definition-list">
            <div><dt>API data / Current API snapshot</dt><dd>Records loaded from the backend with a versioned cohort, ordering method and snapshot. The assistant retrieves evidence for this matching context. Refresh patients reloads the active order.</dd></div>
            <div><dt>Local CSV preview / Local preview</dt><dd>The preview uses bundled public data or a browser-only combined ordering without a matching voice snapshot. Add/delete require API data. Factual text shortcuts can still describe the visible records; live agent access requires a matching API snapshot.</dd></div>
            <div><dt>Connection status</dt><dd><strong>Disconnected</strong> = no agent session; <strong>Connecting</strong> = starting; <strong>Text connected</strong> = text-only session; <strong>Listening / Speaking</strong> = voice activity; <strong>Microphone muted</strong> = input muted; <strong>Retrieving evidence</strong> = a factual read is in progress.</dd></div>
            <div><dt>Assistant controls</dt><dd>Start voice or Start text begins a session. Stop ends it. Mute mic controls input; Mute audio controls output; Reconnect starts a new session. Patient overview, Why prioritized? and Brief queue retrieve factual summaries. The transcript labels messages as You, Assistant or Dashboard.</dd></div>
            <div><dt>Patient actions</dt><dd>Add patient collects all eleven baseline fields and refreshes the selected record's outputs. Delete patient requires a reason and confirmation, removes the record from the live cohort and retains audit history. Changing patient or queue resets the assistant context and transcript; opening these reference tabs preserves workspace state.</dd></div>
          </dl>
        </GuideSection>
        <GuideSection id="guide-benchmark" number="07" title="Historical benchmark">
          <p><strong>Original records</strong> is the labelled public cohort size used for evaluation. <strong>Dropped</strong> is the ingestion missing-row count. <strong>Deaths in top 25</strong> counts recorded outcomes captured by each original ordering: Oldest first, pure points Weight 2 and pure points Weight 3.</p>
          <p><strong>2 vs 3 overlap</strong> is the number of shared patients in those two 25-person points lists. These fixed retrospective counts are separate from today's live cohort and from browser-combined ML + points lists. They are not predictions of how many current patients will die or evidence of a treatment benefit.</p>
        </GuideSection>
        <section className="guide-sources" id="guide-sources" aria-label="Medical definition sources"><h2>Definition sources</h2>
          <p>The definitions above use the source dataset's fields and these medical references. The project's thresholds and ML bands are documented separately in the model metadata.</p>
          <div className="source-links">
            <a href="https://www.heart.org/en/health-topics/heart-failure/diagnosing-heart-failure/ejection-fraction-heart-failure-measurement" target="_blank" rel="noreferrer">American Heart Association · Ejection fraction</a>
            <a href="https://medlineplus.gov/lab-tests/creatinine-test/" target="_blank" rel="noreferrer">MedlinePlus · Creatinine</a>
            <a href="https://medlineplus.gov/lab-tests/sodium-blood-test/" target="_blank" rel="noreferrer">MedlinePlus · Sodium</a>
            <a href="https://medlineplus.gov/lab-tests/platelet-tests/" target="_blank" rel="noreferrer">MedlinePlus · Platelets</a>
            <a href="https://medlineplus.gov/lab-tests/creatine-kinase/" target="_blank" rel="noreferrer">MedlinePlus · Creatine kinase</a>
            <a href="https://archive.ics.uci.edu/dataset/519/heart+failure+clinical+records" target="_blank" rel="noreferrer">UCI · Heart Failure Clinical Records</a>
          </div>
        </section>
      </div>
    </div>
  </div>;
}

export function ProgramOverview() {
  return <div className="reading-page overview-page">
    <ReadingHeader eyebrow="Purpose, workflow and scope" title="About the program">
      Turn baseline patient records into a focused follow-up review, with the evidence in view.
    </ReadingHeader>
    <section className="overview-intro" aria-labelledby="overview-purpose">
      <div><span className="overview-mark"><InterfaceIcon name="pulse" /></span><h2 id="overview-purpose">A clearer starting point for follow-up.</h2><p>H.A.K is a heart-failure follow-up prioritization prototype. It helps a reviewer compare an eligible patient cohort, inspect a limited call list, understand recorded measurements and ask for context-grounded explanations.</p><p>The workspace brings queue order, three independent model outputs, anatomical illustrations and the follow-up assistant into one review.</p></div>
      <div className="overview-facts"><div><strong>25</strong><span>places in the review call list</span></div><div><strong>3</strong><span>published model outputs</span></div><div><strong>11</strong><span>baseline input fields</span></div><div><strong>299</strong><span>records in the original public dataset</span></div></div>
    </section>
    <section className="overview-section" aria-labelledby="overview-flow"><p className="eyebrow">How the pieces connect</p><h2 id="overview-flow">From a record to an explained queue.</h2>
      <ol className="program-flow">
        <li><span className="section-number">01</span><h3>Recorded inputs</h3><p>Eleven baseline measurements and flags enter through the cohort or Add patient.</p></li>
        <li><span className="section-number">02</span><h3>Frozen inference</h3><p>Each published preprocessing pipeline and model produces heart, kidney or patient output.</p></li>
        <li><span className="section-number">03</span><h3>Prioritized review</h3><p>The selected queue mode orders eligible records and displays its first 25.</p></li>
        <li><span className="section-number">04</span><h3>Evidence in context</h3><p>The record, illustrations and assistant explain the selected patient and current list.</p></li>
      </ol>
    </section>
    <div className="overview-columns">
      <section className="overview-section" aria-labelledby="overview-review"><p className="eyebrow">Using the workspace</p><h2 id="overview-review">A practical review sequence.</h2>
        <ol className="review-steps">
          <li><strong>Choose the ordering.</strong> Compare Model, Weight 2, Weight 3 and Oldest. Read the ordering description and historical benchmark.</li>
          <li><strong>Select a patient.</strong> Use a call-list row or the full eligible-patient picker. Check the independent model outputs and recorded measurements.</li>
          <li><strong>Inspect the visual evidence.</strong> Switch between Risk Score and Tissue State, focus an organ and use the legend's numbers.</li>
          <li><strong>Ask for an explanation.</strong> Use factual shortcuts or a connected ElevenLabs voice/text session. The assistant uses the active snapshot when available.</li>
          <li><strong>Manage the live cohort.</strong> Add a fully specified baseline record or delete a selected record with an audit reason. The dashboard refreshes the resulting order.</li>
        </ol>
      </section>
      <section className="overview-section" aria-labelledby="overview-achieves"><p className="eyebrow">What this prototype achieves</p><h2 id="overview-achieves">One traceable review surface.</h2>
        <ul className="outcome-list"><li><strong>Consistent outputs.</strong> Patient reads, the API-backed queue and assistant context use shared versioned model results.</li><li><strong>Visible reasoning.</strong> Measurements, thresholds, rule points and model evidence remain inspectable alongside the ranking.</li><li><strong>Clear comparisons.</strong> ML, combined rules and age-based orderings can be compared without changing the published models.</li><li><strong>Accessible explanations.</strong> The field guide and text summaries complement the 3D view and voice interaction.</li></ul>
      </section>
    </div>
    <section className="scope-card" aria-labelledby="overview-scope"><InterfaceIcon name="info" /><div><h2 id="overview-scope">Research scope</h2><p>The starting cohort is the public UCI Heart Failure Clinical Records dataset with synthetic patient IDs. It has a recorded death outcome but no organ-specific outcomes. All three outputs are uncalibrated outcome proxies, and the organ illustrations are generic models rather than patient scans.</p><p>This prototype demonstrates prioritization and evidence presentation. It does not establish diagnoses, validated individual mortality probabilities, a clinical time horizon or improved patient outcomes. New records are scored by frozen pipelines; dashboard interactions do not train models.</p></div></section>
    <p className="overview-source">Dataset: <a href="https://archive.ics.uci.edu/dataset/519/heart+failure+clinical+records" target="_blank" rel="noreferrer">UCI Heart Failure Clinical Records · CC BY 4.0</a>. The dashboard footer retains attribution for the existing heart and kidney models.</p>
  </div>;
}
