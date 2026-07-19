import path from 'node:path';
import test from 'node:test';
import assert from 'node:assert/strict';

import { resolvePreloadScriptPath } from './window-paths';

test('resolvePreloadScriptPath points at the Forge Vite preload bundle beside main.js', () => {
  assert.equal(
    resolvePreloadScriptPath(path.join('apps', 'ui', '.vite', 'build')),
    path.join('apps', 'ui', '.vite', 'build', 'preload.js'),
  );
});
