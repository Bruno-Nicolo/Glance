import AppKit
import Foundation

enum HelperEventContract {
    static let version = 1
    static let targetFPS = 30
    static let staleSampleMilliseconds = 150
    static let coordinateSpace = "display-logical-top-left"
    static let gazeStatuses = Set([
        "valid",
        "low-confidence",
        "face-lost",
        "uncalibrated",
        "paused"
    ])
    static let gazeSources = Set(["synthetic", "camera"])
    static let trackingStates = Set(["running", "paused", "stopped"])
    static let overlayStates = Set(["visible", "hidden", "frozen"])
}

struct HelperEventEnvelope: Decodable {
    let type: String
    let version: Int
    let sentAtMilliseconds: Int64
    let sequence: Int

    enum CodingKeys: String, CodingKey {
        case type
        case version
        case sentAtMilliseconds = "sent_at_ms"
        case sequence
    }
}

struct DisplayBounds: Codable {
    let id: String
    let x: Double
    let y: Double
    let width: Double
    let height: Double
    let scale: Double
    let coordinateSpace: String

    enum CodingKeys: String, CodingKey {
        case id
        case x
        case y
        case width
        case height
        case scale
        case coordinateSpace = "coordinate_space"
    }
}

struct CursorSnapshot: Encodable {
    let x: Double
    let y: Double
    let display: DisplayBounds
}

struct CoreReadyEvent: Decodable {
    let type: String
    let version: Int
    let sentAtMilliseconds: Int64
    let sequence: Int
    let minVersion: Int
    let targetFPS: Int
    let staleSampleMilliseconds: Int

    enum CodingKeys: String, CodingKey {
        case type
        case version
        case sentAtMilliseconds = "sent_at_ms"
        case sequence
        case minVersion = "min_version"
        case targetFPS = "target_fps"
        case staleSampleMilliseconds = "stale_sample_ms"
    }
}

struct GazeSampleEvent: Decodable {
    let type: String
    let version: Int
    let sentAtMilliseconds: Int64
    let sequence: Int
    let sampleAtMilliseconds: Int64
    let x: Double
    let y: Double
    let display: DisplayBounds
    let confidence: Double
    let status: String
    let source: String

    enum CodingKeys: String, CodingKey {
        case type
        case version
        case sentAtMilliseconds = "sent_at_ms"
        case sequence
        case sampleAtMilliseconds = "sample_at_ms"
        case x
        case y
        case display
        case confidence
        case status
        case source
    }
}

struct TrackingStatusEvent: Decodable {
    let type: String
    let version: Int
    let sentAtMilliseconds: Int64
    let sequence: Int
    let tracking: String
    let overlay: String
    let reason: String?

    enum CodingKeys: String, CodingKey {
        case type
        case version
        case sentAtMilliseconds = "sent_at_ms"
        case sequence
        case tracking
        case overlay
        case reason
    }
}

struct CoreSettings: Decodable {
    let tracking: TrackingSettings
    let input: InputSettings

    struct TrackingSettings: Decodable {
        let pauseBehavior: String

        enum CodingKeys: String, CodingKey {
            case pauseBehavior = "pause_behavior"
        }
    }

    struct InputSettings: Decodable {
        let spaceClickEnabled: Bool

        enum CodingKeys: String, CodingKey {
            case spaceClickEnabled = "space_click_enabled"
        }
    }
}

struct HelperInputEvent: Encodable {
    let type = "helper.input"
    let version = HelperEventContract.version
    let sentAtMilliseconds: Int64
    let sequence: Int
    let action: String
    let cursor: CursorSnapshot?
    let suppressedReason: String?

    enum CodingKeys: String, CodingKey {
        case type
        case version
        case sentAtMilliseconds = "sent_at_ms"
        case sequence
        case action
        case cursor
        case suppressedReason = "suppressed_reason"
    }
}

struct HelperPermissionEvent: Encodable {
    let type = "helper.permission"
    let version = HelperEventContract.version
    let sentAtMilliseconds: Int64
    let sequence: Int
    let permission: String
    let state: String
    let requiredFor: [String]
    let recoverable = true

