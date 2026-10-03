"""Follow-up ranking: oldest-first vs a risk score; then heavier high-risk weight."""
from pathlib import Path

import pandas as pd

DATA = Path(__file__).parent / "data" / "heart_failure_clinical_records.csv"
HI = 2  # points for a bad ejection fraction or bad creatinine - change me to 3 and re-run
HI_REVISE = 3
TOP = 25


def risk(df, hi):
    score = (df["ejection_fraction"] < 35).astype(int) * hi
    score += (df["serum_creatinine"] > 1.5).astype(int) * hi
    score += df["anaemia"] + df["diabetes"] + df["high_blood_pressure"]
    score += (df["age"] >= 70).astype(int)
    return score


def top(df, score, label):
    ranked = df.assign(score=score).sort_values("score", ascending=False).head(TOP)
    deaths = int(ranked["DEATH_EVENT"].sum())
    print(f"{label:32s}  deaths_in_top{TOP}={deaths}  mean_EF={ranked['ejection_fraction'].mean():.1f}%")
    return set(ranked.index), ranked


def main():
    df = pd.read_csv(DATA)
    missing = int(df.isna().sum().sum())
    df = df.dropna().reset_index(drop=True)
    print(f"Dropped {missing} rows with missing values. Ranking {len(df)} patients ({int(df['DEATH_EVENT'].sum())} later died).")

    a, _ = top(df, df["age"], "Baseline: oldest first")
    b, ranked = top(df, risk(df, HI), "v1: risk score")
    c, _ = top(df, risk(df, HI_REVISE), "revise: heavier weak-heart weight")
    print(f"Overlap baseline vs v1: {len(a & b)}/{TOP}")
    print(f"Overlap v1 vs revise:   {len(b & c)}/{TOP}")
    print("\nTop of v1 (patient row, EF, creatinine, score):")
    print(ranked[["age", "ejection_fraction", "serum_creatinine", "DEATH_EVENT", "score"]].head(8).to_string())


if __name__ == "__main__":
    main()
