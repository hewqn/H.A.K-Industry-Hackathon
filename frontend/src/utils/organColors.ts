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

/** 0 = lower score (left), 1 = higher score (right). */
export function riskScalePosition(score: number): number {
  return clamp01(score / 8);
}

function heatColor(amount: number): THREE.Color {
  const t = clamp01(amount);
  if (t < 0.5) {
    return new THREE.Color("#1f8a5b").lerp(new THREE.Color("#e6b325"), t * 2);
  }
  return new THREE.Color("#e6b325").lerp(new THREE.Color("#d12c2c"), (t - 0.5) * 2);
}

/**
 * Anatomy: mix toward pale grey from the recorded value.
 * Heart uses ejection fraction (low EF = paler).
 * Kidneys use creatinine (high Cr = paler).
 * amount 0 keeps the authored texture (rich).
 *
 * Risk: mix toward green → red from that organ's own risk
 * (points placeholder now, ML organ_risk later).
 */
export function getOrganLook(
  mode: ColorMode,
  organId: OrganId,
  indicator: OrganIndicator,
  organHeat = 0
): OrganLook {
  if (mode === "anatomy") {
    if (indicator.value === null) {
      return { tint: new THREE.Color("#c8c4be"), amount: 0.4 };
    }

    const paleAmount =
      organId === "heart"
        ? heartScalePosition(indicator.value)
        : kidneyScalePosition(indicator.value);

    return {
      tint:
        organId === "heart"
          ? new THREE.Color("#edd4ca")
          : new THREE.Color("#c9847a"),
      amount: paleAmount * 0.32,
    };
  }

  const heat = clamp01(organHeat);
  return {
    tint: heatColor(heat),
    amount: 0.3 + heat * 0.25,
  };
}