    enum CodingKeys: String, CodingKey {
        case type
        case version
        case sentAtMilliseconds = "sent_at_ms"
        case sequence
        case permission
        case state
        case requiredFor = "required_for"
        case recoverable
    }
}

final class AppDelegate: NSObject, NSApplicationDelegate {
    private var overlayWindow: NSWindow?
    private var overlayView: CursorOverlayView?
    private var coreSocket: CoreSocket?
    private var inputController: HelperInputController?
    private var settingsRefreshTimer: Timer?

    func applicationDidFinishLaunching(_ notification: Notification) {
        NSApp.setActivationPolicy(.accessory)
        createOverlayWindow()
        connectToCore()
        print("GlanceHelper ready")
    }

    private func createOverlayWindow() {
        guard let screen = NSScreen.main else { return }

        let window = NSWindow(
            contentRect: screen.frame,
            styleMask: [.borderless],
            backing: .buffered,
            defer: false
        )
        window.backgroundColor = .clear
        window.isOpaque = false
        window.ignoresMouseEvents = true
        window.level = .floating
        window.collectionBehavior = [.canJoinAllSpaces, .stationary, .ignoresCycle]
        let cursorView = CursorOverlayView(frame: screen.frame)
        window.contentView = cursorView
        overlayView = cursorView
        window.orderFrontRegardless()
        overlayWindow = window
    }

    private func connectToCore() {
        guard
            let urlText = ProcessInfo.processInfo.environment["GLANCE_CORE_WS_URL"],
            let token = ProcessInfo.processInfo.environment["GLANCE_CORE_TOKEN"],
            let url = URL(string: urlText)
        else {
            print("GlanceHelper missing Core connection environment")
            return
        }
        let coreURL = ProcessInfo.processInfo.environment["GLANCE_CORE_URL"].flatMap(URL.init(string:))

        coreSocket = CoreSocket(
            url: url,
            coreURL: coreURL,
            token: token,
            onGazeSample: { [weak self] event in
                self?.overlayView?.apply(gazeSample: event)
            },
            onTrackingStatus: { [weak self] event in
                self?.overlayView?.apply(trackingStatus: event)
            },
            onSettings: { [weak self] settings in
                self?.inputController?.spaceClickEnabled = settings.input.spaceClickEnabled
                self?.inputController?.pauseBehavior = settings.tracking.pauseBehavior
            }
        )
        coreSocket?.connect()
        if let overlayView, let coreSocket {
            inputController = HelperInputController(overlayView: overlayView, coreSocket: coreSocket)
            inputController?.start()
        }
        settingsRefreshTimer = Timer.scheduledTimer(withTimeInterval: 1, repeats: true) { [weak self] _ in
            self?.coreSocket?.refreshSettings()
        }
    }
}

final class CursorOverlayView: NSView {
    private var cursorPosition: CGPoint?
    private var cursorDisplay: DisplayBounds?
    private var overlayState: String = "visible"
    private var trackingState: String = "stopped"

    override var isFlipped: Bool { true }

    func apply(gazeSample event: GazeSampleEvent) {
        guard overlayState == "visible" else { return }
        guard event.status == "valid" || event.status == "low-confidence" else { return }
        guard !Self.isStale(gazeSample: event) else { return }

        let localPoint = CGPoint(
            x: event.x - event.display.x,
            y: event.y - event.display.y
        )
        cursorPosition = CGPoint(
            x: min(max(localPoint.x, bounds.minX), bounds.maxX),
            y: min(max(localPoint.y, bounds.minY), bounds.maxY)
        )
        cursorDisplay = event.display
        needsDisplay = true
    }

    func apply(trackingStatus event: TrackingStatusEvent) {
        trackingState = event.tracking
        overlayState = event.overlay
        isHidden = event.overlay == "hidden" || cursorPosition == nil
        needsDisplay = true
    }

    func pause(behavior: String) {
        overlayState = behavior == "privacy-low-power" || cursorPosition == nil ? "hidden" : "frozen"
        isHidden = overlayState == "hidden"
        needsDisplay = true
    }

