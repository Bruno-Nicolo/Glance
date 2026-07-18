import { spawnSync } from 'node:child_process';
import fs from 'node:fs';
import fsp from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';
import assert from 'node:assert/strict';

import {
  cleanStaleRuntimeMarkers,
  coreRuntimeFiles,
  fetchCore,
  readCoreConnection,
  shouldKeepRuntimeAliveOnUiQuit,
  startCoreProcess,
  waitForHealthyCore,
} from './core-lifecycle';

test('readCoreConnection reads trimmed authenticated runtime discovery files', async () => {
  const runtimePath = await makeRuntimeDir();
  await fsp.writeFile(path.join(runtimePath, 'core.port'), ' 32123\n');
  await fsp.writeFile(path.join(runtimePath, 'core.token'), ' token-value\n');

  const connection = await readCoreConnection(runtimePath);

  assert.deepEqual(connection, { port: 32123, token: 'token-value' });
});

test('readCoreConnection rejects missing, invalid, or empty discovery files', async () => {
  const runtimePath = await makeRuntimeDir();
  await fsp.writeFile(path.join(runtimePath, 'core.port'), 'not-a-port');
  await fsp.writeFile(path.join(runtimePath, 'core.token'), 'token-value');

  assert.equal(await readCoreConnection(runtimePath), null);

  await fsp.writeFile(path.join(runtimePath, 'core.port'), '32123');
  await fsp.writeFile(path.join(runtimePath, 'core.token'), ' \n');

  assert.equal(await readCoreConnection(runtimePath), null);
});

test('fetchCore sends bearer auth to the resolved localhost Core route', async () => {
  const requests: Array<{ url: string; authorization: string | null }> = [];
  const fakeFetch = (async (url: string | URL | Request, init?: RequestInit) => {
    requests.push({
      url: String(url),
      authorization: new Headers(init?.headers).get('Authorization'),
    });
    return new Response('{}', { status: 200 });
  }) as typeof fetch;

  const response = await fetchCore({ port: 49152, token: 'secret' }, '/status', {}, fakeFetch);

  assert.equal(response.ok, true);
  assert.deepEqual(requests, [
    {
      url: 'http://127.0.0.1:49152/status',
      authorization: 'Bearer secret',
    },
  ]);
});

test('cleanStaleRuntimeMarkers removes stale pid, lock, and port but keeps token', async () => {
  const runtimePath = await makeRuntimeDir();
  const files = coreRuntimeFiles(runtimePath);
  await Promise.all([
    fsp.writeFile(files.pidPath, '111'),
    fsp.writeFile(files.lockPath, ''),
    fsp.writeFile(files.portPath, '49152'),
    fsp.writeFile(files.tokenPath, 'token-value'),
  ]);

  await cleanStaleRuntimeMarkers(runtimePath);

  assert.equal(fs.existsSync(files.pidPath), false);
  assert.equal(fs.existsSync(files.lockPath), false);
  assert.equal(fs.existsSync(files.portPath), false);
  assert.equal(fs.existsSync(files.tokenPath), true);
});

test('waitForHealthyCore waits until runtime files point to a healthy Core', async () => {
  const runtimePath = await makeRuntimeDir();
  let checks = 0;
  const fakeFetch = (async () => {
    checks += 1;
    if (checks === 2) {
      return new Response('{}', { status: 200 });
    }
    throw new Error('not ready yet');
  }) as typeof fetch;

  await fsp.writeFile(path.join(runtimePath, 'core.port'), '49152');
  await fsp.writeFile(path.join(runtimePath, 'core.token'), 'token-value');

  const connection = await waitForHealthyCore({
    runtimePath,
    fetch: fakeFetch,
    sleep: async () => {},
  });

  assert.deepEqual(connection, { port: 49152, token: 'token-value' });
  assert.equal(checks, 2);
});

test('startCoreProcess launches the Python Core module detached from the UI', async () => {
  const repoRoot = await makeRepoRoot();
  const calls: Array<{
    python: string;
    args: string[];
    cwd: string;
    detached: true;
    pyPath: string | undefined;
    stdio: 'ignore';
  }> = [];

  startCoreProcess(repoRoot, (python, args, options) => {
    calls.push({
      python,
      args,
      cwd: options.cwd,
      detached: options.detached,
      pyPath: options.env.PYTHONPATH,
      stdio: options.stdio,
    });
    return spawnSync(process.execPath, ['--version']) as never;
  }, '/custom/python');

  assert.deepEqual(calls, [
    {
      python: '/custom/python',
      args: ['-m', 'glance_core'],
      cwd: repoRoot,
      detached: true,
      pyPath: path.join(repoRoot, 'core', 'src'),
      stdio: 'ignore',
    },
  ]);
});

test('darwin UI quit keeps Core and Helper alive unless Quit Glance was requested', () => {
  assert.equal(shouldKeepRuntimeAliveOnUiQuit('darwin', false), true);
  assert.equal(shouldKeepRuntimeAliveOnUiQuit('darwin', true), false);
  assert.equal(shouldKeepRuntimeAliveOnUiQuit('linux', false), false);
});

async function makeRuntimeDir() {
  return fsp.mkdtemp(path.join(os.tmpdir(), 'glance-runtime-'));
}

async function makeRepoRoot() {
  const repoRoot = await fsp.mkdtemp(path.join(os.tmpdir(), 'glance-repo-'));
  await fsp.mkdir(path.join(repoRoot, 'core'), { recursive: true });
  await fsp.writeFile(path.join(repoRoot, 'core', 'pyproject.toml'), '');
  return repoRoot;
}
