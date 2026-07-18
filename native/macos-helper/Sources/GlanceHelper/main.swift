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

struct DisplayBounds: Decodable {
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

final class AppDelegate: NSObject, NSApplicationDelegate {
    private var overlayWindow: NSWindow?
    private var overlayView: CursorOverlayView?
    private var coreSocket: CoreSocket?

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

        coreSocket = CoreSocket(
            url: url,
            token: token,
            onGazeSample: { [weak self] event in
                self?.overlayView?.apply(gazeSample: event)
            },
            onTrackingStatus: { [weak self] event in
                self?.overlayView?.apply(trackingStatus: event)
            }
        )
        coreSocket?.connect()
    }
}

final class CursorOverlayView: NSView {
    private var cursorPosition: CGPoint = CGPoint(x: 200, y: 200)
    private var overlayState: String = "visible"

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
        needsDisplay = true
    }

    func apply(trackingStatus event: TrackingStatusEvent) {
        overlayState = event.overlay
        isHidden = event.overlay == "hidden"
    }

    private static func isStale(gazeSample event: GazeSampleEvent) -> Bool {
        let nowMilliseconds = Int64(Date().timeIntervalSince1970 * 1000)
        return nowMilliseconds - event.sampleAtMilliseconds
            > HelperEventContract.staleSampleMilliseconds
    }

    override func draw(_ dirtyRect: NSRect) {
        guard overlayState != "hidden" else { return }

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
    private let token: String
    private let onGazeSample: (GazeSampleEvent) -> Void
    private let onTrackingStatus: (TrackingStatusEvent) -> Void
    private var task: URLSessionWebSocketTask?
    private let decoder = JSONDecoder()

    init(
        url: URL,
        token: String,
        onGazeSample: @escaping (GazeSampleEvent) -> Void,
        onTrackingStatus: @escaping (TrackingStatusEvent) -> Void
    ) {
        self.url = url
        self.token = token
        self.onGazeSample = onGazeSample
        self.onTrackingStatus = onTrackingStatus
    }

    func connect() {
        var request = URLRequest(url: url)
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")

        task = URLSession.shared.webSocketTask(with: request)
        task?.resume()
        receive()
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

let app = NSApplication.shared
let delegate = AppDelegate()
app.delegate = delegate
app.run()
