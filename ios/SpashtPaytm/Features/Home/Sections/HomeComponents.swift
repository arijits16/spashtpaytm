import SwiftUI

/// The small pieces every home section is built from (build plan §5.2, §5.3).
///
/// Sixteen sections repeat four shapes: a card, a tile, a chip and a section
/// header. Defining them once is what keeps the spacing consistent enough to
/// hold up next to the reference screenshots.

/// A white section card: radius 20, padding 18, flat (no shadow, per §5.2).
struct SectionCard<Content: View>: View {
    var padding: CGFloat = Metrics.cardPadding
    @ViewBuilder var content: Content

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            content
        }
        .padding(padding)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Theme.card, in: Metrics.cardShape)
    }
}

/// Section title, with an optional "View All →" on the right.
struct SectionHeader: View {
    let title: String
    var viewAll: (() -> Void)?

    var body: some View {
        HStack(alignment: .firstTextBaseline) {
            Text(title)
                // §5.2: section title 20 bold.
                .font(.system(size: 20, weight: .bold))
                .foregroundStyle(Theme.text1)
            Spacer(minLength: 8)
            if let viewAll {
                Button(action: viewAll) {
                    Text("View All →")
                        .font(.system(size: 13, weight: .semibold))
                        .foregroundStyle(Theme.link)
                }
                .buttonStyle(.plain)
                // The label is short, so the tap target is padded out to 44pt
                // rather than left at the text's own height (§5.2).
                .frame(minHeight: Metrics.minimumTapTarget)
            }
        }
    }
}

/// An outline-icon tile: the default style for most sections.
struct OutlineTile: View {
    let tile: HomeConfig.Tile
    let onTap: (HomeConfig.Tile) -> Void

    var body: some View {
        Button {
            onTap(tile)
        } label: {
            VStack(spacing: 7) {
                ZStack(alignment: .topTrailing) {
                    ZStack {
                        if tile.pulses {
                            PulsingRing()
                        }
                        Image(systemName: tile.symbol)
                            .font(.system(size: 25, weight: .regular))
                            .foregroundStyle(tile.tint ?? Theme.iconLine)
                    }
                    .frame(width: 46, height: 46)

                    if let badge = tile.badge {
                        BadgePill(text: badge)
                            // Nudged outside the icon's box so it reads as
                            // attached to the tile rather than inside it.
                            .offset(x: 16, y: -6)
                    }
                }

                Text(tile.label)
                    // §5.2: tile label 13 medium, 2 lines, centred.
                    .font(.system(size: 13, weight: .medium))
                    .foregroundStyle(Theme.text2)
                    .multilineTextAlignment(.center)
                    .lineLimit(2)
                    .fixedSize(horizontal: false, vertical: true)

                if let ribbon = tile.ribbon {
                    Text(ribbon)
                        .font(.system(size: 9, weight: .semibold))
                        .foregroundStyle(.white)
                        .padding(.horizontal, 6)
                        .padding(.vertical, 2.5)
                        .background(Theme.navy, in: Capsule())
                }
            }
            .frame(width: 78)
            .frame(minHeight: Metrics.minimumTapTarget)
        }
        .buttonStyle(.plain)
        .accessibilityLabel(tile.label.replacingOccurrences(of: "\n", with: " "))
    }
}

/// A UPI-row tile: white filled symbol on a navy circle (§5.3 item 3).
struct FilledTile: View {
    let tile: HomeConfig.Tile
    let onTap: (HomeConfig.Tile) -> Void

    var body: some View {
        Button {
            onTap(tile)
        } label: {
            VStack(spacing: 8) {
                Image(systemName: tile.symbol)
                    .font(.system(size: 23, weight: .medium))
                    .foregroundStyle(.white)
                    .frame(width: Metrics.iconCircle, height: Metrics.iconCircle)
                    .background(Theme.navyIcon, in: Circle())

                Text(tile.label)
                    .font(.system(size: 13, weight: .medium))
                    .foregroundStyle(Theme.text2)
                    .multilineTextAlignment(.center)
                    .lineLimit(2)
                    .fixedSize(horizontal: false, vertical: true)
            }
            .frame(maxWidth: .infinity)
        }
        .buttonStyle(.plain)
        .accessibilityLabel(tile.label.replacingOccurrences(of: "\n", with: " "))
    }
}

/// The yellow "NEW" / "SIP @ ₹21" badge. Dark text, per §5.2.
struct BadgePill: View {
    let text: String

    var body: some View {
        Text(text)
            .font(.system(size: 9, weight: .heavy))
            .foregroundStyle(Theme.text1)
            .padding(.horizontal, 5)
            .padding(.vertical, 2)
            .background(Theme.badgeNew, in: Capsule())
    }
}

/// A grey outline chip, e.g. "Refer & Win ₹400".
struct HomeChip: View {
    let chip: HomeConfig.Chip
    let onTap: () -> Void

    var body: some View {
        Button(action: onTap) {
            Text(chip.label)
                // §5.2: chip 13.
                .font(.system(size: 13, weight: .medium))
                .foregroundStyle(chip.tint ?? Theme.text2)
                .padding(.horizontal, 12)
                .padding(.vertical, 8)
                .background(
                    Capsule().strokeBorder(Theme.hairline, lineWidth: 1)
                )
        }
        .buttonStyle(.plain)
        .frame(minHeight: Metrics.minimumTapTarget)
    }
}

/// A horizontally scrolling row of chips.
struct ChipRow: View {
    let chips: [HomeConfig.Chip]
    let onTap: () -> Void

    var body: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 8) {
                ForEach(chips) { chip in
                    HomeChip(chip: chip, onTap: onTap)
                }
            }
        }
        // Lets the chips bleed to the card edge while keeping their own inset,
        // which is how the reference screenshots look.
        .scrollClipDisabled()
    }
}

/// The soft pulsing sky ring behind the Spasht-enabled Loan tile (§5.3 item 10).
///
/// Announced to VoiceOver by its parent tile, not here: the animation is
/// decoration and a second announcement would just be noise.
struct PulsingRing: View {
    @State private var expanded = false

    var body: some View {
        Circle()
            .strokeBorder(Theme.sky.opacity(expanded ? 0.05 : 0.45), lineWidth: 2)
            .scaleEffect(expanded ? 1.35 : 0.85)
            .frame(width: 44, height: 44)
            .animation(
                .easeInOut(duration: 1.6).repeatForever(autoreverses: false),
                value: expanded
            )
            .onAppear { expanded = true }
            .allowsHitTesting(false)
    }
}

/// The small "scroll for more" indicator under a horizontal row (§5.3 item 4).
struct ScrollIndicatorPill: View {
    var body: some View {
        Capsule()
            .fill(Theme.hairline)
            .frame(width: 44, height: 3.5)
            .overlay(alignment: .leading) {
                Capsule()
                    .fill(Theme.iconLine.opacity(0.55))
                    .frame(width: 18, height: 3.5)
            }
            .frame(maxWidth: .infinity)
    }
}
