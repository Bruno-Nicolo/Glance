import React, { useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import {
  CheckCircle2,
  Crosshair,
  ExternalLink,
  ListFilter,
  Power,
  RefreshCw,
  Square,
  Play,
  SlidersHorizontal,
  XCircle,
} from 'lucide-react';
import './styles.css';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { Separator } from '@/components/ui/separator';
import { Switch } from '@/components/ui/switch';
import { createSyntheticCalibrationSamples } from '../shared/calibration-synthetic';
import type {
  CalibrationCancelResponse,
  CalibrationCaptureResponse,
  CalibrationCompleteResponse,
  CalibrationMode,
  CalibrationSamplesRequest,
  CalibrationSession,
  CalibrationSessionRequest,
  CoreUiSettings,
  CoreUiSettingsUpdate,
  CoreUiStatus,
  DiagnosticComponent,
  DiagnosticLogEntry,
  DiagnosticLogRequest,
  HelperPermissionName,
  ShutdownResponse,
} from '../shared/core-contract';

declare global {
  interface Window {
    glance?: {
      getStatus: () => Promise<CoreUiStatus>;
      getSettings: () => Promise<CoreUiSettings>;
      updateSettings: (update: CoreUiSettingsUpdate) => Promise<CoreUiSettings>;
      startTracking: () => Promise<CoreUiStatus>;
      stopTracking: () => Promise<CoreUiStatus>;
      getDiagnosticLogs: () => Promise<{ entries: DiagnosticLogEntry[] }>;
      recordDiagnosticLog: (request: DiagnosticLogRequest) => Promise<void>;
      openPermissionSettings: (permission: HelperPermissionName) => Promise<void>;
      createCalibrationSession: (request: CalibrationSessionRequest) => Promise<CalibrationSession>;
      submitCalibrationSamples: (
        sessionId: string,
        request: CalibrationSamplesRequest,
      ) => Promise<CalibrationSession>;
      captureCalibrationSamples: (sessionId: string) => Promise<CalibrationCaptureResponse>;
      completeCalibrationSession: (sessionId: string) => Promise<CalibrationCompleteResponse>;
      cancelCalibrationSession: (sessionId: string) => Promise<CalibrationCancelResponse>;
      quitGlance: () => Promise<ShutdownResponse>;
    };
  }
}

type CalibrationRunState = {
  phase: 'idle' | 'initial' | 'validation' | 'drift' | 'complete' | 'cancelled';
  session: CalibrationSession | null;
  complete: CalibrationCompleteResponse | null;
};

type GlanceBridge = NonNullable<Window['glance']>;

function requireGlanceBridge(): GlanceBridge {
  if (!window.glance) {
    throw new Error('Glance preload bridge is unavailable. Restart the Electron dev server.');
  }

  return window.glance;
}

function App() {
  const [status, setStatus] = useState<CoreUiStatus | null>(null);
  const [settings, setSettings] = useState<CoreUiSettings | null>(null);
  const [calibrationRun, setCalibrationRun] = useState<CalibrationRunState>({
    phase: 'idle',
    session: null,
    complete: null,
  });
  const [diagnosticLogs, setDiagnosticLogs] = useState<DiagnosticLogEntry[]>([]);
  const [diagnosticFilter, setDiagnosticFilter] = useState<DiagnosticComponent | 'all'>('all');
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const glance = window.glance;
    if (!glance) {
      setError('Glance preload bridge is unavailable. Restart the Electron dev server.');
      return;
    }

    Promise.all([glance.getStatus(), glance.getSettings(), glance.getDiagnosticLogs()]).then(([
      nextStatus,
      nextSettings,
      nextLogs,
    ]) => {
      setStatus(nextStatus);
      setSettings(nextSettings);
      setDiagnosticLogs(nextLogs.entries);
      setError(null);
    }).catch((nextError: unknown) => {
      setStatus(null);
      setError(nextError instanceof Error ? nextError.message : 'Unable to connect to Glance Core');
    });
  }, []);

  async function refreshStatus() {
    try {
      const glance = requireGlanceBridge();
      const [nextStatus, nextSettings] = await Promise.all([
        glance.getStatus(),
        glance.getSettings(),
      ]);
      setStatus(nextStatus);
      setSettings(nextSettings);
      setError(null);
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : 'Unable to refresh status');
    }
  }

  async function refreshDiagnosticLogs() {
    try {
      const nextLogs = await requireGlanceBridge().getDiagnosticLogs();
      setDiagnosticLogs(nextLogs.entries);
      setError(null);
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : 'Unable to refresh diagnostics');
    }
  }

  async function recordRendererDiagnostic(
    severity: DiagnosticLogRequest['severity'],
    message: string,
    details?: Record<string, unknown>,
  ) {
    try {
      await requireGlanceBridge().recordDiagnosticLog({
        component: 'renderer',
        severity,
        message,
        details,
      });
      await refreshDiagnosticLogs();
    } catch {
      // Diagnostics must not break the runtime controls they are meant to inspect.
    }
  }

  async function openPermissionSettings(permission: HelperPermissionName) {
    try {
      await requireGlanceBridge().openPermissionSettings(permission);
      setError(null);
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : 'Unable to open macOS settings');
    }
  }

  async function startTracking() {
    try {
      await recordRendererDiagnostic('info', 'Start tracking requested from UI');
      setStatus(await requireGlanceBridge().startTracking());
      await refreshDiagnosticLogs();
      setError(null);
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : 'Unable to start tracking');
    }
  }

  async function stopTracking() {
    try {
      await recordRendererDiagnostic('info', 'Stop tracking requested from UI');
      setStatus(await requireGlanceBridge().stopTracking());
      await refreshDiagnosticLogs();
      setError(null);
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : 'Unable to stop tracking');
    }
  }

  async function toggleSpaceClick(enabled: boolean) {
    await updateSettings({ input: { space_click_enabled: enabled } });
  }

  async function toggleSyntheticGaze(enabled: boolean) {
    await updateSettings({ debug: { synthetic_gaze_enabled: enabled } });
  }

  async function setPauseBehavior(pause_behavior: CoreUiSettings['tracking']['pause_behavior']) {
    await updateSettings({ tracking: { pause_behavior } });
  }

  async function setConfidenceThreshold(confidence_threshold: number) {
    await updateSettings({ tracking: { confidence_threshold } });
  }

  async function setSmoothing(smoothing: number) {
    await updateSettings({ tracking: { smoothing } });
  }

  async function updateSettings(update: CoreUiSettingsUpdate) {
    try {
      setSettings(await requireGlanceBridge().updateSettings(update));
      await refreshDiagnosticLogs();
      setError(null);
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : 'Unable to update settings');
    }
  }

  async function startCalibration() {
    if (status && hasDeniedHelperPermissions(status)) {
      setError('Grant Accessibility and Input Monitoring permissions, then refresh status before calibrating.');
      return;
    }

    try {
      setError(null);
      const session = await requireGlanceBridge().createCalibrationSession({
        mode: 'initial-9-point',
        display_id: 'main',
      });
      await recordRendererDiagnostic('info', 'Initial calibration started from UI');
      setCalibrationRun({ phase: 'initial', session, complete: null });
      await refreshStatus();
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : 'Unable to start calibration');
    }
  }

  async function runDriftCorrection() {
    try {
      setError(null);
      const session = await requireGlanceBridge().createCalibrationSession({
        mode: 'drift-1-point',
        display_id: 'main',
      });
      await recordRendererDiagnostic('info', 'Drift correction started from UI');
      setCalibrationRun({ phase: 'drift', session, complete: null });
      await refreshStatus();
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : 'Unable to start drift correction');
    }
  }

  async function captureCalibrationTarget() {
    if (!calibrationRun.session) {
      return;
    }

    try {
      setError(null);
      const session = await requireGlanceBridge().captureCalibrationSamples(calibrationRun.session.session_id);
      setCalibrationRun({ ...calibrationRun, session });
      await refreshStatus();
      await refreshDiagnosticLogs();
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : 'Unable to capture calibration target');
    }
  }

  async function completeCalibration() {
    if (!calibrationRun.session) {
      return;
    }

    try {
      setError(null);
      const complete = await requireGlanceBridge().completeCalibrationSession(calibrationRun.session.session_id);
      if (complete.mode === 'initial-9-point') {
        const validation = await requireGlanceBridge().createCalibrationSession({
          mode: 'validation',
          display_id: 'main',
        });
        setCalibrationRun({ phase: 'validation', session: validation, complete: null });
        await refreshStatus();
        await refreshDiagnosticLogs();
        return;
      }
      setCalibrationRun({ phase: 'complete', session: null, complete });
      setStatus(complete.status);
      await refreshDiagnosticLogs();
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : 'Unable to complete calibration');
    }
  }

  async function runSyntheticCalibration() {
    try {
      setError(null);
      await updateSettings({ debug: { synthetic_gaze_enabled: true } });
      const initialComplete = await collectSyntheticCalibrationMode('initial-9-point', 'initial');
      const validationComplete = await collectSyntheticCalibrationMode('validation', 'validation');
      setCalibrationRun({ phase: 'complete', session: null, complete: validationComplete });
      setStatus(validationComplete.status);
      await refreshDiagnosticLogs();
      if (initialComplete.profile_id !== null || !validationComplete.profile_id) {
        throw new Error('Calibration did not produce a persisted profile');
      }
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : 'Unable to complete debug calibration');
    }
  }

  async function collectSyntheticCalibrationMode(
    mode: CalibrationMode,
    phase: CalibrationRunState['phase'],
  ) {
    const glance = requireGlanceBridge();
    let session = await glance.createCalibrationSession({ mode, display_id: 'main' });
    setCalibrationRun({ phase, session, complete: null });

    for (const target of session.targets) {
      session = await glance.submitCalibrationSamples(session.session_id, {
        target_id: target.id,
        samples: createSyntheticCalibrationSamples(target),
      });
      setCalibrationRun({ phase, session, complete: null });
    }

    return glance.completeCalibrationSession(session.session_id);
  }

  async function cancelCalibration() {
    if (!calibrationRun.session) {
      return;
    }

    try {
      const cancelled = await requireGlanceBridge().cancelCalibrationSession(calibrationRun.session.session_id);
      setStatus(cancelled.status);
      setCalibrationRun({ phase: 'cancelled', session: null, complete: null });
      await refreshDiagnosticLogs();
      setError(null);
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : 'Unable to cancel calibration');
    }
  }

  return (
    <main className="min-h-screen bg-background text-foreground">
      <section className="mx-auto grid min-h-screen w-full max-w-6xl gap-6 px-6 py-8 lg:grid-cols-[minmax(0,1fr)_420px] lg:px-10">
        <div className="flex flex-col justify-between gap-10 py-4">
          <div className="space-y-5">
            <Badge variant="secondary" className="w-fit">
              Glance MVP
            </Badge>
            <div className="max-w-2xl space-y-4">
              <h1 className="text-4xl font-semibold leading-tight tracking-normal sm:text-5xl lg:text-6xl">
                Eye tracking control for macOS
              </h1>
              <p className="max-w-xl text-base leading-7 text-muted-foreground">
                The UI stays thin: Python Core and Swift Helper own the runtime path.
              </p>
            </div>
          </div>

          <Card>
            <CardHeader>
              <CardTitle>Runtime Contract</CardTitle>
              <CardDescription>
                Electron reads status and settings through Core, never from runtime-critical internals.
              </CardDescription>
            </CardHeader>
            <CardContent className="grid gap-4 sm:grid-cols-3">
              <StatusMetric label="Core" value={status?.core.state ?? 'loading'} />
              <StatusMetric label="Helper" value={status?.helper.state ?? 'loading'} />
              <StatusMetric label="Calibration" value={status?.calibration.state ?? 'loading'} />
            </CardContent>
          </Card>
        </div>

        <div className="space-y-6 self-start lg:mt-4">
        <Card>
          <CardHeader className="gap-3">
            <div className="flex items-start justify-between gap-4">
              <div className="space-y-1.5">
                <CardTitle>Status</CardTitle>
                <CardDescription>Core/UI contract v{status?.contract_version ?? 1}</CardDescription>
              </div>
              <Button type="button" variant="outline" size="icon" onClick={refreshStatus} aria-label="Refresh status">
                <RefreshCw />
              </Button>
            </div>
          </CardHeader>
          <CardContent className="space-y-6">
            <div className="grid gap-3">
              <StatusRow label="Core" value={status?.core.state ?? 'loading'} />
              <StatusRow label="Helper" value={status?.helper.state ?? 'loading'} />
              <StatusRow label="Camera" value={status?.camera.state ?? 'loading'} />
              <StatusRow label="Tracking" value={status?.tracking.state ?? 'loading'} />
              <StatusRow label="Gaze" value={status?.gaze.status ?? 'loading'} />
              <StatusRow label="Source" value={status?.gaze.source ?? 'loading'} />
              <StatusRow
                label="Confidence"
                value={
                  status?.gaze.confidence === null || status?.gaze.confidence === undefined
                    ? 'pending'
                    : status.gaze.confidence.toFixed(2)
                }
              />
              <StatusRow
                label="Input"
                value={status?.tracking.input_enabled ? 'enabled' : 'disabled'}
              />
              <StatusRow
                label="UI runtime critical"
                value={status?.ui.runtime_critical ? 'yes' : 'no'}
              />
            </div>

            {status && hasDeniedHelperPermissions(status) ? (
              <PermissionPanel
                status={status}
                onOpenPermissionSettings={openPermissionSettings}
              />
            ) : null}

            <Separator />

            <div className="space-y-5">
              <div className="flex items-center justify-between gap-3">
                <div className="flex items-center gap-2 text-sm font-medium">
                  <Crosshair className="size-4" />
                  Calibration
                </div>
                <Badge variant="outline" className="capitalize">
                  {status?.calibration.state ?? 'loading'}
                </Badge>
              </div>

              <div className="relative aspect-[16/10] overflow-hidden border border-border bg-muted">
                {calibrationRun.session ? (
                  <TargetPreview session={calibrationRun.session} />
                ) : (
                  <div className="grid h-full place-items-center px-4 text-center text-sm text-muted-foreground">
                    {calibrationRun.complete?.profile_id ?? status?.calibration.profile_id ?? 'No profile'}
                  </div>
                )}
              </div>

              <div className="grid gap-2 text-sm">
                <StatusRow
                  label="Session"
                  value={calibrationRun.session?.mode ?? calibrationRun.phase}
                />
                <StatusRow
                  label="Progress"
                  value={
                    calibrationRun.session
                      ? `${Math.min(calibrationRun.session.current_target_index, calibrationRun.session.targets.length)}/${calibrationRun.session.targets.length}`
                      : '0/0'
                  }
                />
                <StatusRow
                  label="Mean error"
                  value={
                    calibrationRun.complete?.validation
                      ? `${calibrationRun.complete.validation.mean_error_px.toFixed(1)} px`
                      : 'pending'
                  }
                />
              </div>

              <div className="flex flex-wrap gap-2">
                <Button type="button" onClick={startCalibration}>
                  <CheckCircle2 />
                  Calibrate
                </Button>
                <Button
                  type="button"
                  variant="secondary"
                  onClick={captureCalibrationTarget}
                  disabled={!calibrationRun.session}
                >
                  <Crosshair />
                  Capture
                </Button>
                <Button
                  type="button"
                  variant="secondary"
                  onClick={completeCalibration}
                  disabled={
                    !calibrationRun.session
                    || calibrationRun.session.current_target_index < calibrationRun.session.targets.length
                  }
                >
                  <CheckCircle2 />
                  Complete
                </Button>
                <Button
                  type="button"
                  variant="secondary"
                  onClick={runDriftCorrection}
                  disabled={status?.calibration.state !== 'valid'}
                >
                  <Crosshair />
                  Drift
                </Button>
                <Button type="button" variant="outline" onClick={runSyntheticCalibration}>
                  <SlidersHorizontal />
                  Debug Synthetic
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  onClick={cancelCalibration}
                  disabled={!calibrationRun.session}
                >
                  <XCircle />
                  Cancel
                </Button>
              </div>
            </div>

            <Separator />

            <div className="space-y-5">
              <div className="flex items-center gap-2 text-sm font-medium">
                <SlidersHorizontal className="size-4" />
                Settings
              </div>

              <label className="grid gap-2 text-sm">
                <span className="font-medium">Pause behavior</span>
                <select
                  className="h-10 border border-input bg-background px-3 text-sm"
                  value={settings?.tracking.pause_behavior ?? 'fast-recovery'}
                  onChange={(event) => {
                    void setPauseBehavior(event.target.value as CoreUiSettings['tracking']['pause_behavior']);
                  }}
                >
                  <option value="fast-recovery">Fast recovery</option>
                  <option value="privacy-low-power">Privacy / low power</option>
                </select>
              </label>

              <SliderSetting
                label="Confidence threshold"
                value={settings?.tracking.confidence_threshold ?? 0.6}
                onChange={setConfidenceThreshold}
              />

              <SliderSetting
                label="Smoothing"
                value={settings?.tracking.smoothing ?? 0.5}
                onChange={setSmoothing}
              />

              <div className="flex items-center justify-between gap-4">
                <div className="space-y-1">
                  <p className="text-sm font-medium">Space click</p>
                  <p className="text-sm text-muted-foreground">Persisted by Python Core settings.</p>
                </div>
                <Switch
                  checked={settings?.input.space_click_enabled ?? false}
                  onCheckedChange={toggleSpaceClick}
                  aria-label="Toggle Space click"
                />
              </div>

              <div className="flex items-center justify-between gap-4">
                <div className="space-y-1">
                  <p className="text-sm font-medium">Synthetic gaze</p>
                  <p className="text-sm text-muted-foreground">Debug gaze source owned by Core.</p>
                </div>
                <Switch
                  checked={settings?.debug.synthetic_gaze_enabled ?? false}
                  onCheckedChange={toggleSyntheticGaze}
                  aria-label="Toggle synthetic gaze"
                />
              </div>

              <div className="flex flex-wrap gap-2">
                <Button type="button" onClick={startTracking}>
                  <Play />
                  Start
                </Button>
                <Button type="button" variant="secondary" onClick={stopTracking}>
                  <Square />
                  Stop
                </Button>
              </div>
            </div>

            {error ? (
              <p className="border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
                {error}
              </p>
            ) : null}

            <Button className="w-full" variant="destructive" type="button" onClick={() => {
              try {
                void requireGlanceBridge().recordDiagnosticLog({
                  component: 'renderer',
                  severity: 'info',
                  message: 'Full runtime shutdown requested from UI',
                });
                void requireGlanceBridge().quitGlance();
              } catch (nextError) {
                setError(nextError instanceof Error ? nextError.message : 'Unable to quit Glance');
              }
            }}>
              <Power />
              Quit Glance
            </Button>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="gap-3">
            <div className="flex items-start justify-between gap-4">
              <div className="space-y-1.5">
                <CardTitle>Diagnostics</CardTitle>
                <CardDescription>Privacy-preserving runtime logs from each component.</CardDescription>
              </div>
              <Button
                type="button"
                variant="outline"
                size="icon"
                onClick={refreshDiagnosticLogs}
                aria-label="Refresh diagnostics"
              >
                <RefreshCw />
              </Button>
            </div>
          </CardHeader>
          <CardContent className="space-y-4">
            <label className="grid gap-2 text-sm">
              <span className="flex items-center gap-2 font-medium">
                <ListFilter className="size-4" />
                Component
              </span>
              <select
                className="h-10 border border-input bg-background px-3 text-sm"
                value={diagnosticFilter}
                onChange={(event) => {
                  setDiagnosticFilter(event.target.value as DiagnosticComponent | 'all');
                }}
              >
                <option value="all">All</option>
                <option value="core">Core</option>
                <option value="helper">Helper</option>
                <option value="electron-main">Electron main</option>
                <option value="renderer">Renderer</option>
                <option value="camera">Camera</option>
                <option value="calibration">Calibration</option>
                <option value="tracking">Tracking</option>
              </select>
            </label>

            <div className="max-h-72 space-y-2 overflow-auto border border-border bg-muted p-3 font-mono text-xs">
              {diagnosticLogs.filter((entry) => (
                diagnosticFilter === 'all' || entry.component === diagnosticFilter
              )).length > 0 ? (
                diagnosticLogs.filter((entry) => (
                  diagnosticFilter === 'all' || entry.component === diagnosticFilter
                )).map((entry) => (
                  <div key={`${entry.timestamp_ms}-${entry.component}-${entry.message}`} className="grid gap-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="tabular-nums text-muted-foreground">
                        {new Date(entry.timestamp_ms).toLocaleTimeString()}
                      </span>
                      <Badge variant="outline" className="uppercase">
                        {entry.component}
                      </Badge>
                      <span className={severityClassName(entry.severity)}>{entry.severity}</span>
                    </div>
                    <p className="break-words text-foreground">{entry.message}</p>
                  </div>
                ))
              ) : (
                <p className="text-muted-foreground">No diagnostic logs</p>
              )}
            </div>
          </CardContent>
        </Card>
        </div>
      </section>
    </main>
  );
}

