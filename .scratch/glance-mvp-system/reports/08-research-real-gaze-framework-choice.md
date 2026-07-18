# Real Gaze Framework Choice for MVP 1

Date: 2026-07-18

## Recommendation

Use **MediaPipe Face Landmarker Tasks for Python plus OpenCV `VideoCapture`**, not a third-party gaze cursor library.

The MVP 1 real-camera slice should:

1. Capture frames with `opencv-python` and `cv2.VideoCapture(0)`.
2. Run MediaPipe Face Landmarker in `LIVE_STREAM` mode with `num_faces=1`.
3. Enable facial transformation matrices if the mapping slice needs a first-party head-pose signal.
4. Extract normalized landmark features from the 478-landmark face result, especially iris/eye-relative positions, face center/scale, and head orientation.
5. Feed those features into Glance's own 9-point calibrated regression/correction/smoothing pipeline.

This fits ADR 0001: Python Core owns webcam, MediaPipe/OpenCV, gaze estimation, calibration, smoothing, confidence, and emits the existing `gaze.sample` contract at a target 30 FPS. It also avoids training a custom model because MediaPipe provides pre-trained, ready-to-run models through MediaPipe Solutions and Tasks. Sources: [ADR 0001](../../../docs/adr/0001-glance-mvp-architecture.md), [MediaPipe PyPI project description](https://pypi.org/project/mediapipe/), [MediaPipe Face Landmarker Python guide](https://developers.google.com/edge/mediapipe/solutions/vision/face_landmarker/python), [MediaPipe Face Landmarker overview](https://developers.google.com/edge/mediapipe/solutions/vision/face_landmarker), [OpenCV VideoCapture docs](https://docs.opencv.org/4.x/d8/dfe/classcv_1_1VideoCapture.html).

Important nuance: MediaPipe gives the ready-made **face/iris perception layer**, not final screen gaze. Google's Iris docs explicitly say iris tracking does not infer where a person is looking. The Glance-specific calibrated regression remains necessary for screen coordinates. Source: [MediaPipe Iris docs](https://github.com/google-ai-edge/mediapipe/blob/master/docs/solutions/iris.md).

## Why This Approach

MediaPipe Face Landmarker accepts decoded video frames and live video feeds, and returns a complete face mesh, optional blendshapes, and optional facial transformation matrices. Source: [Face Landmarker overview](https://developers.google.com/edge/mediapipe/solutions/vision/face_landmarker).

The Face Landmarker model bundle includes face detection, face mesh, and blendshape models, and the face mesh output is 478 three-dimensional landmarks. Source: [Face Landmarker overview](https://developers.google.com/edge/mediapipe/solutions/vision/face_landmarker).

The older MediaPipe Iris documentation is still useful as first-party source context for iris landmarks: the iris pipeline adds 10 iris landmarks to 468 face landmarks for 478 total landmarks, tracks iris/pupil/eye-contour landmarks from a single RGB camera in real time, and has desktop CPU/GPU example graphs. It also warns that iris tracking does not itself infer gaze target. Source: [MediaPipe Iris docs](https://github.com/google-ai-edge/mediapipe/blob/master/docs/solutions/iris.md).

MediaPipe's Python guide explicitly says webcam/live-stream frames can be loaded with an external library such as OpenCV, converted to `mediapipe.Image`, and processed with `detect_for_video` or `detect_async`; `LIVE_STREAM` returns immediately, invokes a callback when a result is ready, and ignores a new frame if the task is still busy. Sources: [Face Landmarker Python guide](https://developers.google.com/edge/mediapipe/solutions/vision/face_landmarker/python), [OpenCV VideoCapture docs](https://docs.opencv.org/4.x/d8/dfe/classcv_1_1VideoCapture.html).

For MVP 1, use `LIVE_STREAM` mode for the production camera loop so inference cannot build a stale queue behind cursor motion. `VIDEO` mode remains useful for deterministic tests, recorded-file evaluation, or a short debugging spike, but not as the primary runtime loop. In `VIDEO` and `LIVE_STREAM` modes, MediaPipe uses tracking to avoid running the model on every frame, which the docs say helps reduce latency. Source: [Face Landmarker Python guide](https://developers.google.com/edge/mediapipe/solutions/vision/face_landmarker/python).

## Rejected Candidates

### EyeGestures

Rejected for MVP 1 as the main engine. EyeGestures is an open-source gaze tracking library using native webcams and camera input, but its repo is GPL-3.0 licensed, its Python package depends on a broader stack including MediaPipe, OpenCV contrib, scikit-learn, PyAutoGUI, pynput, pygame, and keyboard, and its own README warns that some users report MediaPipe, scikit-learn, or OpenCV do not install together with EyeGestures. That is too much dependency and licensing surface for Glance's Python Core slice. Sources: [EyeGestures README](https://github.com/NativeSensors/EyeGestures), [EyeGestures pyproject](https://raw.githubusercontent.com/NativeSensors/EyeGestures/main/pyproject.toml).

### GazeTracking by Antoine Lame

Rejected. It is a webcam-based Python eye tracking library that reports pupil coordinates and coarse left/right/center/up/down ratios, but it is OpenCV plus dlib rather than MediaPipe/OpenCV, has no published GitHub releases, and its pyproject depends on `dlib>=20.0`. Glance already committed to MediaPipe/OpenCV and needs calibrated screen coordinates, not only categorical gaze direction ratios. Sources: [GazeTracking README](https://github.com/antoinelame/GazeTracking), [GazeTracking pyproject](https://raw.githubusercontent.com/antoinelame/GazeTracking/master/pyproject.toml), [ADR 0001](../../../docs/adr/0001-glance-mvp-architecture.md).

### OpenFace

Rejected for the MVP 1 real-camera slice. OpenFace includes eye-gaze estimation, real-time webcam use, and source for training/running models, but it is a larger C++/MATLAB/C#/CMake research toolkit with its latest GitHub release listed as OpenFace 2.2.0 from July 13, 2019. It also introduces dlib/OpenBLAS/OpenCV and dataset/model-license considerations. Glance needs a small Python Core dependency path with pip-installable MediaPipe/OpenCV. Sources: [OpenFace README](https://github.com/TadasBaltrusaitis/OpenFace), [OpenFace releases metadata on GitHub](https://github.com/TadasBaltrusaitis/OpenFace).

### Raw MediaPipe Iris Desktop Graphs

Rejected as the main integration path. The legacy Iris docs expose CPU/GPU desktop graphs and targets, but the docs say legacy solutions were upgraded to new MediaPipe Solutions, and the desktop path is Bazel graph/application oriented. Glance's Python Core should use the current MediaPipe Tasks Python API unless a measured blocker appears. Sources: [MediaPipe Iris docs](https://github.com/google-ai-edge/mediapipe/blob/master/docs/solutions/iris.md), [MediaPipe setup guide for Python](https://developers.google.com/edge/mediapipe/solutions/setup_python).

## macOS Install and Runtime Constraints

Use a Python version supported by both MediaPipe and OpenCV wheels. MediaPipe's PyPI classifiers for 0.10.35 list Python 3.9, 3.10, 3.11, and 3.12 and macOS; its release page shows a macOS 11.0+ ARM64 wheel. MediaPipe's setup guide says Python 3.9+ and pip 20.3+ are required. Sources: [MediaPipe PyPI](https://pypi.org/project/mediapipe/), [MediaPipe setup guide for Python](https://developers.google.com/edge/mediapipe/solutions/setup_python).

Avoid Python 3.13 for MVP 1 unless MediaPipe wheel support is re-verified during dependency locking. The current MediaPipe PyPI classifiers do not list Python 3.13, even though OpenCV's wheel repo supports newer Python versions. Sources: [MediaPipe PyPI](https://pypi.org/project/mediapipe/), [opencv-python README](https://github.com/opencv/opencv-python).

Use `opencv-python`, not `opencv-python-headless`, because this is a desktop macOS app that needs camera/video I/O. The OpenCV wheel README says there are four package variants, only one should be installed in an environment because they all share the `cv2` namespace, and the standard desktop package is `opencv-python`; headless variants are for server environments and omit GUI dependencies. Source: [opencv-python README](https://github.com/opencv/opencv-python).

OpenCV's `VideoCapture` opens cameras by index and `read()` grabs, decodes, and returns the next frame. It supports selecting an API backend, with `CAP_ANY` as auto-detect. OpenCV's configuration docs say AVFoundation is the Apple backend and can capture frames from camera and encode/decode video files. Sources: [OpenCV VideoCapture docs](https://docs.opencv.org/4.x/d8/dfe/classcv_1_1VideoCapture.html), [OpenCV configuration reference](https://docs.opencv.org/4.x/db/d05/tutorial_config_reference.html).

The Face Landmarker task requires a local `.task` model path via `BaseOptions(model_asset_path=...)`. The repo should vendor or download/pin the model in a deterministic setup step rather than fetching it at runtime. Source: [Face Landmarker Python guide](https://developers.google.com/edge/mediapipe/solutions/vision/face_landmarker/python).

## Camera Permission Implications

macOS 10.14 and later requires the user to grant each app camera permission before camera access. The system shows an app-specific alert on first camera use, remembers the user's response, and lets the user change it later in system privacy settings. Source: [Apple: Requesting authorization to capture and save media](https://developer.apple.com/documentation/avfoundation/requesting-authorization-to-capture-and-save-media).

For a packaged macOS app, Apple requires `NSCameraUsageDescription` in `Info.plist`. If the app uses App Sandbox or Hardened Runtime resource access restrictions, it also needs the camera entitlement (`com.apple.security.device.camera`) on the executable that may interact with built-in or external cameras. Sources: [NSCameraUsageDescription](https://developer.apple.com/documentation/bundleresources/information-property-list/nscamerausagedescription), [Apple camera entitlement](https://developer.apple.com/documentation/bundleresources/entitlements/com.apple.security.device.camera), [Apple: Requesting authorization to capture and save media](https://developer.apple.com/documentation/avfoundation/requesting-authorization-to-capture-and-save-media).

Apple's AVFoundation API exposes `authorizationStatus(for:)` and `requestAccess(for:completionHandler:)`; if authorization is not determined, apps should request access before capture setup. Source: [AVCaptureDevice authorization docs](https://developer.apple.com/documentation/AVFoundation/AVCaptureDevice/authorizationStatus%28for%3A%29).

For Glance, the awkward MVP reality is that Python/OpenCV is the process opening the camera. During development, the camera grant may attach to Terminal, the Python binary, or the launching app depending on how Core is started and packaged. The real-camera slice should therefore expose a distinct `permission-denied` or `camera-unavailable` state through Core status, and packaging work must verify which signed bundle owns the TCC prompt when Electron launches Python Core. This is an implementation risk inferred from Apple's per-app camera permission model and Glance's three-process architecture. Sources: [ADR 0001](../../../docs/adr/0001-glance-mvp-architecture.md), [Apple: Requesting authorization to capture and save media](https://developer.apple.com/documentation/avfoundation/requesting-authorization-to-capture-and-save-media), [OpenCV VideoCapture docs](https://docs.opencv.org/4.x/d8/dfe/classcv_1_1VideoCapture.html).

## Expected Performance Relative to 30 FPS

30 FPS is plausible but must be measured on target Macs. MediaPipe Iris is described by Google as real-time on a single RGB camera, and MediaPipe has desktop CPU/GPU iris examples. Face Landmarker supports live video feeds, has a `LIVE_STREAM` mode, and uses tracking in video/live-stream modes to reduce latency. Sources: [MediaPipe Iris docs](https://github.com/google-ai-edge/mediapipe/blob/master/docs/solutions/iris.md), [Face Landmarker overview](https://developers.google.com/edge/mediapipe/solutions/vision/face_landmarker), [Face Landmarker Python guide](https://developers.google.com/edge/mediapipe/solutions/vision/face_landmarker/python).

The implementation should not assume exact 33 ms frame pacing. The existing Core-to-Helper contract already says the Helper treats the stream as best effort and renders the newest valid non-stale sample. Source: [Core-to-Helper event contract issue](../issues/02-define-core-helper-event-contract.md).

Recommended MVP performance target:

- Request camera frames at 640x480 or 720p only if measured latency leaves enough budget.
- Emit at most one `gaze.sample` per completed MediaPipe result.
- If using `LIVE_STREAM`, expect dropped frames when inference is busy because MediaPipe ignores new input in that condition.
- Report measured capture FPS, inference FPS, emitted gaze FPS, and dropped/invalid sample counts in the real-camera slice report.

## Risks for Real-Camera Slice

- **MediaPipe landmarks are not screen gaze.** The final screen coordinate quality depends on calibration/regression/correction, not the model alone. Source: [MediaPipe Iris docs](https://github.com/google-ai-edge/mediapipe/blob/master/docs/solutions/iris.md).
- **Packaging can fail on Python version drift.** MediaPipe currently lists support through Python 3.12 on PyPI, while OpenCV supports newer Python versions; dependency locking should choose the intersection. Sources: [MediaPipe PyPI](https://pypi.org/project/mediapipe/), [opencv-python README](https://github.com/opencv/opencv-python).
- **macOS camera permission ownership is a slice blocker until tested from the real launch path.** Apple permissions are per app, while Glance has Electron, Python Core, and Swift Helper processes. Sources: [Apple camera authorization docs](https://developer.apple.com/documentation/avfoundation/requesting-authorization-to-capture-and-save-media), [ADR 0001](../../../docs/adr/0001-glance-mvp-architecture.md).
- **Frame pacing may be bursty.** MediaPipe `LIVE_STREAM` can drop input frames when busy, and OpenCV camera properties can vary by backend/device. Sources: [Face Landmarker Python guide](https://developers.google.com/edge/mediapipe/solutions/vision/face_landmarker/python), [OpenCV VideoCapture docs](https://docs.opencv.org/4.x/d8/dfe/classcv_1_1VideoCapture.html).
- **Third-party gaze libraries add unwanted surface area.** EyeGestures has a broad dependency stack and GPL-3.0 license, GazeTracking brings dlib and coarse ratios, and OpenFace is a heavier research toolkit. Sources: [EyeGestures README](https://github.com/NativeSensors/EyeGestures), [EyeGestures pyproject](https://raw.githubusercontent.com/NativeSensors/EyeGestures/main/pyproject.toml), [GazeTracking README](https://github.com/antoinelame/GazeTracking), [GazeTracking pyproject](https://raw.githubusercontent.com/antoinelame/GazeTracking/master/pyproject.toml), [OpenFace README](https://github.com/TadasBaltrusaitis/OpenFace).

## Fallback Plan

If Face Landmarker Tasks Python cannot meet the measured MVP target, fall back to the legacy MediaPipe Face Mesh/Iris Python solution or desktop iris graph only as an implementation workaround, while preserving the same extracted feature contract and `gaze.sample` event shape. The fallback should be triggered only by measurement: install failure on supported macOS/Python, missing iris landmarks in the Tasks path, or sustained emitted gaze below 20 FPS after reducing input resolution. Sources: [MediaPipe Iris docs](https://github.com/google-ai-edge/mediapipe/blob/master/docs/solutions/iris.md), [Face Landmarker Python guide](https://developers.google.com/edge/mediapipe/solutions/vision/face_landmarker/python), [Core-to-Helper event contract issue](../issues/02-define-core-helper-event-contract.md).

## Decision

Proceed with **MediaPipe Face Landmarker Tasks Python + OpenCV `VideoCapture`** for MVP 1. Treat MediaPipe as the pre-trained landmark/iris/head-pose provider; treat Glance's calibration mapper as the actual gaze-to-screen estimator.
