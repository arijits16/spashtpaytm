import SwiftUI

/// Every tile, chip and label on the home screen (build plan §5.3).
///
/// The home screen is sixteen sections of near-identical rows, so they are data
/// here and the views are small. Checking the layout against the reference
/// screenshots means editing this file, not hunting through SwiftUI.
///
/// **Legal guardrails (§5.1), enforced by construction:**
/// - no official Paytm logo artwork anywhere; the wordmark is plain text;
/// - partners are generic placeholders ("Partner Life A"), never real brands;
/// - only `Loan` is `live`. Everything else opens the concept sheet, which it
///   cannot avoid doing because `HomeAction` has no other case for it.
enum HomeConfig {

    /// What tapping a tile does.
    enum Action: Equatable {
        /// Opens the Spasht journey. Exactly one tile has this.
        case spasht
        /// Opens the "concept demo" sheet (§5.1).
        case concept
    }

    /// One tile in a grid or horizontal row.
    struct Tile: Identifiable, Equatable {
        let id: String
        let label: String
        let symbol: String
        var action: Action = .concept
        /// Overrides the default outline-blue icon tint.
        var tint: Color?
        /// Yellow "NEW" badge (§5.3 item 10).
        var badge: String?
        /// The small navy ribbon under the Loan tile.
        var ribbon: String?
        /// Draws the soft pulsing sky ring. Only the Spasht tile has it.
        var pulses: Bool = false
    }

    /// A pill under a section, e.g. "₹1200* OFF on Flights".
    struct Chip: Identifiable, Equatable {
        let id: String
        let label: String
        var tint: Color?
    }

    // MARK: - 1. Top bar

    /// Two-line promo text. The asterisks are deliberate: the reference screen
    /// has them, and they are what makes it read as a real promo strip.
    static let promoRedLine = "Festive offers on bills*"
    static let promoBlackLine = "with 20% Cashback*"

    // MARK: - 2. Promo carousel

    struct Slide: Identifiable, Equatable {
        let id: String
        let title: String
        let subtitle: String
        let cta: String
        let action: Action
        let colors: [Color]
        /// Draws the mic illustration with pulsing rings (slide 1 only).
        var showsMic: Bool = false
        var titleColor: Color = .white
        var subtitleColor: Color = .white.opacity(0.85)
    }

    static let slides: [Slide] = [
        Slide(
            id: "spasht",
            title: "Loan, ab aapki bhasha mein",
            subtitle: "Bolo · Samjho · Spasht",
            cta: "Try Spasht →",
            action: .spasht,
            colors: [Theme.navy, Theme.sky],
            showsMic: true
        ),
        Slide(
            id: "bills",
            title: "Pay your household bills",
            subtitle: "Earn reward coins on every bill",
            cta: "Pay Now →",
            action: .concept,
            colors: [Color(hex: 0xFFF3D6), Color(hex: 0xE8C97A)],
            titleColor: Theme.text1,
            subtitleColor: Theme.text2
        ),
        Slide(
            id: "recharge",
            title: "Cashback on recharges",
            subtitle: "Up to ₹50 back on every recharge",
            cta: "Recharge →",
            action: .concept,
            colors: [Color(hex: 0xE3F2FD), Color(hex: 0xBBDEFB)],
            titleColor: Theme.text1,
            subtitleColor: Theme.text2
        ),
    ]

    /// §5.3: the carousel advances every 4 s.
    static let carouselInterval: TimeInterval = 4

    // MARK: - 3. UPI money transfer

    /// White filled symbols on navy circles — the only section styled that way.
    static let upiTiles: [Tile] = [
        Tile(id: "upi.scan", label: "Scan any\nQR", symbol: "qrcode.viewfinder"),
        Tile(id: "upi.pay", label: "Pay\nAnyone", symbol: "indianrupeesign.circle.fill"),
        Tile(id: "upi.bank", label: "To Bank &\nSelf A/c", symbol: "building.columns.fill"),
        Tile(id: "upi.balance", label: "Balance &\nHistory", symbol: "list.bullet.rectangle.fill"),
    ]

    // MARK: - 4. Recharge & bills

    static let rechargeTiles: [Tile] = [
        Tile(id: "rb.mobile", label: "Mobile\nRecharge", symbol: "iphone"),
        Tile(id: "rb.cc", label: "Credit Card\nBill", symbol: "creditcard"),
        Tile(id: "rb.electricity", label: "Electricity\nBill", symbol: "lightbulb"),
        Tile(id: "rb.fastag", label: "FASTag\nRecharge", symbol: "car"),
        Tile(id: "rb.emi", label: "Loan EMI\nPayment", symbol: "calendar.badge.clock"),
        Tile(id: "rb.dth", label: "DTH", symbol: "tv"),
        Tile(id: "rb.gas", label: "Gas", symbol: "flame"),
    ]

    // MARK: - 6. Two-column grid

    static let postpaidTitle = "Paytm Postpaid"
    static let postpaidSubtitle = "Start using with up to ₹1 Lakh limit"

    // MARK: - 7. Chips row

    static let topChips: [Chip] = [
        Chip(id: "chip.refer", label: "Refer & Win ₹400"),
        Chip(id: "chip.cashback", label: "Cashback & Offers"),
        Chip(id: "chip.lite", label: "UPI Lite"),
    ]

