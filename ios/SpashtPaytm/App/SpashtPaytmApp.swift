import SwiftUI

/// App entry point.
///
/// Three things happen here and nowhere else: the single root view, the
/// light-mode lock (§5.2), and the privacy cover driven by `scenePhase`
/// (§5.10). Firebase configuration joins this file in phase 1, guarded by the
/// presence of `GoogleService-Info.plist`.
@main
struct SpashtPaytmApp: App {

    @Environment(\.scenePhase) private var scenePhase

    var body: some Scene {
        WindowGroup {
            RootView()
                // The whole app is light mode: the reference screenshots are,
                // and a half-converted dark mode on the projector looks broken.
                .preferredColorScheme(.light)
                .privacyCover(scenePhase: scenePhase)
                .animation(.easeInOut(duration: 0.15), value: scenePhase)
        }
    }
}

/// The root view.
///
/// Phase 0 shows the health screen. Phase 1 turns this into the
/// login / signed-in switch, and phase 4 into the Paytm-style home.
struct RootView: View {
    var body: some View {
        HealthView()
    }
}
