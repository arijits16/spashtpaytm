import SwiftUI

/// Hides the screen contents in the app switcher (build plan §5.10).
///
/// iOS snapshots an app when it leaves the foreground, and that snapshot shows
/// in the multitasking switcher. A journey screen carries the customer's
/// income, her offers and her consents, so it must not end up there — the same
/// reason Paytm shows a "protected screen".
///
/// **It must NOT react to screen recording or mirroring.** The demo mirrors the
/// iPhone to the laptop for the projector; hiding then would blank the demo.
/// Only `scenePhase` drives this.
struct PrivacyCover: View {
    var body: some View {
        ZStack {
            Theme.loginGradient
                .ignoresSafeArea()

            VStack(spacing: 8) {
                HStack(alignment: .firstTextBaseline, spacing: 8) {
                    // Plain text wordmark — never the official logo artwork (§5.1).
                    Text("Paytm")
                        .font(.system(size: 34, weight: .bold))
                        .foregroundStyle(Theme.navy)

                    Text("Concept")
                        .font(.system(size: 10, weight: .bold))
                        .foregroundStyle(Theme.text1)
                        .padding(.horizontal, 8)
                        .padding(.vertical, 2)
                        .background(Theme.badgeNew, in: Capsule())
                }

                Text("Screen hidden")
                    .font(.spashtCaption)
                    .foregroundStyle(Theme.text3)
            }
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("Screen hidden for privacy")
    }
}

extension View {
    /// Overlay the privacy cover whenever the scene is not active.
    ///
    /// `.inactive` is included as well as `.background`: iOS takes its snapshot
    /// during the inactive moment, so covering only on `.background` is too
    /// late and the switcher still shows real data.
    func privacyCover(scenePhase: ScenePhase) -> some View {
        overlay {
            if scenePhase != .active {
                PrivacyCover()
                    .transition(.opacity)
            }
        }
    }
}

#Preview {
    PrivacyCover()
}
