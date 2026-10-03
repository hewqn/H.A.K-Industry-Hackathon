import { useLayoutEffect, useMemo, useRef } from "react";
import { useFrame } from "@react-three/fiber";
import { useGLTF } from "@react-three/drei";
import * as THREE from "three";
import type { OrganIndicator } from "../types/patient";
import { getOrganLook, type ColorMode } from "../utils/organColors";

function applyMeshTint(
  material: THREE.Material,
  tint: THREE.Color,
  amount: number
) {
  if (!material.userData.tintUniforms) {
    const uniforms = {
      uTint: { value: tint.clone() },
      uTintAmount: { value: amount },
    };
    material.userData.tintUniforms = uniforms;
    const previous = material.onBeforeCompile;
    material.onBeforeCompile = (shader, renderer) => {
      previous?.call(material, shader, renderer);
      shader.uniforms.uTint = uniforms.uTint;
      shader.uniforms.uTintAmount = uniforms.uTintAmount;
      shader.fragmentShader =
        "uniform vec3 uTint;\nuniform float uTintAmount;\n" +
        shader.fragmentShader.replace(
          "#include <color_fragment>",
          `#include <color_fragment>
           diffuseColor.rgb = mix(diffuseColor.rgb, uTint, uTintAmount);`
        );
    };
    material.needsUpdate = true;
    return;
  }

  material.userData.tintUniforms.uTint.value.copy(tint);
  material.userData.tintUniforms.uTintAmount.value = amount;
}

interface OrganModelProps {
  url: string;
  organId: "heart" | "kidney";
  indicator: OrganIndicator;
  colorMode: ColorMode;
  riskScore?: number;
  position?: [number, number, number];
  scale?: number;
  onClick?: () => void;
  focused?: boolean;
  onReady?: () => void;
}

interface BakedModel {
  group: THREE.Group;
  before: { size: number[]; center: number[]; maxDim: number; meshes: number };
  after: { size: number[]; center: number[]; maxDim: number };
}

function bakeUnitModel(source: THREE.Object3D, label: string): BakedModel {
  source.updateWorldMatrix(true, true);

  const group = new THREE.Group();
  let meshes = 0;

  source.traverse((child) => {
    if (!(child instanceof THREE.Mesh) || !child.geometry) return;

    const geometry = child.geometry.clone();
    geometry.applyMatrix4(child.matrixWorld);
    geometry.computeBoundingBox();
    geometry.computeVertexNormals();

    const cloneMaterial = (item: THREE.Material) => {
      const cloned = item.clone();
      if ("color" in cloned && cloned.color instanceof THREE.Color) {
        cloned.userData.baseColor = cloned.color.clone();
      }
      if ("emissive" in cloned && cloned.emissive instanceof THREE.Color) {
        cloned.userData.baseEmissive = cloned.emissive.clone();
      }
      return cloned;
    };

    const material = Array.isArray(child.material)
      ? child.material.map(cloneMaterial)
      : cloneMaterial(child.material);

    const mesh = new THREE.Mesh(geometry, material);
    mesh.name = child.name;
    group.add(mesh);
    meshes += 1;
  });

  group.updateMatrixWorld(true);
  const beforeBox = new THREE.Box3().setFromObject(group);
  const beforeSize = beforeBox.getSize(new THREE.Vector3());
  const beforeCenter = beforeBox.getCenter(new THREE.Vector3());
  const maxDim = Math.max(beforeSize.x, beforeSize.y, beforeSize.z) || 1;

  const bake = new THREE.Matrix4()
    .makeScale(1 / maxDim, 1 / maxDim, 1 / maxDim)
    .multiply(
      new THREE.Matrix4().makeTranslation(
        -beforeCenter.x,
        -beforeCenter.y,
        -beforeCenter.z
      )
    );

  group.traverse((child) => {
    if (!(child instanceof THREE.Mesh)) return;
    child.geometry.applyMatrix4(bake);
    child.geometry.computeBoundingBox();
    child.geometry.computeBoundingSphere();
    child.position.set(0, 0, 0);
    child.rotation.set(0, 0, 0);
    child.scale.set(1, 1, 1);
  });

  group.position.set(0, 0, 0);
  group.rotation.set(0, 0, 0);
  group.scale.set(1, 1, 1);
  group.updateMatrixWorld(true);

  const afterBox = new THREE.Box3().setFromObject(group);
  const afterSize = afterBox.getSize(new THREE.Vector3());
  const afterCenter = afterBox.getCenter(new THREE.Vector3());

  const result: BakedModel = {
    group,
    before: {
      size: beforeSize.toArray(),
      center: beforeCenter.toArray(),
      maxDim,
      meshes,
    },
    after: {
      size: afterSize.toArray(),
      center: afterCenter.toArray(),
      maxDim: Math.max(afterSize.x, afterSize.y, afterSize.z),
    },
  };

  console.info(`[Organ bake] ${label}`, result.before, "→", result.after);
  return result;
}

