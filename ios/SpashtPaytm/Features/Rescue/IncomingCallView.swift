import SwiftUI

/// The full-screen incoming call (build plan §5.11, phase 10).
///
/// Deliberately styled like a phone call rather than a notification, because
/// that is the behaviour being demonstrated: an agent that *rings you back* in
/// your language and picks up where you stopped.
///
/// Equally deliberately, it never pretends to be a real call. The subtitle says
/// "Concept demo · simulated call", the caption of what will be spoken is on
/// screen before Accept is pressed, and nothing here dials anything. In
/// production the call would be placed by a telephony provider (Exotel) - noted
/// in `docs/DECISIONS.md`.
///
/// **Decline is as prominent as Accept.** A rescue agent whose decline button
/// is a grey afterthought is a dark pattern wearing a helpful hat.
struct IncomingCallView: View {
    let call: RescueCall
    let isWorking: Bool
    let onAccept: () -> Void
    let onDecline: () -> Void

    @State private var pulsing = false

    var body: some View {
        ZStack {
            // Dark, unlike the rest of the app: a call screen that matched the
            // home screen would read as another card rather than as a call.
            LinearGradient(
                colors: [Theme.navy, Color(red: 0.03, green: 0.07, blue: 0.16)],
                startPoint: .top,
                endPoint: .bottom
            )
            .ignoresSafeArea()

            VStack(spacing: 0) {
                Spacer(minLength: 40)

                caller

                Spacer(minLength: 24)

                caption

                Spacer(minLength: 32)

                buttons
                    .padding(.horizontal, 34)

                Text("Simulated in the demo · a real deployment would use a telephony provider")
                    .font(.system(size: 10))
                    .foregroundStyle(.white.opacity(0.45))
                    .multilineTextAlignment(.center)
                    .padding(.horizontal, 36)
                    .padding(.top, 18)
                    .padding(.bottom, 14)
            }
        }
        .onAppear { pulsing = true }
        .accessibilityAddTraits(.isModal)
    }

    // MARK: - Pieces

    private var caller: some View {
        VStack(spacing: 14) {
            Text("Incoming call")
                .font(.system(size: 12, weight: .semibold))
                .tracking(1.6)
                .foregroundStyle(.white.opacity(0.6))

            ZStack {
                ForEach([1.0, 1.26, 1.52], id: \.self) { scale in
                    Circle()
                        .strokeBorder(.white.opacity(pulsing ? 0.04 : 0.26), lineWidth: 1.5)
                        .frame(width: 104 * scale, height: 104 * scale)
                }

                Circle()
                    .fill(.white.opacity(0.14))
                    .frame(width: 104, height: 104)

                Image(systemName: "waveform")
                    .font(.system(size: 38, weight: .medium))
                    .foregroundStyle(.white)
            }
            .animation(
                .easeInOut(duration: 1.4).repeatForever(autoreverses: false),
                value: pulsing
            )

            VStack(spacing: 6) {
                Text(call.callerName)
                    .font(.system(size: 24, weight: .bold))
                    .foregroundStyle(.white)

                Text(call.subtitle)
                    .font(.system(size: 11, weight: .semibold))
                    .foregroundStyle(.white.opacity(0.55))
            }
            .padding(.top, 6)
        }
    }

    /// What the agent is about to say, in writing, before anybody answers.
    ///
    /// The line comes from the backend's `rescue_call` template in the
    /// journey's own language; the app neither composes nor translates it.
    private var caption: some View {
        VStack(spacing: 10) {
            Text(call.line)
                .font(.system(size: 15, weight: .medium))
                .foregroundStyle(.white.opacity(0.92))
                .multilineTextAlignment(.center)
                .lineSpacing(3)

            Text("Continues at: \(call.step)")
                .font(.system(size: 10, weight: .semibold))
                .foregroundStyle(.white.opacity(0.45))
        }
        .padding(.vertical, 18)
        .padding(.horizontal, 22)
        .background(.white.opacity(0.08), in: RoundedRectangle(cornerRadius: 18, style: .continuous))
        .padding(.horizontal, 26)
    }

    private var buttons: some View {
        HStack(spacing: 0) {
            CallButton(
                symbol: "phone.down.fill",
                label: "Decline",
                tint: Color(red: 0.86, green: 0.25, blue: 0.25),
                disabled: isWorking,
                action: onDecline
            )

            Spacer()

            CallButton(
                symbol: "phone.fill",
                label: "Accept",
                tint: Color(red: 0.14, green: 0.68, blue: 0.38),
                disabled: isWorking,
                action: onAccept
            )
        }
    }
}

private struct CallButton: View {
    let symbol: String
    let label: String
    let tint: Color
    let disabled: Bool
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            VStack(spacing: 9) {
                ZStack {
                    Circle()
                        .fill(tint)
                        .frame(width: 70, height: 70)
                    Image(systemName: symbol)
                        .font(.system(size: 27, weight: .semibold))
                        .foregroundStyle(.white)
                }
                Text(label)
                    .font(.system(size: 12, weight: .semibold))
                    .foregroundStyle(.white.opacity(0.8))
            }
        }
        .buttonStyle(.plain)
        .disabled(disabled)
        .opacity(disabled ? 0.5 : 1)
        .accessibilityLabel(label)
    }
}
