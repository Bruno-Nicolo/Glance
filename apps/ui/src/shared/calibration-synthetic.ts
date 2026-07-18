import type { CalibrationSample, CalibrationTarget } from './core-contract';

export function createSyntheticCalibrationSamples(
  target: CalibrationTarget,
  count = 15,
  startAtMs = Date.now(),
): CalibrationSample[] {
  const xRatio = clamp01((target.x - target.display.x) / target.display.width);
  const yRatio = clamp01((target.y - target.display.y) / target.display.height);

  return Array.from({ length: count }, (_, index) => {
    const offset = (index % 3) * 0.0025;
    const avgIrisX = clamp01(xRatio + offset);
    const avgIrisY = clamp01(yRatio - offset);

    return {
      sample_at_ms: startAtMs + index * 50,
      features: {
        left_iris_x: clamp01(avgIrisX - 0.01),
        left_iris_y: clamp01(avgIrisY + 0.005),
        right_iris_x: clamp01(avgIrisX + 0.01),
        right_iris_y: clamp01(avgIrisY - 0.005),
        avg_iris_x: avgIrisX,
        avg_iris_y: avgIrisY,
        face_center_x: clamp01(0.5 + (xRatio - 0.5) * 0.08),
        face_center_y: clamp01(0.5 + (yRatio - 0.5) * 0.08),
        face_scale: 0.37,
        head_yaw: (xRatio - 0.5) * 0.08,
        head_pitch: (0.5 - yRatio) * 0.06,
        head_roll: offset,
      },
      quality: {
        eye_openness: 0.92,
        landmark_stability: 0.88,
        face_stability: 0.9,
        left_right_divergence: 0.04,
        temporal_jitter: 0.03,
      },
    };
  });
}

function clamp01(value: number) {
  return Math.max(0, Math.min(1, Number(value.toFixed(6))));
}
