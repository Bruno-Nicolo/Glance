import React, { useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { CheckCircle2, Crosshair, Power, RefreshCw, Square, Play, SlidersHorizontal, XCircle } from 'lucide-react';
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
  CalibrationCompleteResponse,
  CalibrationMode,
  CalibrationSamplesRequest,
  CalibrationSession,
  CalibrationSessionRequest,
  CoreUiSettings,
  CoreUiSettingsUpdate,
  CoreUiStatus,
  ShutdownResponse,
} from '../shared/core-contract';

declare global {
  interface Window {
    glance: {
      getStatus: () => Promise<CoreUiStatus>;
      getSettings: () => Promise<CoreUiSettings>;
      updateSettings: (update: CoreUiSettingsUpdate) => Promise<CoreUiSettings>;
      startTracking: () => Promise<CoreUiStatus>;
      stopTracking: () => Promise<CoreUiStatus>;
      createCalibrationSession: (request: CalibrationSessionRequest) => Promise<CalibrationSession>;
      submitCalibrationSamples: (
        sessionId: string,
        request: CalibrationSamplesRequest,
      ) => Promise<CalibrationSession>;
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

function App() {
  const [status, setStatus] = useState<CoreUiStatus | null>(null);
  const [settings, setSettings] = useState<CoreUiSettings | null>(null);
  const [calibrationRun, setCalibrationRun] = useState<CalibrationRunState>({
    phase: 'idle',
    session: null,
    complete: null,
  });
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([window.glance.getStatus(), window.glance.getSettings()]).then(([nextStatus, nextSettings]) => {
      setStatus(nextStatus);
      setSettings(nextSettings);
      setError(null);
    }).catch((nextError: unknown) => {
      setStatus(null);
      setError(nextError instanceof Error ? nextError.message : 'Unable to connect to Glance Core');
    });
  }, []);

  async function refreshStatus() {
    try {
      const [nextStatus, nextSettings] = await Promise.all([
        window.glance.getStatus(),
        window.glance.getSettings(),
      ]);
      setStatus(nextStatus);
      setSettings(nextSettings);
      setError(null);
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : 'Unable to refresh status');
    }
  }

  async function startTracking() {
    try {
      setStatus(await window.glance.startTracking());
      setError(null);
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : 'Unable to start tracking');
    }
  }

  async function stopTracking() {
    try {
      setStatus(await window.glance.stopTracking());
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
      setSettings(await window.glance.updateSettings(update));
      setError(null);
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : 'Unable to update settings');
    }
  }

  async function runSyntheticCalibration() {
    try {
      setError(null);
      const initialComplete = await collectCalibrationMode('initial-9-point', 'initial');
      const validationComplete = await collectCalibrationMode('validation', 'validation');
      setCalibrationRun({ phase: 'complete', session: null, complete: validationComplete });
      setStatus(validationComplete.status);
      if (initialComplete.profile_id !== null || !validationComplete.profile_id) {
        throw new Error('Calibration did not produce a persisted profile');
      }
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : 'Unable to complete calibration');
    }
  }

  async function runDriftCorrection() {
    try {
      setError(null);
      const complete = await collectCalibrationMode('drift-1-point', 'drift');
      setCalibrationRun({ phase: 'complete', session: null, complete });
      setStatus(complete.status);
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : 'Unable to complete drift correction');
    }
  }

  async function collectCalibrationMode(
    mode: CalibrationMode,
    phase: CalibrationRunState['phase'],
  ) {
    let session = await window.glance.createCalibrationSession({ mode, display_id: 'main' });
    setCalibrationRun({ phase, session, complete: null });

    for (const target of session.targets) {
      session = await window.glance.submitCalibrationSamples(session.session_id, {
        target_id: target.id,
        samples: createSyntheticCalibrationSamples(target),
      });
      setCalibrationRun({ phase, session, complete: null });
    }

    return window.glance.completeCalibrationSession(session.session_id);
  }

  async function cancelCalibration() {
    if (!calibrationRun.session) {
      return;
    }

    try {
      const cancelled = await window.glance.cancelCalibrationSession(calibrationRun.session.session_id);
      setStatus(cancelled.status);
      setCalibrationRun({ phase: 'cancelled', session: null, complete: null });
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

        <Card className="self-start lg:mt-4">
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
              <StatusRow
                label="Input"
                value={status?.tracking.input_enabled ? 'enabled' : 'disabled'}
              />
              <StatusRow
                label="UI runtime critical"
                value={status?.ui.runtime_critical ? 'yes' : 'no'}
              />
            </div>

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
                <Button type="button" onClick={runSyntheticCalibration}>
                  <CheckCircle2 />
                  Calibrate
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

            <Button className="w-full" variant="destructive" type="button" onClick={() => window.glance.quitGlance()}>
              <Power />
              Quit Glance
            </Button>
          </CardContent>
        </Card>
      </section>
    </main>
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
