import SwiftUI

/// The sheet every non-Spasht tap opens (build plan §5.1).
///
/// It exists for one reason: this app looks enough like Paytm that a person
/// holding it could reasonably believe a tile does something. Saying so plainly
/// on every tap is the honest version of a prototype, and the `Try Spasht →`
/// button turns the dead end into a route to the thing that does work.
struct ConceptSheet: View {
    let subject: String
    let onTrySpasht: () -> Void

    @Environment(\.dismiss) private var dismiss

    var body: some View {
        VStack(spacing: 0) {
            Capsule()
                .fill(Theme.hairline)
                .frame(width: 38, height: 4)
                .padding(.top, 10)

            VStack(spacing: 16) {
                Image(systemName: "hand.raised.fill")
                    .font(.system(size: 26))
                    .foregroundStyle(Theme.navy)
                    .frame(width: 62, height: 62)
                    .background(Theme.offerStrip, in: Circle())

                Text(subject)
                    .font(.system(size: 13, weight: .semibold))
                    .foregroundStyle(Theme.text3)
                    .textCase(.uppercase)

                Text("This is a concept demo.")
                    .font(.system(size: 19, weight: .bold))
                    .foregroundStyle(Theme.text1)

                Text("Only **Spasht** is live in this prototype. Everything else is here to show where it would sit inside a real app.")
                    .font(.system(size: 14))
                    .foregroundStyle(Theme.text2)
                    .multilineTextAlignment(.center)
                    .fixedSize(horizontal: false, vertical: true)

                Button(action: onTrySpasht) {
                    Text("Try Spasht →")
                        .font(.system(size: 16, weight: .bold))
                        .foregroundStyle(.white)
                        .frame(maxWidth: .infinity)
                        .frame(height: 52)
                        .background(Theme.navy, in: Capsule())
                }
                .buttonStyle(.plain)
                .padding(.top, 4)

                Button("Not now") { dismiss() }
                    .font(.system(size: 14, weight: .medium))
                    .foregroundStyle(Theme.text3)
                    .frame(minHeight: Metrics.minimumTapTarget)
            }
            .padding(.horizontal, 26)
            .padding(.top, 22)

            Spacer(minLength: 0)
        }
        .frame(maxWidth: .infinity)
        .background(Theme.card)
        .presentationDetents([.height(420)])
        .presentationDragIndicator(.hidden)
    }
}
