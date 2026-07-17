// swift-tools-version: 5.9

import PackageDescription

let package = Package(
    name: "GlanceHelper",
    platforms: [.macOS(.v13)],
    products: [
        .executable(name: "GlanceHelper", targets: ["GlanceHelper"])
    ],
    targets: [
        .executableTarget(name: "GlanceHelper")
    ]
)