export default function OrganModel({
  url,
  organId,
  indicator,
  colorMode,
  riskScore = 0,
  position = [0, 0, 0],
  scale = 1,
  onClick,
  focused = false,
  onReady,
}: OrganModelProps) {
  const { scene } = useGLTF(url);
  const baked = useMemo(() => bakeUnitModel(scene, organId), [scene, organId]);
  const groupRef = useRef<THREE.Group>(null);
  const hovered = useRef(false);
  const reduceMotion = useRef(
    typeof window !== "undefined" &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches
  );

  useFrame((_, delta) => {
    const group = groupRef.current;
    if (!group) return;

    const targetScale =
      scale * (focused ? 1.04 : 1) * (hovered.current ? 1.08 : 1);

    if (reduceMotion.current) {
      group.scale.setScalar(targetScale);
      return;
    }

    const t = 1 - Math.exp(-14 * delta);
    const nextScale = THREE.MathUtils.lerp(group.scale.x, targetScale, t);
    group.scale.setScalar(nextScale);
  });

  useLayoutEffect(() => {
    const look = getOrganLook(
      colorMode,
      organId === "heart" ? "heart" : "kidney_left",
      indicator,
      riskScore
    );

    baked.group.traverse((child) => {
      if (!(child instanceof THREE.Mesh)) return;
      const materials = Array.isArray(child.material)
        ? child.material
        : [child.material];
      for (const material of materials) {
        if ("color" in material && material.color instanceof THREE.Color) {
          const base =
            material.userData.baseColor instanceof THREE.Color
              ? material.userData.baseColor
              : new THREE.Color("#ffffff");
          material.color.copy(base);
        }
        if (
          "emissive" in material &&
          material.emissive instanceof THREE.Color &&
          material.userData.baseEmissive instanceof THREE.Color
        ) {
          material.emissive.copy(material.userData.baseEmissive);
        }
        applyMeshTint(material, look.tint, look.amount);
        if (organId === "kidney" && "roughness" in material) {
          // Kidney map is a flat 0.22. Three multiplies factor * map,
          // so 2.7 lands near the heart's 0.6 and keeps the authored map.
          material.roughness = 2.7;
        }
        material.transparent = false;
        material.opacity = 1;
      }
    });
  }, [baked, colorMode, indicator, organId, riskScore]);

  useLayoutEffect(() => {
    onReady?.();
  }, [onReady]);

  return (
    <group
      ref={groupRef}
      position={position}
      scale={scale}
      onClick={(event) => {
        event.stopPropagation();
        onClick?.();
      }}
      onPointerOver={(event) => {
        event.stopPropagation();
        hovered.current = true;
        document.body.style.cursor = "pointer";
      }}
      onPointerOut={() => {
        hovered.current = false;
        document.body.style.cursor = "default";
      }}
    >
      <primitive object={baked.group} />
    </group>
  );
}

useGLTF.preload("/models/human_heart.glb");
useGLTF.preload("/models/human_kidney.glb");
