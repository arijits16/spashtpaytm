import SwiftUI

/// The Spasht Receipt, in the app (build plan §5.7).
///
/// The payoff of the whole journey, so it is allowed to feel like one: the
/// stamp springs in rotated, there is one confetti burst and a success haptic,
/// and then it settles into something you could actually show someone.
///
/// Every figure comes from the signed payload. The QR encodes
/// `publicUrl`, which the **backend** built from `PUBLIC_BASE_URL` (§11.6) - the
/// app never constructs it, so it cannot be pointed somewhere else.
struct ReceiptCardView: View {
    let data: ReceiptCard

    @State private var stamped = false
    @State private var confetti = false

    var body: some View {
        VStack(spacing: 12) {
            JourneyCard {
                stamp
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 4)

                Divider()

                VStack(spacing: 7) {
                    DetailRow(label: "Receipt", value: data.receiptNo, monospaced: true)
                    DetailRow(label: "Lender", value: data.lender)
                    DetailRow(
                        label: "EMI",
                        value: "₹\(Format.rupees(data.emi)) × \(data.tenureMonths)"
                    )
                    DetailRow(label: "Total repay", value: "₹\(Format.rupees(data.totalRepay))")
                    DetailRow(label: "Language", value: data.language.nativeName)
                    DetailRow(
                        label: "Insurance",
                        value: data.insuranceTaken ? "taken" : "not taken",
                        // Highlighted when *not* taken, because that is the
                        // outcome worth noticing: it means nothing was bundled.
                        tint: data.insuranceTaken ? Theme.text2 : Theme.success
                    )
                }
            }
            .overlay(alignment: .top) {
                if confetti {
                    ConfettiBurst()
                        .allowsHitTesting(false)
                }
            }

            qrCard
            summaryPreview
        }
        .task {
            // A beat before the stamp, so the card has settled and the
            // animation reads as a stamp rather than a layout jump.
            try? await Task.sleep(for: .milliseconds(180))
            withAnimation(.spring(response: 0.45, dampingFraction: 0.55)) {
                stamped = true
            }
            confetti = true
        }
        .sensoryFeedback(.success, trigger: stamped)
    }

    private var stamp: some View {
        VStack(spacing: 4) {
            Text("SPASHT ✓")
                .font(.system(size: 23, weight: .heavy))
            Text("\(data.teachback.passed)/\(data.teachback.total) understood")
                .font(.system(size: 11, weight: .bold))
        }
        .foregroundStyle(Theme.success)
        .padding(.horizontal, 20)
        .padding(.vertical, 11)
        .overlay(
            RoundedRectangle(cornerRadius: 10)
                .strokeBorder(Theme.success, lineWidth: 2.5)
        )
        // §5.7: rotated -6 degrees, spring scale-in.
        .rotationEffect(.degrees(-6))
        .scaleEffect(stamped ? 1 : 0.4)
        .opacity(stamped ? 1 : 0)
    }

    private var qrCard: some View {
        JourneyCard {
            HStack(spacing: 14) {
                if let code = QrCode.image(from: data.publicUrl, scale: 8) {
                    code
                        .interpolation(.none)
                        .resizable()
                        .scaledToFit()
                        .frame(width: 94, height: 94)
                        .padding(6)
                        .background(.white, in: RoundedRectangle(cornerRadius: 10))
                        .overlay(
                            RoundedRectangle(cornerRadius: 10)
                                .strokeBorder(Theme.hairline, lineWidth: 1)
                        )
                }

                VStack(alignment: .leading, spacing: 4) {
                    Text("Check this receipt")
                        .font(.system(size: 13, weight: .bold))
                        .foregroundStyle(Theme.text1)
                    Text("Scan to verify the hash chain and signature on any phone.")
                        .font(.system(size: 11.5))
                        .foregroundStyle(Theme.text3)
                        .fixedSize(horizontal: false, vertical: true)
                    Text(data.publicUrl)
                        .font(.system(size: 9, design: .monospaced))
                        .foregroundStyle(Theme.link)
                        .lineLimit(2)
                        .truncationMode(.middle)
                }
            }
        }
    }

    /// A mock message preview (§5.7). Nothing is actually sent anywhere, and
    /// the bubble is deliberately generic - no third-party messaging logo.
    private var summaryPreview: some View {
        JourneyCard {
            HStack(spacing: 7) {
                Image(systemName: "text.bubble.fill")
                    .font(.system(size: 12))
                    .foregroundStyle(Theme.text3)
                Text("Summary sent in \(data.language.nativeName)")
                    .font(.system(size: 11, weight: .semibold))
                    .foregroundStyle(Theme.text3)
            }

            Text(data.summaryText)
                .font(.system(size: 13))
                .foregroundStyle(Theme.text1)
                .fixedSize(horizontal: false, vertical: true)
                .padding(12)
                .background(Theme.offerStrip.opacity(0.55), in: RoundedRectangle(cornerRadius: 14))

            Text("Preview only — nothing was sent in this demo.")
                .font(.system(size: 9.5))
                .foregroundStyle(Theme.text3)
        }
    }
}

private struct DetailRow: View {
    let label: String
    let value: String
    var monospaced = false
    var tint: Color = Theme.text2

    var body: some View {
        HStack {
            Text(label)
                .font(.system(size: 12))
                .foregroundStyle(Theme.text3)
            Spacer()
            Text(value)
                .font(.system(size: 13, weight: .semibold, design: monospaced ? .monospaced : .default))
                .foregroundStyle(tint)
        }
    }
}

/// One confetti burst (§5.7). Drawn, short, and non-interactive.
private struct ConfettiBurst: View {
    @State private var launched = false

    private let pieces: [(x: CGFloat, delay: Double, colour: Color, rotation: Double)] = {
        let colours = [Theme.sky, Theme.navy, Theme.success, Theme.badgeNew, Theme.warning]
        return (0..<26).map { index in
            (
                x: CGFloat.random(in: -140...140),
                delay: Double.random(in: 0...0.18),
                colour: colours[index % colours.count],
                rotation: Double.random(in: -180...180)
            )
        }
    }()

    var body: some View {
        ZStack {
            ForEach(Array(pieces.enumerated()), id: \.offset) { _, piece in
                RoundedRectangle(cornerRadius: 1.5)
                    .fill(piece.colour)
                    .frame(width: 6, height: 10)
                    .rotationEffect(.degrees(launched ? piece.rotation : 0))
                    .offset(x: piece.x, y: launched ? 260 : -10)
                    .opacity(launched ? 0 : 1)
                    .animation(
                        .easeIn(duration: 1.5).delay(piece.delay),
                        value: launched
                    )
            }
        }
        .onAppear { launched = true }
    }
}
