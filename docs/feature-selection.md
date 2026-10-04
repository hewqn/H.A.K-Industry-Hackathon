# Literature-informed organ feature groups

Quick primary-source review, October 3, 2026. This assigns medically relevant candidate
inputs available in this CSV; it does not establish optimal predictors or clinical validity.
Both organ models still predict `DEATH_EVENT`, because organ-specific targets are absent.

| Model | Selected fields | Medical rationale |
|---|---|---|
| Heart-feature outcome proxy | `ejection_fraction`, `age`, `high_blood_pressure`, `diabetes`, `smoking`, `anaemia` | EF directly describes pumping function; age, hypertension, diabetes, smoking and anaemia provide cardiovascular context. |
| Kidney-feature outcome proxy | `serum_creatinine`, `age`, `sex`, `diabetes`, `high_blood_pressure`, `smoking` | Creatinine is a filtration-related marker interpreted with age/sex; diabetes/hypertension are major kidney-disease causes, and smoking is additional risk context. |
| Patient outcome | All 11 approved baseline features | Captures shared/cardiorenal and other potential predictive information; feature utility must be tested on development data. |

Heart rationale: [AHA heart-health measurements](https://www.heart.org/en/health-topics/heart-failure/heart-failure-tools-resources/know-your-heart-health-numbers)
describes EF as a measure of pumping function;
[AHA causes/risk factors](https://www.heart.org/en/health-topics/heart-failure/causes-and-risks-for-heart-failure)
and [NHLBI causes/risk factors](https://www.nhlbi.nih.gov/health/heart-failure/causes)
support the contextual factors. The anaemia flag does not measure haemoglobin, iron
deficiency or severity; its inclusion is a candidate association, not a diagnosis.

Kidney rationale: [NKF 2021 creatinine equation](https://www.kidney.org/ckd-epi-creatinine-equation-2021)
uses creatinine, age and sex. Including these inputs does not mean this ML model
calculates eGFR or diagnoses CKD. [NIDDK CKD causes](https://www.niddk.nih.gov/health-information/kidney-disease/chronic-kidney-disease-ckd/causes)
identifies diabetes and hypertension as major causes;
[NIDDK diabetic kidney disease](https://www.niddk.nih.gov/health-information/diabetes/overview/preventing-problems/diabetic-kidney-disease)
also identifies smoking as risk context. Dataset `sex` is the original binary source
encoding, not a substitute for broader patient identity or physiology assessment.

## Changes and deliberate exclusions

The heart group is retained with an explicit medical rationale. The kidney group drops
`serum_sodium` and `anaemia`, adds `sex`, and retains creatinine/age/diabetes/BP/smoking.
Serum sodium and anaemia can matter in systemic illness/cardiorenal assessment, but this
compact renal-focused group treats them as nonspecific context rather than primary
filtration inputs. This exclusion is a modelling judgment, not a claim of irrelevance.
All remain available to the full-patient model.

Total `creatinine_phosphokinase` (CPK/CK) is not a heart-specific assay. CK is present in
skeletal muscle as well as the heart, and localisation may require specific tests.
[MedlinePlus CK test](https://medlineplus.gov/lab-tests/creatine-kinase/).
No CK-MB/troponin is present here, so CPK is excluded from the focused heart group.
Platelets are also kept in the full-patient candidate model rather than assigned to
one organ without stronger evidence. `time` and `DEATH_EVENT` never enter predictors.

Code uses `organ-feature-groups-v2`. Rerun the notebook to regenerate pipelines/scores
after changing groups; previous exports have the older feature assignment. Existing
test records have already been evaluated in earlier experiments, so repeated runs are
exploratory comparisons rather than a newly independent validation. Use development
CV for further selection; acquire organ-specific labels for genuine organ-outcome models.
