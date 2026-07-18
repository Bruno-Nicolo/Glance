export type CoreUiStatus = {
  contract_version: number;
  core: {
    state: 'starting' | 'running' | 'shutting-down' | 'error';
    pid: number | null;
  };
  helper: {
    state: 'not-started' | 'running' | 'exited' | 'error';
  };
  camera: {
    state: 'stopped' | 'starting' | 'running' | 'error';
    active: boolean;
  };
  tracking: {
    state: 'stopped' | 'running' | 'paused' | 'error';
    input_enabled: boolean;
  };
  calibration: {
    state: 'missing' | 'in-progress' | 'valid' | 'error';
    profile_id: string | null;
  };
  ui: {
    runtime_critical: false;
  };
  error: CoreUiError | null;
};

export type CoreUiSettings = {
  contract_version: number;
  tracking: {
    pause_behavior: 'fast-recovery' | 'privacy-low-power';
    confidence_threshold: number;
    smoothing: number;
  };
  input: {
    space_click_enabled: boolean;
  };
  debug: {
    synthetic_gaze_enabled: boolean;
  };
};

export type CoreUiSettingsUpdate = {
  tracking?: Partial<CoreUiSettings['tracking']>;
  input?: Partial<CoreUiSettings['input']>;
  debug?: Partial<CoreUiSettings['debug']>;
};

export type CoreUiError = {
  code: string;
  message: string;
  recoverable: boolean;
};

export type ShutdownResponse = {
  status: 'shutting-down';
  scope: 'full-runtime';
  ui_should_exit: boolean;
};