    func resume() {
        overlayState = trackingState == "running" ? "visible" : "hidden"
        isHidden = overlayState == "hidden" || cursorPosition == nil
        needsDisplay = true
    }

    func latestCursor() -> CursorSnapshot? {
        guard let cursorPosition, let cursorDisplay else { return nil }
        return CursorSnapshot(
            x: cursorDisplay.x + cursorPosition.x,
            y: cursorDisplay.y + cursorPosition.y,
            display: cursorDisplay
        )
    }

    func trackingInputEnabled(spaceClickEnabled: Bool) -> Bool {
        trackingState == "running" && spaceClickEnabled
    }

    private static func isStale(gazeSample event: GazeSampleEvent) -> Bool {
        let nowMilliseconds = Int64(Date().timeIntervalSince1970 * 1000)
        return nowMilliseconds - event.sampleAtMilliseconds
            > HelperEventContract.staleSampleMilliseconds
    }

    override func draw(_ dirtyRect: NSRect) {
        guard overlayState != "hidden" else { return }
        guard let cursorPosition else { return }

        NSColor.clear.setFill()
        dirtyRect.fill()

        let radius: CGFloat = 12
        let rect = CGRect(
            x: cursorPosition.x - radius,
            y: cursorPosition.y - radius,
            width: radius * 2,
            height: radius * 2
        )
        NSColor.systemBlue.withAlphaComponent(0.88).setFill()
        NSBezierPath(ovalIn: rect).fill()
    }
}

final class CoreSocket {
    private let url: URL
    private let coreURL: URL?
    private let token: String
    private let onGazeSample: (GazeSampleEvent) -> Void
    private let onTrackingStatus: (TrackingStatusEvent) -> Void
    private let onSettings: (CoreSettings) -> Void
    private var task: URLSessionWebSocketTask?
    private let decoder = JSONDecoder()
    private let encoder = JSONEncoder()
    private var helperSequence = 0

    init(
        url: URL,
        coreURL: URL?,
        token: String,
        onGazeSample: @escaping (GazeSampleEvent) -> Void,
        onTrackingStatus: @escaping (TrackingStatusEvent) -> Void,
        onSettings: @escaping (CoreSettings) -> Void
    ) {
        self.url = url
        self.coreURL = coreURL
        self.token = token
        self.onGazeSample = onGazeSample
        self.onTrackingStatus = onTrackingStatus
        self.onSettings = onSettings
    }

    func connect() {
        var request = URLRequest(url: url)
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")

        task = URLSession.shared.webSocketTask(with: request)
        task?.resume()
        receive()
        refreshSettings()
    }

    func refreshSettings() {
        guard let coreURL else { return }
        var request = URLRequest(url: coreURL.appendingPathComponent("settings"))
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        URLSession.shared.dataTask(with: request) { [weak self] data, _response, error in
            guard let self else { return }
            if let error {
                print("GlanceHelper failed to refresh settings: \(error.localizedDescription)")
                return
            }
            guard let data else { return }
            do {
                let settings = try self.decoder.decode(CoreSettings.self, from: data)
                DispatchQueue.main.async { [onSettings] in
                    onSettings(settings)
                }
            } catch {
                print("GlanceHelper ignored malformed settings: \(error.localizedDescription)")
            }
        }.resume()
    }

    func sendInput(action: String, cursor: CursorSnapshot? = nil, suppressedReason: String? = nil) {
        let event = HelperInputEvent(
            sentAtMilliseconds: Self.nowMilliseconds(),
            sequence: nextSequence(),
            action: action,
            cursor: cursor,
            suppressedReason: suppressedReason
        )
        send(event)
    }

    func sendPermission(permission: String, state: String, requiredFor: [String]) {
        let event = HelperPermissionEvent(
            sentAtMilliseconds: Self.nowMilliseconds(),
            sequence: nextSequence(),
            permission: permission,
            state: state,
            requiredFor: requiredFor
        )
        send(event)
    }

    private func nextSequence() -> Int {
        helperSequence += 1
        return helperSequence
    }

