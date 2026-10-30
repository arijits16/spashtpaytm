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
                .task { await auth.start() }
                .onOpenURL { url in
                    // The redirect back from Google. Without this the sheet
                    // closes and nothing happens.
                    _ = GoogleSignInService.handle(url)
                }
        }
    }
}

/// Switches between login and the signed-in screen.
///
/// Phase 4 replaces `SignedInView` with the Paytm-style home; the shape of this
/// view does not change.
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
                SignedInView(auth: auth, me: me)
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