    // MARK: - 8. Travel & tickets

    static let travelTiles: [Tile] = [
        Tile(id: "tr.flight", label: "Flight", symbol: "airplane"),
        Tile(id: "tr.train", label: "Train", symbol: "tram.fill"),
        Tile(id: "tr.bus", label: "Bus", symbol: "bus"),
        Tile(id: "tr.hotel", label: "Hotels", symbol: "bed.double"),
    ]

    static let travelChips: [Chip] = [
        Chip(id: "tr.c1", label: "₹1200* OFF on Flights"),
        Chip(id: "tr.c2", label: "15% Off* on Bus"),
    ]

    // MARK: - 9. Grow your money

    static let growTiles: [Tile] = [
        Tile(id: "gw.gold", label: "Save in\nGold", symbol: "circle.hexagongrid.fill",
             tint: Color(hex: 0xD4A017)),
        Tile(id: "gw.silver", label: "Save in\nSilver", symbol: "circle.hexagongrid",
             tint: Color(hex: 0x8E9AAF)),
        Tile(id: "gw.mf", label: "Mutual\nFund", symbol: "chart.line.uptrend.xyaxis",
             badge: "SIP @ ₹21"),
        Tile(id: "gw.ipo", label: "Apply for\nIPOs", symbol: "doc.text.magnifyingglass"),
    ]

    // MARK: - 10. Loans & insurance  ★ the one live feature

    static let loanTile = Tile(
        id: "loan.spasht",
        label: "Loan",
        symbol: "indianrupeesign.square",
        action: .spasht,
        badge: "NEW",
        ribbon: "Spasht · मराठी / हिंदी",
        pulses: true
    )

    static let loanTiles: [Tile] = [
        loanTile,
        Tile(id: "loan.postpaid", label: "Paytm\nPostpaid", symbol: "creditcard.circle"),
        Tile(id: "loan.car", label: "Car\nInsurance", symbol: "car.circle"),
        Tile(id: "loan.health", label: "Health\nInsurance", symbol: "heart.circle.fill",
             tint: Theme.danger),
    ]

    static let loanChips: [Chip] = [
        Chip(id: "loan.c1", label: "Get Credit Card"),
        Chip(id: "loan.c2", label: "Bike Insurance"),
    ]

    // MARK: - 11. Free tools

    struct ToolCard: Identifiable, Equatable {
        let id: String
        let title: String
        let background: Color
        /// Which illustration the view draws.
        let kind: Kind

        enum Kind: Equatable {
            /// A gauge with a placeholder score.
            case creditScore(Int)
            case roundUp
            /// Made-up amounts (§5.3 item 11) — invented, never real spending.
            case spends([String])
        }
    }

    static let toolCards: [ToolCard] = [
        ToolCard(
            id: "tool.score",
            title: "Check Your\nCredit Score",
            background: Color(hex: 0xDFF5E8),
            kind: .creditScore(750)
        ),
        ToolCard(
            id: "tool.roundup",
            title: "Round Up\nSpends In Gold",
            background: Color(hex: 0xFFF3D6),
            kind: .roundUp
        ),
        ToolCard(
            id: "tool.spends",
            title: "Track Your\nSpends",
            background: Color(hex: 0xFDE7EF),
            kind: .spends(["₹1,250", "₹3,480", "₹860"])
        ),
    ]

    // MARK: - 12. Do more

    static let doMoreTiles: [Tile] = [
        Tile(id: "dm.deals", label: "Claim\nDeals", symbol: "tag"),
        Tile(id: "dm.vouchers", label: "Gift\nVouchers", symbol: "giftcard"),
        Tile(id: "dm.cashback", label: "Cashback\n& Offers", symbol: "sparkles"),
        Tile(id: "dm.all", label: "See All\nServices", symbol: "square.grid.2x2"),
    ]

    static let doMoreChips: [Chip] = [
        Chip(id: "dm.c1", label: "App Store | 4% Off"),
        Chip(id: "dm.c2", label: "Deals Near You | 50% OFF"),
    ]

    // MARK: - 13. Promoted

    /// Generic placeholders only (§5.1). Initials in a coloured circle, never a
    /// real partner's name or mark.
    struct Partner: Identifiable, Equatable {
        let id: String
        let name: String
        let initials: String
        let colour: Color
    }

    static let partners: [Partner] = [
        Partner(id: "p.a", name: "Partner Life A", initials: "LA", colour: Color(hex: 0x1565E5)),
        Partner(id: "p.b", name: "Partner Bank B", initials: "BB", colour: Color(hex: 0x0B6B4F)),
        Partner(id: "p.c", name: "Partner Gen C", initials: "GC", colour: Color(hex: 0xB0275A)),
        Partner(id: "p.d", name: "Partner Fin D", initials: "FD", colour: Color(hex: 0x1E3A7A)),
    ]

    // MARK: - 14. Referral card

    static let referralTitle = "You ❤ Paytm"
    static let referralSubtitle = "Your referral streak unlocks Assured ₹400 →"

    // MARK: - 15. Floating pill

    static let scanPillLabel = "Scan QR"

    // MARK: - 16. First-visit tooltip

    static let tooltipText = "New: loans in Marathi & Hindi →"
    /// `@AppStorage` key, so the tooltip is shown exactly once per install.
    static let tooltipSeenKey = "spasht.home.tooltipSeen"
}
