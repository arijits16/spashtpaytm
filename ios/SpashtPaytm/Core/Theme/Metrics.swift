import SwiftUI

/// Spacing, radii and sizes from build plan §5.2.
///
/// Named constants rather than literals scattered through the views: the home
/// screen is checked side by side against the reference screenshots, and a
/// one-off `padding(16)` is exactly the kind of drift that is hard to spot.
enum Metrics {

    // MARK: - Spacing

    /// Left and right padding on every screen.
    static let screenPadding: CGFloat = 14
    /// Vertical gap between section cards.
    static let cardGap: CGFloat = 12
    /// Padding inside a card.
    static let cardPadding: CGFloat = 18

    // MARK: - Shape

    /// Section cards. Continuous, not circular — it is visibly softer.
    static let cardRadius: CGFloat = 20
    /// Promo banners and carousel slides.
    static let bannerRadius: CGFloat = 16

    /// Circles behind the UPI row icons.
    static let iconCircle: CGFloat = 56
    /// The top-bar avatar.
    static let avatar: CGFloat = 44

    /// The journey's mic button (§5.6).
    static let micButton: CGFloat = 72

    /// Apple's minimum, and the floor for every control in this app.
    static let minimumTapTarget: CGFloat = 44

    // MARK: - Helpers

    /// The standard card shape.
    static var cardShape: RoundedRectangle {
        RoundedRectangle(cornerRadius: cardRadius, style: .continuous)
    }

    /// The standard banner shape.
    static var bannerShape: RoundedRectangle {
        RoundedRectangle(cornerRadius: bannerRadius, style: .continuous)
    }
}

extension View {
    /// Apply the standard white card treatment: padding, fill, continuous corners.
    ///
    /// Cards are flat by design (§5.2) — only the floating Scan QR pill has a
    /// shadow, so adding one here would make every section look wrong.
    func spashtCard(padding: CGFloat = Metrics.cardPadding) -> some View {
        self
            .padding(padding)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(Theme.card, in: Metrics.cardShape)
    }

    /// Guarantee a control is at least 44×44 pt, whatever its content measures.
    func spashtTappable() -> some View {
        frame(minWidth: Metrics.minimumTapTarget, minHeight: Metrics.minimumTapTarget)
            .contentShape(Rectangle())
    }
}
