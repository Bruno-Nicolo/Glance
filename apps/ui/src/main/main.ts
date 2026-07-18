import { app, BrowserWindow, ipcMain } from 'electron';
import { spawn, type ChildProcess } from 'node:child_process';
import path from 'node:path';
import WebSocket from 'ws';
import {
  cleanStaleRuntimeMarkers,
  defaultRuntimePath,
  fetchCore,
  findRepoRoot,
  isCoreHealthy,
  readCoreConnection,
  shouldKeepRuntimeAliveOnUiQuit,
  startCoreProcess,
  waitForHealthyCore,
  type CoreConnection,
} from './core-lifecycle';
import type {
  CalibrationCancelResponse,
  CalibrationCompleteResponse,
  CalibrationSamplesRequest,
  CalibrationSession,
  CalibrationSessionRequest,
  CoreUiSettings,
  CoreUiSettingsUpdate,
  CoreUiStatus,
  ShutdownResponse,
} from '../shared/core-contract';

let mainWindow: BrowserWindow | null = null;
let coreClient: CoreClient | null = null;
let allowFullQuit = false;

const runtimePath = defaultRuntimePath();

class CoreClient {
  private connection: CoreConnection | null = null;
  private process: ChildProcess | null = null;
  private events: WebSocket | null = null;

  async ensureConnected() {
    const existing = await readCoreConnection(runtimePath);
    if (existing && (await isCoreHealthy(existing))) {
      this.connection = existing;
      this.openEvents(existing);
      return existing;
    }

    await cleanStaleRuntimeMarkers(runtimePath);
    this.startCore();
    const started = await waitForHealthyCore({ runtimePath });
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

  async createCalibrationSession(request: CalibrationSessionRequest): Promise<CalibrationSession> {
    const connection = await this.ensureConnected();
    const response = await fetchCore(connection, '/calibration/sessions', {
      method: 'POST',
      body: JSON.stringify(request),
      headers: { 'Content-Type': 'application/json' },
    });
    if (!response.ok) {
      throw new Error(`Core calibration session failed with ${response.status}`);
    }

    return (await response.json()) as CalibrationSession;
  }

  async submitCalibrationSamples(
    sessionId: string,
    request: CalibrationSamplesRequest,
  ): Promise<CalibrationSession> {
    const connection = await this.ensureConnected();
    const response = await fetchCore(connection, `/calibration/sessions/${sessionId}/samples`, {
      method: 'POST',
      body: JSON.stringify(request),
      headers: { 'Content-Type': 'application/json' },
    });
    if (!response.ok) {
      throw new Error(`Core calibration samples failed with ${response.status}`);
    }

    return (await response.json()) as CalibrationSession;
  }

  async completeCalibrationSession(sessionId: string): Promise<CalibrationCompleteResponse> {
    const connection = await this.ensureConnected();
    const response = await fetchCore(connection, `/calibration/sessions/${sessionId}/complete`, {
      method: 'POST',
    });
    if (!response.ok) {
      throw new Error(`Core calibration complete failed with ${response.status}`);
    }

    return (await response.json()) as CalibrationCompleteResponse;
  }

  async cancelCalibrationSession(sessionId: string): Promise<CalibrationCancelResponse> {
    const connection = await this.ensureConnected();
    const response = await fetchCore(connection, `/calibration/sessions/${sessionId}`, {
      method: 'DELETE',
    });
    if (!response.ok) {
      throw new Error(`Core calibration cancel failed with ${response.status}`);
    }

    return (await response.json()) as CalibrationCancelResponse;
  }

  async quitGlance() {
    const connection = await this.ensureConnected();
    const response = await fetchCore(connection, '/shutdown', { method: 'POST' });
    if (!response.ok) {
      throw new Error(`Core shutdown failed with ${response.status}`);
    }

    return (await response.json()) as ShutdownResponse;
  }

  private startCore() {
    if (this.process) {
      return;
    }

    const repoRoot = findRepoRoot([process.cwd(), app.getAppPath(), __dirname]);
    const child = startCoreProcess(repoRoot, spawn);

    this.process = child;
    child.once('exit', () => {
      this.process = null;
      this.connection = null;
    });
    child.unref();
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
  ipcMain.handle('glance:createCalibrationSession', async (_event, request: CalibrationSessionRequest) => (
    coreClient?.createCalibrationSession(request)
  ));
  ipcMain.handle(
    'glance:submitCalibrationSamples',
    async (_event, sessionId: string, request: CalibrationSamplesRequest) => (
      coreClient?.submitCalibrationSamples(sessionId, request)
    ),
  );
  ipcMain.handle('glance:completeCalibrationSession', async (_event, sessionId: string) => (
    coreClient?.completeCalibrationSession(sessionId)
  ));
  ipcMain.handle('glance:cancelCalibrationSession', async (_event, sessionId: string) => (
    coreClient?.cancelCalibrationSession(sessionId)
  ));
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
  if (shouldKeepRuntimeAliveOnUiQuit(process.platform, allowFullQuit)) {
    event.preventDefault();
    mainWindow?.close();
  }
});

app.on('activate', () => {
  if (mainWindow === null) {
    createWindow();
  }
});
