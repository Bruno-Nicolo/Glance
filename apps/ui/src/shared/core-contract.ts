export type CoreUiStatus = {
  contract_version: number;
  core: {
    state: 'starting' | 'running' | 'shutting-down' | 'error';
    pid: number | null;
  };
  helper: {
    state: 'not-started' | 'running' | 'exited' | 'error';
    input: {
      latest_action:
        | 'space-down'
        | 'space-up'
        | 'space-click'
        | 'esc-down'
        | 'esc-up'
        | 'pause-started'
        | 'pause-ended'
        | null;
      latest_suppressed_reason:
        | 'disabled'
        | 'paused'
        | 'permission-denied'
        | 'repeat'
        | 'no-cursor'
        | null;
      paused: boolean;
      permissions: {
        accessibility: 'granted' | 'denied' | 'unknown';
        input_monitoring: 'granted' | 'denied' | 'unknown';
      };
    };
  };
  camera: {
    state: 'stopped' | 'starting' | 'running' | 'error';
    active: boolean;
    metrics: {
      captured_frames: number;
      inference_results: number;
      emitted_samples: number;
      invalid_samples: number;
      dropped_frames: number;
      last_sample_at_ms: number | null;
      last_error: string | null;
      captured_fps: number;
      inference_fps: number;
      emitted_fps: number;
    } | null;
  };
  tracking: {
    state: 'stopped' | 'running' | 'paused' | 'error';
    input_enabled: boolean;
  };
  gaze: {
    contract_version: number;
    profile_id: string | null;
    status: 'valid' | 'low-confidence' | 'face-lost' | 'uncalibrated' | 'paused';
    confidence: number | null;
    sample_at_ms: number | null;
    source: 'synthetic' | 'camera';
    correction: 'idw-3x3';
    smoothing_alpha: number;
    confidence_threshold: number;
    invalid_reason:
      | 'face-lost'
      | 'uncalibrated'
      | 'paused'
      | 'synthetic-disabled'
      | 'tracking-stopped'
      | null;
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

export type CalibrationMode = 'initial-9-point' | 'validation' | 'drift-1-point';

export type CalibrationSessionState =
  | 'collecting'
  | 'processing'
  | 'complete'
  | 'cancelled'
  | 'error';

export type CalibrationTarget = {
  id: string;
  x: number;
  y: number;
  display: {
    id: string;
    x: number;
    y: number;
    width: number;
    height: number;
    scale: number;
    coordinate_space: 'display-logical-top-left';
  };
};

export type CalibrationSession = {
  contract_version: number;
  session_id: string;
  mode: CalibrationMode;
  state: CalibrationSessionState;
  current_target_index: number;
  targets: CalibrationTarget[];
  error: CoreUiError | null;
};

export type CalibrationSessionRequest = {
  mode: CalibrationMode;
  display_id: 'main';
};

export type CalibrationSample = {
  sample_at_ms: number;
  features: {
    left_iris_x: number;
    left_iris_y: number;
    right_iris_x: number;
    right_iris_y: number;
    avg_iris_x: number;
    avg_iris_y: number;
    face_center_x: number;
    face_center_y: number;
    face_scale: number;
    head_yaw: number;
    head_pitch: number;
    head_roll: number;
  };
  quality: {
    eye_openness: number;
    landmark_stability: number;
    face_stability: number;
    left_right_divergence: number;
    temporal_jitter: number;
  };
};

export type CalibrationSamplesRequest = {
  target_id: string;
  samples: CalibrationSample[];
};

export type CalibrationCompleteResponse = {
  contract_version: number;
  session_id: string;
  state: 'complete' | 'error';
  mode: CalibrationMode;
  profile_id: string | null;
  validation: {
    mode: 'validation-3-point' | 'validation-5-point' | 'drift-check-1-point';
    mean_error_px: number;
    median_error_px: number;
    max_error_px: number;
    accepted: boolean;
    mean_error_threshold_px: number;
    max_error_threshold_px: number;
    sample_count: number;
  } | null;
  status: CoreUiStatus;
  error: CoreUiError | null;
};

export type CalibrationCancelResponse = {
  contract_version: number;
  session_id: string;
  state: 'cancelled';
  status: CoreUiStatus;
  error: CoreUiError | null;
};
