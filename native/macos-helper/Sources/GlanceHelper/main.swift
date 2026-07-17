import AppKit
import Foundation

final class AppDelegate: NSObject, NSApplicationDelegate {
    private var overlayWindow: NSWindow?
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
        window.contentView = CursorOverlayView(frame: screen.frame)
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

        coreSocket = CoreSocket(url: url, token: token)
        coreSocket?.connect()
    }
}

final class CursorOverlayView: NSView {
    private var cursorPosition: CGPoint = CGPoint(x: 200, y: 200)

    override var isFlipped: Bool { true }

    override func draw(_ dirtyRect: NSRect) {
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
    private var task: URLSessionWebSocketTask?

    init(url: URL, token: String) {
        self.url = url
        self.token = token
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
            case .success:
                self?.receive()
            case .failure(let error):
                print("GlanceHelper Core WebSocket closed: \(error.localizedDescription)")
            }
        }
    }
}

let app = NSApplication.shared
let delegate = AppDelegate()
app.delegate = delegate
app.run()