    private func send<T: Encodable>(_ event: T) {
        do {
            let data = try encoder.encode(event)
            guard let text = String(data: data, encoding: .utf8) else { return }
            task?.send(.string(text)) { error in
                if let error {
                    print("GlanceHelper failed to send event: \(error.localizedDescription)")
                }
            }
        } catch {
            print("GlanceHelper failed to encode event: \(error.localizedDescription)")
        }
    }

    private static func nowMilliseconds() -> Int64 {
        Int64(Date().timeIntervalSince1970 * 1000)
    }

    private func receive() {
        task?.receive { [weak self] result in
            switch result {
            case .success(let message):
                self?.handle(message: message)
                self?.receive()
            case .failure(let error):
                print("GlanceHelper Core WebSocket closed: \(error.localizedDescription)")
            }
        }
    }

    private func handle(message: URLSessionWebSocketTask.Message) {
        let data: Data
        switch message {
        case .string(let text):
            data = Data(text.utf8)
        case .data(let payload):
            data = payload
        @unknown default:
            print("GlanceHelper ignored unknown WebSocket message kind")
            return
        }

        do {
            let envelope = try decoder.decode(HelperEventEnvelope.self, from: data)
            guard envelope.version == HelperEventContract.version else {
                print("GlanceHelper ignored unsupported event version \(envelope.version)")
                return
            }

            switch envelope.type {
            case "core.ready":
                _ = try decoder.decode(CoreReadyEvent.self, from: data)
            case "gaze.sample":
                let event = try decoder.decode(GazeSampleEvent.self, from: data)
                guard isValid(gazeSample: event) else {
                    print("GlanceHelper ignored invalid gaze.sample event")
                    return
                }
                DispatchQueue.main.async { [onGazeSample] in
                    onGazeSample(event)
                }
            case "tracking.status":
                let event = try decoder.decode(TrackingStatusEvent.self, from: data)
                guard isValid(trackingStatus: event) else {
                    print("GlanceHelper ignored invalid tracking.status event")
                    return
                }
                DispatchQueue.main.async { [onTrackingStatus] in
                    onTrackingStatus(event)
                }
            default:
                print("GlanceHelper ignored unknown event type \(envelope.type)")
            }
        } catch {
            print("GlanceHelper ignored malformed event: \(error.localizedDescription)")
        }
    }

    private func isValid(gazeSample event: GazeSampleEvent) -> Bool {
        guard
            event.x.isFinite,
            event.y.isFinite,
            event.display.x.isFinite,
            event.display.y.isFinite,
            event.display.width.isFinite,
            event.display.height.isFinite,
            event.display.scale.isFinite,
            event.display.width > 0,
            event.display.height > 0,
            event.display.scale > 0,
            event.display.coordinateSpace == HelperEventContract.coordinateSpace,
            event.confidence.isFinite,
            (0...1).contains(event.confidence),
            HelperEventContract.gazeStatuses.contains(event.status),
            HelperEventContract.gazeSources.contains(event.source),
            !isStale(gazeSample: event)
        else {
            return false
        }

        let minX = event.display.x - event.display.width
        let maxX = event.display.x + (event.display.width * 2)
        let minY = event.display.y - event.display.height
        let maxY = event.display.y + (event.display.height * 2)
        return (minX...maxX).contains(event.x) && (minY...maxY).contains(event.y)
    }

    private func isValid(trackingStatus event: TrackingStatusEvent) -> Bool {
        HelperEventContract.trackingStates.contains(event.tracking)
            && HelperEventContract.overlayStates.contains(event.overlay)
    }

    private func isStale(gazeSample event: GazeSampleEvent) -> Bool {
        let nowMilliseconds = Int64(Date().timeIntervalSince1970 * 1000)
        return nowMilliseconds - event.sampleAtMilliseconds
            > HelperEventContract.staleSampleMilliseconds
    }
}

final class HelperInputController {
    private let overlayView: CursorOverlayView
    private let coreSocket: CoreSocket
    private var eventTap: CFMachPort?
    private var runLoopSource: CFRunLoopSource?
    private var spaceIsDown = false
    private var spacePressCanClick = false
    private var escIsDown = false
    private var permissionRetryTimer: Timer?
    private var requestedAccessibilityPermission = false
    private var requestedInputMonitoringPermission = false