function severityClassName(severity: DiagnosticLogEntry['severity']) {
  if (severity === 'error') {
    return 'font-semibold text-destructive';
  }
  if (severity === 'warning') {
    return 'font-semibold text-amber-700';
  }
  return 'font-semibold text-muted-foreground';
}

function hasDeniedHelperPermissions(status: CoreUiStatus) {
  return status.helper.input.permissions.accessibility !== 'granted'
    || status.helper.input.permissions.input_monitoring !== 'granted';
}

function PermissionPanel({
  status,
  onOpenPermissionSettings,
}: {
  status: CoreUiStatus;
  onOpenPermissionSettings: (permission: HelperPermissionName) => Promise<void>;
}) {
  const permissions = status.helper.input.permissions;

  return (
    <div className="grid gap-3 border border-destructive/40 bg-destructive/10 p-3 text-sm">
      <div className="font-medium text-destructive">macOS permissions required</div>
      <PermissionAction
        label="Accessibility"
        value={permissions.accessibility}
        onClick={() => onOpenPermissionSettings('accessibility')}
      />
      <PermissionAction
        label="Input Monitoring"
        value={permissions.input_monitoring}
        onClick={() => onOpenPermissionSettings('input_monitoring')}
      />
    </div>
  );
}

function PermissionAction({
  label,
  value,
  onClick,
}: {
  label: string;
  value: string;
  onClick: () => Promise<void>;
}) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-3">
      <div className="flex items-center gap-2">
        <span>{label}</span>
        <Badge variant="outline" className="capitalize">
          {value}
        </Badge>
      </div>
      <Button type="button" variant="outline" size="sm" onClick={() => { void onClick(); }}>
        <ExternalLink />
        Open
      </Button>
    </div>
  );
}

