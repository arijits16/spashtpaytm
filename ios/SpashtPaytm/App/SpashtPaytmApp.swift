import SwiftUI

/// App entry point.
///
/// Owns the session, the light-mode lock (§5.2), the privacy cover driven by
/// `scenePhase` (§5.10), and the Google sign-in callback URL.
@main
struct SpashtPaytmApp: App {

    @Environment(\.scenePhase) private var scenePhase
    @State private var auth = AuthService()

    var body: some Scene {
        WindowGroup {
            RootView(auth: auth)
                // The whole app is light mode: the reference screenshots are,
                // and a half-converted dark mode on the projector looks broken.
                .preferredColorScheme(.light)
                .privacyCover(scenePhase: scenePhase)
                .animation(.easeInOut(duration: 0.15), value: scenePhase)
                .task {
                    // Warms the tunnel, the TLS connection and the backend's
                    // first database connection while the customer is still
                    // looking at the login screen (§10.4).
                    Prewarm.ping()
                    await auth.start()
                }
                .onOpenURL { url in
                    // The redirect back from Google. Without this the sheet
                    // closes and nothing happens.
                    _ = GoogleSignInService.handle(url)
                }
        }
    }
}

/// Switches between login and the home screen.
struct RootView: View {
    let auth: AuthService

    var body: some View {
        Group {
            switch auth.state {
            case .starting:
                SplashView()
            case .signedOut, .signingIn:
                LoginView(auth: auth)
            case .signedIn(let me):
                // The concept ribbon sits above the home screen rather than
                // inside it, so it is present on every screen the app can
                // reach and no navigation can scroll it away (§5.1).
                VStack(spacing: 0) {
                    ConceptRibbon()
                    HomeView(auth: auth, me: me)
                }
                .ignoresSafeArea(.keyboard, edges: .bottom)
            }
        }
        .animation(.easeInOut(duration: 0.2), value: auth.state)
    }
}

/// Shown while the stored session is being restored.
///
/// Matches the launch screen colour, so a signed-in user sees one continuous
/// background rather than a flash of the login screen.
private struct SplashView: View {
    var body: some View {
        ZStack {
            Theme.loginGradient.ignoresSafeArea()
            ProgressView()
                .controlSize(.large)
                .tint(Theme.navy)
        }
    }
}
