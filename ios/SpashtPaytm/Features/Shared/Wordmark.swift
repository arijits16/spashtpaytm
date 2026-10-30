import SwiftUI

/// The header wordmark: plain text, never logo artwork (build plan §5.1).
///
/// A rendered word with a `Concept` pill beside it. No image asset exists for
/// this on purpose - there is nothing in the bundle that could be mistaken for
/// an official mark, and nothing a screenshot could lift.
struct Wordmark: View {
    var size: CGFloat = 22
    var showsPill = true
    var colour: Color = Theme.navy

    var body: some View {
        HStack(spacing: 6) {
            Text("Paytm")
                .font(.system(size: size, weight: .bold, design: .default))
                .foregroundStyle(colour)

            if showsPill {
                Text("Concept")
                    .font(.system(size: max(8, size * 0.42), weight: .bold))
                    .foregroundStyle(colour.opacity(0.75))
                    .padding(.horizontal, 6)
                    .padding(.vertical, 2)
                    .background(
                        Capsule().strokeBorder(colour.opacity(0.4), lineWidth: 1)
                    )
            }
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("Paytm, concept demo")
    }
}
