import { app, BrowserWindow, ipcMain } from 'electron';
import { spawn, type ChildProcess } from 'node:child_process';
import fs from 'node:fs';
import fsp from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import WebSocket from 'ws';
import type {
  CoreUiSettings,
  CoreUiSettingsUpdate,
  CoreUiStatus,
  ShutdownResponse,
} from '../shared/core-contract';

let mainWindow: BrowserWindow | null = null;
let coreClient: CoreClient | null = null;
let allowFullQuit = false;

type CoreConnection = {
  port: number;
  token: string;
};

const runtimePath = path.join(
  os.homedir(),
  'Library',
  'Application Support',
  'Glance',
  'runtime',
);

function findRepoRoot() {
  const candidates = [process.cwd(), app.getAppPath(), __dirname];

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

  return path.resolve(app.getAppPath(), '../..');
}

async function readCoreConnection(): Promise<CoreConnection | null> {
  try {
    const [portText, token] = await Promise.all([
      fsp.readFile(path.join(runtimePath, 'core.port'), 'utf8'),
      fsp.readFile(path.join(runtimePath, 'core.token'), 'utf8'),
    ]);

    const port = Number.parseInt(portText.trim(), 10);
    if (!Number.isInteger(port) || port <= 0) {
      return null;
    }

    return { port, token: token.trim() };
  } catch {
    return null;
  }
}

async function fetchCore(
  connection: CoreConnection,
  route: string,
  init: RequestInit = {},
) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 900);

  try {
    return await fetch(`http://127.0.0.1:${connection.port}${route}`, {
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

class CoreClient {
  private connection: CoreConnection | null = null;
  private process: ChildProcess | null = null;
  private events: WebSocket | null = null;

  async ensureConnected() {
    const existing = await readCoreConnection();
    if (existing && (await this.isHealthy(existing))) {
      this.connection = existing;
      this.openEvents(existing);
      return existing;
    }

    this.startCore();
    const started = await this.waitForCore();
    this.connection = started;
    this.openEvents(started);
    return started;
  }

  async getStatus(): Promise<CoreUiStatus> {
    const connection = await this.ensureConnected();
    const response = await fetchCore(connection, '/status');
    if (!response.ok) {
      throw new Error(`Core status failed with ${response.status}`);
    }

    return (await response.json()) as CoreUiStatus;
  }

  async getSettings(): Promise<CoreUiSettings> {
    const connection = await this.ensureConnected();
    const response = await fetchCore(connection, '/settings');
    if (!response.ok) {
      throw new Error(`Core settings failed with ${response.status}`);
    }

    return (await response.json()) as CoreUiSettings;
  }

  async updateSettings(update: CoreUiSettingsUpdate): Promise<CoreUiSettings> {
    const connection = await this.ensureConnected();
    const response = await fetchCore(connection, '/settings', {
      method: 'PUT',
      body: JSON.stringify(update),
      headers: { 'Content-Type': 'application/json' },
    });
    if (!response.ok) {
      throw new Error(`Core settings update failed with ${response.status}`);
    }

    return (await response.json()) as CoreUiSettings;
  }

  async startTracking(): Promise<CoreUiStatus> {
    const connection = await this.ensureConnected();
    const response = await fetchCore(connection, '/controls/start', { method: 'POST' });
    if (!response.ok) {
      throw new Error(`Core start failed with ${response.status}`);
    }

    return (await response.json()) as CoreUiStatus;
  }

  async stopTracking(): Promise<CoreUiStatus> {
    const connection = await this.ensureConnected();
    const response = await fetchCore(connection, '/controls/stop', { method: 'POST' });
    if (!response.ok) {
      throw new Error(`Core stop failed with ${response.status}`);
    }

    return (await response.json()) as CoreUiStatus;
  }

  async quitGlance() {
    const connection = await this.ensureConnected();
    const response = await fetchCore(connection, '/shutdown', { method: 'POST' });
    if (!response.ok) {
      throw new Error(`Core shutdown failed with ${response.status}`);
    }

    return (await response.json()) as ShutdownResponse;
  }

  private async isHealthy(connection: CoreConnection) {
    try {
      const response = await fetchCore(connection, '/health');
      return response.ok;
    } catch {
      return false;
    }
  }

  private startCore() {
    if (this.process) {
      return;
    }

    const repoRoot = findRepoRoot();
    const venvPython = path.join(repoRoot, '.venv', 'bin', 'python');
    const python = fs.existsSync(venvPython) ? venvPython : 'python3';

    const child = spawn(python, ['-m', 'glance_core'], {
      cwd: repoRoot,
      detached: true,
      env: {
        ...process.env,
        PYTHONPATH: path.join(repoRoot, 'core', 'src'),
      },
      stdio: 'ignore',
    });

    this.process = child;
    child.once('exit', () => {
      this.process = null;
      this.connection = null;
    });
    child.unref();
  }

  private async waitForCore() {
    const deadline = Date.now() + 10_000;

    while (Date.now() < deadline) {
      const connection = await readCoreConnection();
      if (connection && (await this.isHealthy(connection))) {
        return connection;
      }

      await new Promise((resolve) => setTimeout(resolve, 250));
    }

    throw new Error('Timed out waiting for Glance Core');
  }

  private openEvents(connection: CoreConnection) {
    if (this.events?.readyState === WebSocket.OPEN || this.events?.readyState === WebSocket.CONNECTING) {
      return;
    }

    this.events = new WebSocket(`ws://127.0.0.1:${connection.port}/ui/events`, {
      headers: { Authorization: `Bearer ${connection.token}` },
    });

    this.events.on('close', () => {
      this.events = null;
    });
  }
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 960,
    height: 680,
    title: 'Glance',
    webPreferences: {
      preload: path.join(__dirname, '../preload/preload.js'),
    },
  });

  if (MAIN_WINDOW_VITE_DEV_SERVER_URL) {
    mainWindow.loadURL(MAIN_WINDOW_VITE_DEV_SERVER_URL);
  } else {
    mainWindow.loadFile(path.join(__dirname, `../renderer/${MAIN_WINDOW_VITE_NAME}/index.html`));
  }

  mainWindow.on('closed', () => {
    mainWindow = null;
  });
}

app.whenReady().then(() => {
  coreClient = new CoreClient();

  ipcMain.handle('glance:getStatus', async () => coreClient?.getStatus());
  ipcMain.handle('glance:getSettings', async () => coreClient?.getSettings());
  ipcMain.handle('glance:updateSettings', async (_event, update: CoreUiSettingsUpdate) => (
    coreClient?.updateSettings(update)
  ));
  ipcMain.handle('glance:startTracking', async () => coreClient?.startTracking());
  ipcMain.handle('glance:stopTracking', async () => coreClient?.stopTracking());
  ipcMain.handle('glance:quitGlance', async () => {
    await coreClient?.quitGlance();
    allowFullQuit = true;
    app.quit();
  });

  createWindow();
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit();
  }
});

app.on('before-quit', (event) => {
  if (process.platform === 'darwin' && !allowFullQuit) {
    event.preventDefault();
    mainWindow?.close();
  }
});

app.on('activate', () => {
  if (mainWindow === null) {
    createWindow();
  }
});
