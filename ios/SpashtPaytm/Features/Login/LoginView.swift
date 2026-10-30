import SwiftUI

/// Login screen (build plan §5.5).
///
/// Light-blue vertical gradient, a text wordmark with a `Concept` pill, Google
/// sign-in, and — in Debug builds with a demo key — a demo path that needs no
/// network at all.
struct LoginView: View {
    let auth: AuthService

    var body: some View {
        ZStack {
            Theme.loginGradient.ignoresSafeArea()

            VStack(spacing: 0) {
                ConceptRibbon()
                Spacer()
                wordmark
                Spacer()
                buttons
                footer
            }
        }
    }

    // MARK: - Pieces

    private var wordmark: some View {
        VStack(spacing: 6) {
            HStack(alignment: .firstTextBaseline, spacing: 8) {
                // Plain text, never the official two-tone logo artwork (§5.1).
                Text("Paytm")
                    .font(.system(size: 38, weight: .bold))
                    .foregroundStyle(Theme.navy)

                Text("Concept")
                    .font(.system(size: 11, weight: .bold))
                    .foregroundStyle(Theme.text1)
                    .padding(.horizontal, 8)
                    .padding(.vertical, 3)
                    .background(Theme.badgeNew, in: Capsule())
            }

            Text("Spasht · loans you understand")
                .font(.spashtBody)
                .foregroundStyle(Theme.text2)

            Text("स्पष्ट — तुमच्या भाषेत, तुम्हाला समजेल असं")
                .font(.spashtCaption)
                .foregroundStyle(Theme.text3)
        }
    }

    @ViewBuilder
    private var buttons: some View {
        VStack(spacing: 12) {
            if let message = auth.errorMessage {
                Label(message, systemImage: "exclamationmark.circle.fill")
                    .font(.spashtCaption)
                    .foregroundStyle(Theme.danger)
                    .multilineTextAlignment(.leading)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(12)
                    .background(Theme.alertPink, in: Metrics.bannerShape)
            }

            if auth.isGoogleAvailable {
                GoogleButton(busy: auth.state.isBusy) {
                    Task { await auth.signInWithGoogle() }
                }
            } else {
                Text(
                    "Google sign-in is unavailable: add GoogleService-Info.plist and run `make ios-config`."
                )
                .font(.spashtCaption)
                .foregroundStyle(Theme.text3)
                .multilineTextAlignment(.center)
                .padding(12)
                .overlay(
                    Metrics.bannerShape.strokeBorder(
                        Theme.hairline, style: StrokeStyle(lineWidth: 1, dash: [4])
                    )
                )
            }

            #if DEBUG
                if auth.isDemoAvailable {
                    Button {
                        Task { await auth.signInAsDemoUser() }
                    } label: {
                        Text(auth.state == .signingIn ? "Signing in…" : "Continue as demo user")
                            .font(.spashtBodyBold)
                            .foregroundStyle(Theme.text2)
                            .frame(maxWidth: .infinity, minHeight: 48)
                            .background(.white.opacity(0.7), in: Capsule())
                            .overlay(Capsule().strokeBorder(Theme.hairline, lineWidth: 1))
                    }
                    .disabled(auth.state.isBusy)
                }
            #endif
        }
        .frame(maxWidth: 340)
        .padding(.horizontal, Metrics.screenPadding)
    }

    private var footer: some View {
        Text(
            "Concept prototype for Paytm Build for India AI Hackathon · not the live Paytm app · synthetic data only"
        )
        .font(.system(size: 11))
        .foregroundStyle(Theme.text3)
        .multilineTextAlignment(.center)
        .padding(.horizontal, 28)
        .padding(.top, 28)
        .padding(.bottom, 12)
    }
}

/// Google sign-in button.
///
/// Deliberately **text only, with no Google logo artwork**. §5.1 forbids
/// third-party logos anywhere in this concept, and that rule does not get an
/// exception for the sign-in button: reproducing someone's mark is exactly what
/// it exists to prevent. The white surface, 48 pt height and "Continue with
/// Google" wording still read as the standard control.
private struct GoogleButton: View {
    let busy: Bool
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            HStack(spacing: 10) {
                if busy {
                    ProgressView().controlSize(.small)
                } else {
                    Image(systemName: "person.badge.key.fill")
                        .foregroundStyle(Theme.text2)
                        .accessibilityHidden(true)
                }
                Text(busy ? "Opening Google…" : "Continue with Google")
                    .font(.system(size: 16, weight: .medium))
                    .foregroundStyle(Color(hex: 0x1F1F1F))
            }
            .frame(maxWidth: .infinity, minHeight: 48)
            .background(.white, in: Capsule())
            .overlay(Capsule().strokeBorder(Color(hex: 0x747775), lineWidth: 1))
        }
        .disabled(busy)
    }
}