    var spaceClickEnabled = true
    var pauseBehavior = "fast-recovery"

    init(overlayView: CursorOverlayView, coreSocket: CoreSocket) {
        self.overlayView = overlayView
        self.coreSocket = coreSocket
    }

    func start() {
        reportPermissions()
        if !installEventTap() {
            schedulePermissionRetry()
        }
    }

    private func schedulePermissionRetry() {
        permissionRetryTimer?.invalidate()
        permissionRetryTimer = Timer.scheduledTimer(withTimeInterval: 2, repeats: true) { [weak self] timer in
            guard let self else {
                timer.invalidate()
                return
            }
            self.reportPermissions()
            if self.installEventTap() {
                timer.invalidate()
                self.permissionRetryTimer = nil
            }
        }
    }

    private func installEventTap() -> Bool {
        guard eventTap == nil else { return true }
        guard CGPreflightListenEventAccess() else {
            print("GlanceHelper missing Input Monitoring permission for Space/Esc capture")
            return false
        }

        let mask = (1 << CGEventType.keyDown.rawValue) | (1 << CGEventType.keyUp.rawValue)
        let callback: CGEventTapCallBack = { _proxy, type, event, refcon in
            guard let refcon else { return Unmanaged.passRetained(event) }
            let controller = Unmanaged<HelperInputController>
                .fromOpaque(refcon)
                .takeUnretainedValue()
            return controller.handle(event: event, type: type)
                ? nil
                : Unmanaged.passRetained(event)
        }

        eventTap = CGEvent.tapCreate(
            tap: .cgSessionEventTap,
            place: .headInsertEventTap,
            options: .defaultTap,
            eventsOfInterest: CGEventMask(mask),
            callback: callback,
            userInfo: Unmanaged.passUnretained(self).toOpaque()
        )
        guard let eventTap else {
            coreSocket.sendPermission(
                permission: "input-monitoring",
                state: "denied",
                requiredFor: ["esc-pause", "space-click"]
            )
            print("GlanceHelper could not create keyboard event tap")
            return false
        }

        runLoopSource = CFMachPortCreateRunLoopSource(kCFAllocatorDefault, eventTap, 0)
        if let runLoopSource {
            CFRunLoopAddSource(CFRunLoopGetMain(), runLoopSource, .commonModes)
        }
        CGEvent.tapEnable(tap: eventTap, enable: true)
        return true
    }

    private func handle(event: CGEvent, type: CGEventType) -> Bool {
        let keyCode = Int(event.getIntegerValueField(.keyboardEventKeycode))
        let isRepeat = event.getIntegerValueField(.keyboardEventAutorepeat) != 0
        switch (keyCode, type) {
        case (49, .keyDown):
            return handleSpaceDown(isRepeat: isRepeat)
        case (49, .keyUp):
            return handleSpaceUp()
        case (53, .keyDown):
            return handleEscDown(isRepeat: isRepeat)
        case (53, .keyUp):
            return handleEscUp()
        default:
            return false
        }
    }

    private func handleSpaceDown(isRepeat: Bool) -> Bool {
        guard overlayView.trackingInputEnabled(spaceClickEnabled: spaceClickEnabled) else {
            coreSocket.sendInput(action: "space-down", suppressedReason: "disabled")
            return false
        }
        guard !escIsDown else {
            coreSocket.sendInput(action: "space-down", suppressedReason: "paused")
            return true
        }
        guard !isRepeat && !spaceIsDown else {
            coreSocket.sendInput(action: "space-down", suppressedReason: "repeat")
            return true
        }
        guard overlayView.latestCursor() != nil else {
            coreSocket.sendInput(action: "space-down", suppressedReason: "no-cursor")
            return true
        }

        spaceIsDown = true
        spacePressCanClick = true
        coreSocket.sendInput(action: "space-down")
        return true
    }

