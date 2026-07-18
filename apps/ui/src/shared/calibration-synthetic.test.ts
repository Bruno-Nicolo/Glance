import test from 'node:test';
import assert from 'node:assert/strict';

import { createSyntheticCalibrationSamples } from './calibration-synthetic';
import type { CalibrationTarget } from './core-contract';

test('createSyntheticCalibrationSamples creates contract-shaped samples near the target', () => {
  const target: CalibrationTarget = {
    id: 'top-right',
    x: 1296,
    y: 90,
    display: {
      id: 'main',
      x: 0,
      y: 0,
      width: 1440,
      height: 900,
      scale: 2,
      coordinate_space: 'display-logical-top-left',
    },
  };

  const samples = createSyntheticCalibrationSamples(target, 4, 1721300000000);

  assert.equal(samples.length, 4);
  assert.deepEqual(Object.keys(samples[0].features), [
    'left_iris_x',
    'left_iris_y',
    'right_iris_x',
    'right_iris_y',
    'avg_iris_x',
    'avg_iris_y',
    'face_center_x',
    'face_center_y',
    'face_scale',
    'head_yaw',
    'head_pitch',
    'head_roll',
  ]);
  assert.equal(samples[0].features.avg_iris_x, 0.9);
  assert.equal(samples[0].features.avg_iris_y, 0.1);
  assert.equal(samples[3].sample_at_ms, 1721300000150);
  assert.equal(samples[0].quality.eye_openness, 0.92);
});

test('createSyntheticCalibrationSamples defaults to roughly 700 ms per target', () => {
  const target: CalibrationTarget = {
    id: 'center',
    x: 720,
    y: 450,
    display: {
      id: 'main',
      x: 0,
      y: 0,
      width: 1440,
      height: 900,
      scale: 2,
      coordinate_space: 'display-logical-top-left',
    },
  };

  const samples = createSyntheticCalibrationSamples(target, undefined, 1721300000000);

  assert.equal(samples.length, 15);
  assert.equal(samples.at(-1)?.sample_at_ms, 1721300000700);
});