function TargetPreview({ session }: { session: CalibrationSession }) {
  const target = session.targets[Math.min(session.current_target_index, session.targets.length - 1)];
  const left = ((target.x - target.display.x) / target.display.width) * 100;
  const top = ((target.y - target.display.y) / target.display.height) * 100;

  return (
    <div className="relative h-full">
      <div className="absolute inset-0 opacity-60 [background-image:linear-gradient(to_right,var(--border)_1px,transparent_1px),linear-gradient(to_bottom,var(--border)_1px,transparent_1px)] [background-size:20%_20%]" />
      <div
        className="absolute size-8 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-primary bg-background shadow"
        style={{ left: `${left}%`, top: `${top}%` }}
      >
        <span className="absolute left-1/2 top-1/2 size-2 -translate-x-1/2 -translate-y-1/2 rounded-full bg-primary" />
      </div>
      <div className="absolute bottom-3 left-3 right-3 flex items-center justify-between gap-3 text-xs text-muted-foreground">
        <span>{target.id}</span>
        <span>
          {session.current_target_index}/{session.targets.length}
        </span>
      </div>
    </div>
  );
}

function StatusMetric({ label, value }: { label: string; value: string }) {
  return (
    <div className="space-y-1">
      <p className="text-sm text-muted-foreground">{label}</p>
      <p className="text-lg font-semibold capitalize">{value}</p>
    </div>
  );
}

function StatusRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-4 text-sm">
      <span className="text-muted-foreground">{label}</span>
      <Badge variant="outline" className="capitalize">
        {value}
      </Badge>
    </div>
  );
}

function SliderSetting({
  label,
  value,
  onChange,
}: {
  label: string;
  value: number;
  onChange: (value: number) => Promise<void>;
}) {
  return (
    <label className="grid gap-2 text-sm">
      <span className="flex items-center justify-between gap-3">
        <span className="font-medium">{label}</span>
        <span className="tabular-nums text-muted-foreground">{value.toFixed(2)}</span>
      </span>
      <input
        className="w-full accent-primary"
        min={0}
        max={1}
        step={0.05}
        type="range"
        value={value}
        onChange={(event) => {
          void onChange(Number(event.target.value));
        }}
      />
    </label>
  );
}

createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
