import SwiftUI

/// The mandatory concept-demo label (build plan §5.1).
///
/// The app deliberately imitates the Paytm app's layout and feel, so this
/// ribbon is what keeps that honest for anyone who picks up the phone. It is
/// persistent and must never be made dismissible, animated away, or hidden
/// behind a setting.
struct ConceptRibbon: View {
    var body: some View {
        Text("Concept demo · Paytm Build for India AI Hackathon · not the live Paytm app")
            .font(.spashtFinePrint)
            .foregroundStyle(.white.opacity(0.9))
            .multilineTextAlignment(.center)
            .lineLimit(2)
            .minimumScaleFactor(0.8)
            .frame(maxWidth: .infinity)
            .padding(.horizontal, Metrics.screenPadding)
            .padding(.vertical, 4)
            .background(Theme.navy)
            // One label for VoiceOver instead of a wall of punctuation.
            .accessibilityElement(children: .ignore)
            .accessibilityLabel(
                "Concept demo for the Paytm Build for India AI Hackathon. "
                    + "This is not the live Paytm app."
            )
    }
}

#Preview {
    VStack(spacing: 0) {
        ConceptRibbon()
        Spacer()
    }
}
