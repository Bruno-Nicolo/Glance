import type { ChildProcess } from 'node:child_process';
import fs from 'node:fs';
import fsp from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';

export type CoreConnection = {
  port: number;
  token: string;
};

export type CoreRuntimeFiles = {
  runtimePath: string;
  pidPath: string;
  lockPath: string;
  portPath: string;
  tokenPath: string;
};

export type CoreProcessSpawner = (python: string, args: string[], options: {
  cwd: string;
  detached: true;
  env: NodeJS.ProcessEnv;
  stdio: 'ignore';
}) => ChildProcess;

export type CoreLifecycleOptions = {
  runtimePath?: string;
  fetch?: typeof fetch;
  sleep?: (ms: number) => Promise<void>;
};

export function defaultRuntimePath() {
  return path.join(
    os.homedir(),
    'Library',
    'Application Support',
    'Glance',
    'runtime',
  );
}

export function coreRuntimeFiles(runtimePath = defaultRuntimePath()): CoreRuntimeFiles {
  return {
    runtimePath,
    pidPath: path.join(runtimePath, 'core.pid'),
    lockPath: path.join(runtimePath, 'core.lock'),
    portPath: path.join(runtimePath, 'core.port'),
    tokenPath: path.join(runtimePath, 'core.token'),
  };
}

export async function readCoreConnection(runtimePath = defaultRuntimePath()): Promise<CoreConnection | null> {
  const files = coreRuntimeFiles(runtimePath);
  try {
    const [portText, token] = await Promise.all([
      fsp.readFile(files.portPath, 'utf8'),
      fsp.readFile(files.tokenPath, 'utf8'),
    ]);

    const port = Number.parseInt(portText.trim(), 10);
    const trimmedToken = token.trim();
    if (!Number.isInteger(port) || port <= 0 || trimmedToken.length === 0) {
      return null;
    }

    return { port, token: trimmedToken };
  } catch {
    return null;
  }
}

export async function cleanStaleRuntimeMarkers(runtimePath = defaultRuntimePath()) {
  const files = coreRuntimeFiles(runtimePath);
  await Promise.all([
    unlinkIfPresent(files.pidPath),
    unlinkIfPresent(files.lockPath),
    unlinkIfPresent(files.portPath),
  ]);
}

export async function fetchCore(
  connection: CoreConnection,
  route: string,
  init: RequestInit = {},
  requestFetch: typeof fetch = fetch,
) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 900);

  try {
    return await requestFetch(`http://127.0.0.1:${connection.port}${route}`, {
      ...init,
      headers: {
        Authorization: `Bearer ${connection.token}`,
        ...(init.headers ?? {}),
      },
      signal: controller.signal,
    });
  } finally {
    clearTimeout(timeout);
  }
}

export async function isCoreHealthy(
  connection: CoreConnection,
  requestFetch: typeof fetch = fetch,
) {
  try {
    const response = await fetchCore(connection, '/health', {}, requestFetch);
    return response.ok;
  } catch {
    return false;
  }
}

export function findRepoRoot(candidates: string[]) {
  for (const candidate of candidates) {
    let current = candidate;
    for (let depth = 0; depth < 8; depth += 1) {
      if (fs.existsSync(path.join(current, 'core', 'pyproject.toml'))) {
        return current;
      }

      const parent = path.dirname(current);
      if (parent === current) {
        break;
      }
      current = parent;
    }
  }

  return path.resolve(candidates[0] ?? process.cwd(), '../..');
}

export function resolvePython(repoRoot: string, explicitPython?: string) {
  if (explicitPython) {
    return explicitPython;
  }

  const venvPython = path.join(repoRoot, '.venv', 'bin', 'python');
  return fs.existsSync(venvPython) ? venvPython : 'python3';
}

export function startCoreProcess(
  repoRoot: string,
  spawnCore: CoreProcessSpawner,
  explicitPython?: string,
) {
  const python = resolvePython(repoRoot, explicitPython);
  return spawnCore(python, ['-m', 'glance_core'], {
    cwd: repoRoot,
    detached: true,
    env: {
      ...process.env,
      PYTHONPATH: path.join(repoRoot, 'core', 'src'),
    },
    stdio: 'ignore',
  });
}

export async function waitForHealthyCore(options: CoreLifecycleOptions = {}) {
  const requestFetch = options.fetch ?? fetch;
  const sleep = options.sleep ?? ((ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms)));
  const runtimePath = options.runtimePath ?? defaultRuntimePath();
  const deadline = Date.now() + 10_000;

  while (Date.now() < deadline) {
    const connection = await readCoreConnection(runtimePath);
    if (connection && (await isCoreHealthy(connection, requestFetch))) {
      return connection;
    }

    await sleep(250);
  }

  throw new Error('Timed out waiting for Glance Core');
}

export function shouldKeepRuntimeAliveOnUiQuit(platform: NodeJS.Platform, allowFullQuit: boolean) {
  return platform === 'darwin' && !allowFullQuit;
}

async function unlinkIfPresent(filePath: string) {
  try {
    await fsp.unlink(filePath);
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code !== 'ENOENT') {
      throw error;
    }
  }
}
