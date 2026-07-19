import path from 'node:path';

export function resolvePreloadScriptPath(mainBundleDir: string) {
  return path.join(mainBundleDir, 'preload.js');
}
