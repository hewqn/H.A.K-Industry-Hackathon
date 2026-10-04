import * as THREE from "three";
import type { OrganId, OrganIndicator } from "../types/patient";

export type ColorMode = "anatomy" | "risk";

export interface OrganLook {
  tint: THREE.Color;
  amount: number;
}

export function clamp01(value: number): number {
  return Math.max(0, Math.min(1, value));
}

/** 0 = rich (left), 1 = pale (right). Matches the anatomy heart swatch. */
export function heartScalePosition(ef: number): number {
  return 1 - clamp01((ef - 14) / 46);
}

/** 0 = rich (left), 1 = pale (right). Matches the anatomy kidney swatch. */
export function kidneyScalePosition(creatinine: number): number {
  return clamp01((creatinine - 0.6) / 2.9);
}

/** EF weight + Cr 2 + anaemia/diabetes/HBP/age 1 each. */
export function pointsCeiling(heartWeight: number): number {
  return heartWeight + 6;
}

/** 0 = lower score (left), 1 = higher score (right). */
export function riskScalePosition(score: number, heartWeight = 2): number {
  return clamp01(score / pointsCeiling(heartWeight));
}

export function scoreScalePosition(
  score: number,
  kind: "points" | "model_output" | "age" | "combined",
  heartWeight = 2,
): number {
  if (kind === "model_output") return clamp01(score);
  if (kind === "points" || kind === "combined")
    return riskScalePosition(score, heartWeight);
  return 0;
}

function heatColor(amount: number): THREE.Color {
  const t = clamp01(amount);
  const green = new THREE.Color("#16c784");
  const amber = new THREE.Color("#e6b325");
  const red = new THREE.Color("#d12c2c");
  // Hold green longer so low risk still reads green on pink mesh.
  if (t < 0.38) {
    return green.lerp(amber, (t / 0.38) * 0.35);
  }
  if (t < 0.62) {
    return green.clone().lerp(amber, 0.35).lerp(amber, (t - 0.38) / 0.24);
  }
  return amber.lerp(red, (t - 0.62) / 0.38);
}

/**
 * Tissue State: rich→pale from EF / creatinine.
 * Risk Score: green→red from frozen ML heart_risk / kidney_risk.
 */
export function getOrganLook(
  mode: ColorMode,
  organId: OrganId,
  indicator: OrganIndicator,
  organHeat?: number,
): OrganLook {
  if (mode === "risk") {
    if (organHeat == null) {
      return { tint: new THREE.Color("#ffffff"), amount: 0 };
    }
    const heat = clamp01(organHeat);
    return {
      tint: heatColor(heat),
      amount: 0.72 + heat * 0.18,
    };
  }

  if (indicator.value === null) {
    return { tint: new THREE.Color("#c8c4be"), amount: 0.4 };
  }

  const pale =
    organId === "heart"
      ? heartScalePosition(indicator.value)
      : kidneyScalePosition(indicator.value);

  const rich =
    organId === "heart"
      ? new THREE.Color("#c4786a")
      : new THREE.Color("#b24a42");
  const bloodless =
    organId === "heart"
      ? new THREE.Color("#efe6e1")
      : new THREE.Color("#e8ddd8");

  return {
    tint: rich.lerp(bloodless, pale),
    amount: 0.36 + pale * 0.56,
  };
}
