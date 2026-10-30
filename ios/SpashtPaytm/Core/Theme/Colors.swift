import SwiftUI

/// The design tokens from build plan §5.2, as SwiftUI colours.
///
/// The same values are defined for the website in
/// `frontend/src/styles/index.css` (`@theme`). When one changes, change both —
/// the dashboard and the app are shown side by side during the demo.
///
/// Light mode only: the app sets `.preferredColorScheme(.light)` and the
/// Info.plist pins `UIUserInterfaceStyle`, so these are plain colours rather
/// than appearance-aware assets.
enum Theme {

    // MARK: - Surfaces

    /// App background behind the cards.
    static let bg = Color(hex: 0xF3F4F6)
    /// Section cards.
    static let card = Color(hex: 0xFFFFFF)

    // MARK: - Brand

    /// Wordmark, primary buttons, user bubbles.
    static let navy = Color(hex: 0x002E6E)
    /// Filled circles behind the UPI icons.
    static let navyIcon = Color(hex: 0x0F3D86)
    /// Accents, the top half of the QR border, progress.
    static let sky = Color(hex: 0x00BAF2)
    /// "View All →".
    static let link = Color(hex: 0x1F6FEB)
    /// Outline icons.
    static let iconLine = Color(hex: 0x1D5BD0)

    /// Floating "Scan QR" pill, top to bottom.
    static let navyGradient = LinearGradient(
        colors: [Color(hex: 0x1A4FA6), Color(hex: 0x0B3A82)],
        startPoint: .top,
        endPoint: .bottom
    )

    /// Login and privacy-cover background (§5.5, §5.10).
    static let loginGradient = LinearGradient(
        colors: [Color(hex: 0xE6F6FD), Color(hex: 0xFFFFFF), Color(hex: 0xE6F6FD)],
        startPoint: .top,
        endPoint: .bottom
    )

    // MARK: - Text

    /// Titles.
    static let text1 = Color(hex: 0x1C1C1E)
    /// Labels.
    static let text2 = Color(hex: 0x3A3A3C)
    /// Secondary text.
    static let text3 = Color(hex: 0x6B7280)

    // MARK: - Accents

    /// "Exclusive offer" strip.
    static let offerStrip = Color(hex: 0xD6F1FA)
    /// Promo text in the top bar.
    static let promoRed = Color(hex: 0xD32F2F)
    /// "New" badges — dark text on this.
    static let badgeNew = Color(hex: 0xFFE14D)
    /// Pink alert strip in the profile card.
    static let alertPink = Color(hex: 0xFDECEC)

    // MARK: - Status

    /// Verified, correct answers.
    static let success = Color(hex: 0x12B76A)
    /// Red flags, tampered receipts.
    static let danger = Color(hex: 0xD92D20)
    /// "Low rate, high fees".
    static let warning = Color(hex: 0xF79009)

    /// Profile-completion cards, in order (§5.4).
    static let profileTiles = [
        Color(hex: 0x1565E5),
        Color(hex: 0x0B6B4F),
        Color(hex: 0xB0275A),
        Color(hex: 0x1E3A7A),
    ]

    /// Avatar background when the user has no Google photo (§5.3).
    static let avatarBackground = Color(hex: 0xD9E8C4)

    /// Hairline borders on assistant bubbles and cards.
    static let hairline = Color(hex: 0xE5E7EB)
}

extension Color {
    /// Build a colour from a 24-bit RGB literal, e.g. `Color(hex: 0x002E6E)`.
    ///
    /// Using sRGB explicitly rather than the default colour space, so the navy
    /// on the phone matches the navy in the dashboard on the projector.
    init(hex: UInt32) {
        self.init(
            .sRGB,
            red: Double((hex >> 16) & 0xFF) / 255,
            green: Double((hex >> 8) & 0xFF) / 255,
            blue: Double(hex & 0xFF) / 255,
            opacity: 1
        )
    }
}
