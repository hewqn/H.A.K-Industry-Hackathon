# Dataset and identity

Bundled public **UCI Heart Failure Clinical Records**, 299 rows, 13 columns, 96 recorded
death labels, no missing cells in the current file. Source: [UCI](https://archive.ics.uci.edu/dataset/519/heart+failure+clinical+records), CC BY 4.0.

Citation: Chicco, Davide and Jurman, Giuseppe (2020), *Machine learning can predict
survival of patients with heart failure from serum creatinine and ejection fraction
alone*. BMC Medical Informatics and Decision Making 20, 16.

Expected SHA-256: `9c73cea7468ff5d517801ec050fe9993da5912fce4b56f296f8df3b38dd75912`.
`HF-0001`…`HF-0299` come from original one-based source row, before cleaning. Do not
renumber after exclusions. The file contains no names, contacts, symptoms, medication
plans, or organ diagnoses. Synthetic IDs identify source records, not real patients.

`time` and `DEATH_EVENT` are evaluator/trainer-only. The 11-field predictor allowlist
is in `domain/constants.py`. The application receives features and aggregate reports.
Numeric source flags remain documented 0/1 encodings; do not infer unknown labels.
Platelets stay raw until the team verifies unit interpretation. No outlier clipping.

The previous empty `placeholder` file has been replaced by these concrete instructions.