    private func handleSpaceUp() -> Bool {
        guard spaceIsDown else { return false }
        spaceIsDown = false
        defer { spacePressCanClick = false }

        guard spacePressCanClick else {
            coreSocket.sendInput(action: "space-up", suppressedReason: "disabled")
            return true
        }
        guard overlayView.trackingInputEnabled(spaceClickEnabled: spaceClickEnabled) else {
            coreSocket.sendInput(action: "space-up", suppressedReason: "disabled")
            return true
        }
        guard !escIsDown else {
            coreSocket.sendInput(action: "space-up", suppressedReason: "paused")
            return true
        }
        guard let cursor = overlayView.latestCursor() else {
            coreSocket.sendInput(action: "space-up", suppressedReason: "no-cursor")
            return true
        }
        guard AXIsProcessTrusted() else {
            coreSocket.sendPermission(
                permission: "accessibility",
                state: "denied",
                requiredFor: ["space-click"]
            )
            coreSocket.sendInput(action: "space-click", suppressedReason: "permission-denied")
            return true
        }

        guard postLeftClick(at: cursor) else {
            coreSocket.sendInput(action: "space-click", suppressedReason: "no-cursor")
            return true
        }
        coreSocket.sendInput(action: "space-click", cursor: cursor)
        return true
    }

    private func handleEscDown(isRepeat: Bool) -> Bool {
        guard !isRepeat && !escIsDown else {
            coreSocket.sendInput(action: "esc-down", suppressedReason: "repeat")
            return true
        }

        escIsDown = true
        spacePressCanClick = false
        overlayView.pause(behavior: pauseBehavior)
        coreSocket.sendInput(action: "esc-down")
        coreSocket.sendInput(action: "pause-started")
        return true
    }

    private func handleEscUp() -> Bool {
        guard escIsDown else { return false }
        escIsDown = false
        overlayView.resume()
        coreSocket.sendInput(action: "esc-up")
        coreSocket.sendInput(action: "pause-ended")
        return true
    }

    private func postLeftClick(at cursor: CursorSnapshot) -> Bool {
        guard let point = coreGraphicsPoint(from: cursor) else { return false }
        guard
            let mouseDown = CGEvent(
                mouseEventSource: nil,
                mouseType: .leftMouseDown,
                mouseCursorPosition: point,
                mouseButton: .left
            ),
            let mouseUp = CGEvent(
                mouseEventSource: nil,
                mouseType: .leftMouseUp,
                mouseCursorPosition: point,
                mouseButton: .left
            )
        else {
            return false
        }
        mouseDown.post(tap: .cghidEventTap)
        mouseUp.post(tap: .cghidEventTap)
        return true
    }

    private func coreGraphicsPoint(from cursor: CursorSnapshot) -> CGPoint? {
        guard cursor.display.coordinateSpace == HelperEventContract.coordinateSpace else { return nil }
        let displayLocalX = cursor.x - cursor.display.x
        let displayLocalY = cursor.y - cursor.display.y
        return CGPoint(
            x: cursor.display.x + displayLocalX,
            y: cursor.display.y + displayLocalY
        )
    }

    private func reportPermissions() {
        let accessibilityGranted = AXIsProcessTrusted()
        let inputMonitoringGranted = CGPreflightListenEventAccess()
        if !accessibilityGranted && !requestedAccessibilityPermission {
            requestedAccessibilityPermission = true
            let options = [
                kAXTrustedCheckOptionPrompt.takeUnretainedValue() as String: true
            ] as CFDictionary
            _ = AXIsProcessTrustedWithOptions(options)
        }
        if !inputMonitoringGranted && !requestedInputMonitoringPermission {
            requestedInputMonitoringPermission = true
            _ = CGRequestListenEventAccess()
        }
        coreSocket.sendPermission(
            permission: "accessibility",
            state: AXIsProcessTrusted() ? "granted" : "denied",
            requiredFor: ["space-click"]
        )
        coreSocket.sendPermission(
            permission: "input-monitoring",
            state: CGPreflightListenEventAccess() ? "granted" : "denied",
            requiredFor: ["esc-pause", "space-click"]
        )
    }
}

let app = NSApplication.shared
let delegate = AppDelegate()
app.delegate = delegate
app.run()
