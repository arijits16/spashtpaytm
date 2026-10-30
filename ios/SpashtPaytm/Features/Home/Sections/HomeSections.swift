import SwiftUI

/// The sixteen home sections (build plan §5.3), in order.
///
/// Each is a small view over `HomeConfig`, so the order and content of the home
/// screen is readable in one place (`HomeView`) and the styling lives in
/// `HomeComponents`.

// MARK: - 1. Top bar

struct HomeTopBar: View {
    let initials: String
    let photoURL: URL?
    let onAvatar: () -> Void
    let onConcept: () -> Void

    var body: some View {
        HStack(spacing: 12) {
            Button(action: onAvatar) {
                Avatar(initials: initials, photoURL: photoURL, size: Metrics.avatar)
            }
            .buttonStyle(.plain)
            .accessibilityLabel("Profile")

            VStack(alignment: .leading, spacing: 1) {
                Text(HomeConfig.promoRedLine)
                    .font(.system(size: 12, weight: .semibold))
                    .foregroundStyle(Theme.promoRed)
                HStack(spacing: 4) {
                    Text(HomeConfig.promoBlackLine)
                        .font(.system(size: 13, weight: .semibold))
                        .foregroundStyle(Theme.text1)
                    Image(systemName: "chevron.right")
                        .font(.system(size: 7, weight: .bold))
                        .foregroundStyle(.white)
                        .frame(width: 14, height: 14)
                        .background(Theme.sky, in: Circle())
                }
            }

            Spacer(minLength: 4)

            ForEach(["magnifyingglass", "bell"], id: \.self) { symbol in
                Button(action: onConcept) {
                    Image(systemName: symbol)
                        .font(.system(size: 19, weight: .medium))
                        .foregroundStyle(Theme.text1)
                        .frame(width: Metrics.minimumTapTarget, height: Metrics.minimumTapTarget)
                }
                .buttonStyle(.plain)
                .accessibilityLabel(symbol == "bell" ? "Notifications" : "Search")
            }
        }
    }
}

/// The user's photo, or their initials on the §5.2 avatar green.
struct Avatar: View {
    let initials: String
    let photoURL: URL?
    let size: CGFloat

    var body: some View {
        ZStack {
            Circle().fill(Theme.avatarBackground)
            if let photoURL {
                AsyncImage(url: photoURL) { image in
                    image.resizable().scaledToFill()
                } placeholder: {
                    initialsText
                }
                .clipShape(Circle())
            } else {
                initialsText
            }
        }
        .frame(width: size, height: size)
    }

    private var initialsText: some View {
        Text(initials)
            .font(.system(size: size * 0.36, weight: .semibold))
            .foregroundStyle(Theme.navy)
    }
}

// MARK: - 2. Promo carousel

struct PromoCarousel: View {
    let onAction: (HomeConfig.Action) -> Void

    @State private var index = 0
    /// Paused while the app is backgrounded: a timer firing behind the privacy
    /// cover would land the user on a different slide than they left.
    @Environment(\.scenePhase) private var scenePhase

    var body: some View {
        VStack(spacing: 8) {
            TabView(selection: $index) {
                ForEach(Array(HomeConfig.slides.enumerated()), id: \.element.id) { offset, slide in
                    PromoSlide(slide: slide, onAction: onAction)
                        .tag(offset)
                }
            }
            .tabViewStyle(.page(indexDisplayMode: .never))
            .frame(height: 180)

            HStack(spacing: 6) {
                ForEach(HomeConfig.slides.indices, id: \.self) { dot in
                    Capsule()
                        .fill(dot == index ? Theme.navy : Theme.hairline)
                        .frame(width: dot == index ? 16 : 6, height: 6)
                        .animation(.easeInOut(duration: 0.2), value: index)
                }
            }
        }
        .task(id: scenePhase) {
            guard scenePhase == .active else { return }
            await advanceForever()
        }
    }

    /// Auto-advance every 4 s (§5.3 item 2).
    private func advanceForever() async {
        while !Task.isCancelled {
            try? await Task.sleep(for: .seconds(HomeConfig.carouselInterval))
            guard !Task.isCancelled else { return }
            withAnimation(.easeInOut(duration: 0.4)) {
                index = (index + 1) % HomeConfig.slides.count
            }
        }
    }
}

private struct PromoSlide: View {
    let slide: HomeConfig.Slide
    let onAction: (HomeConfig.Action) -> Void

    var body: some View {
        Button {
            onAction(slide.action)
        } label: {
            ZStack(alignment: .leading) {
                LinearGradient(colors: slide.colors, startPoint: .topLeading, endPoint: .bottomTrailing)

                if slide.showsMic {
                    MicIllustration()
                        .frame(maxWidth: .infinity, alignment: .trailing)
                        .padding(.trailing, 26)
                }

                VStack(alignment: .leading, spacing: 6) {
                    Text(slide.title)
                        .font(.system(size: 21, weight: .bold))
                        .foregroundStyle(slide.titleColor)
                        .fixedSize(horizontal: false, vertical: true)
                    Text(slide.subtitle)
                        .font(.system(size: 13, weight: .medium))
                        .foregroundStyle(slide.subtitleColor)

                    Text(slide.cta)
                        .font(.system(size: 13, weight: .bold))
                        .foregroundStyle(Theme.navy)
                        .padding(.horizontal, 14)
                        .padding(.vertical, 8)
                        .background(.white, in: Capsule())
                        .padding(.top, 4)
                }
                .padding(20)
                .frame(maxWidth: 230, alignment: .leading)
            }
            .clipShape(RoundedRectangle(cornerRadius: Metrics.bannerRadius, style: .continuous))
        }
        .buttonStyle(.plain)
        .padding(.horizontal, Metrics.screenPadding)
    }
}

/// A mic with pulsing rings, drawn rather than imported — no logo artwork (§5.1).
private struct MicIllustration: View {
    @State private var pulse = false

    var body: some View {
        ZStack {
            ForEach([1.0, 1.45, 1.9], id: \.self) { scale in
                Circle()
                    .strokeBorder(.white.opacity(pulse ? 0.05 : 0.3), lineWidth: 1.5)
                    .frame(width: 42 * scale, height: 42 * scale)
            }
            Image(systemName: "mic.fill")
                .font(.system(size: 22, weight: .semibold))
                .foregroundStyle(Theme.navy)
                .frame(width: 44, height: 44)
                .background(.white, in: Circle())
        }
        .animation(.easeInOut(duration: 1.8).repeatForever(autoreverses: true), value: pulse)
        .onAppear { pulse = true }
        .allowsHitTesting(false)
    }
}

// MARK: - 3. UPI money transfer

struct UpiSection: View {
    let onTile: (HomeConfig.Tile) -> Void

    var body: some View {
        SectionCard {
            SectionHeader(title: "UPI Money Transfer")
            HStack(alignment: .top, spacing: 4) {
                ForEach(HomeConfig.upiTiles) { tile in
                    FilledTile(tile: tile, onTap: onTile)
                }
            }
        }
    }
}

// MARK: - 4. Recharge & bills

struct RechargeSection: View {
    let onTile: (HomeConfig.Tile) -> Void
    let onConcept: () -> Void

    var body: some View {
        SectionCard {
            SectionHeader(title: "Recharge & Bills", viewAll: onConcept)
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(alignment: .top, spacing: 2) {
                    ForEach(HomeConfig.rechargeTiles) { tile in
                        OutlineTile(tile: tile, onTap: onTile)
                    }
                }
            }
            .scrollClipDisabled()
            ScrollIndicatorPill()
        }
    }
}

// MARK: - 5. Exclusive offer strip

struct OfferStrip: View {
    let onTap: () -> Void

    var body: some View {
        Button(action: onTap) {
            HStack(spacing: 12) {
                Image(systemName: "gift.fill")
                    .font(.system(size: 19))
                    .foregroundStyle(Theme.navy)
                VStack(alignment: .leading, spacing: 1) {
                    Text("Exclusive offer for You!")
                        .font(.system(size: 14, weight: .bold))
                        .foregroundStyle(Theme.text1)
                    Text("Claim your exclusive reward")
                        .font(.system(size: 12))
                        .foregroundStyle(Theme.text2)
                }
                Spacer()
                Image(systemName: "chevron.right")
                    .font(.system(size: 12, weight: .semibold))
                    .foregroundStyle(Theme.text3)
            }
            .padding(14)
            .background(Theme.offerStrip, in: Metrics.cardShape)
        }
        .buttonStyle(.plain)
    }
}

// MARK: - 6. Two-column grid

struct PostpaidGrid: View {
    let onTap: () -> Void

    var body: some View {
        HStack(spacing: Metrics.cardGap) {
            Button(action: onTap) {
                VStack(alignment: .leading, spacing: 8) {
                    Image(systemName: "creditcard.fill")
                        .font(.system(size: 24))
                        .foregroundStyle(Theme.navy)
                    Spacer(minLength: 10)
                    Text(HomeConfig.postpaidTitle)
                        .font(.system(size: 15, weight: .bold))
                        .foregroundStyle(Theme.text1)
                    Text(HomeConfig.postpaidSubtitle)
                        .font(.system(size: 12))
                        .foregroundStyle(Theme.text2)
                        .fixedSize(horizontal: false, vertical: true)
                }
                .padding(16)
                .frame(maxWidth: .infinity, minHeight: 168, alignment: .topLeading)
                .background(Theme.card, in: Metrics.cardShape)
            }
            .buttonStyle(.plain)

            VStack(spacing: Metrics.cardGap) {
                SmallCard(title: "Refer & Win", symbol: "person.2.fill", onTap: onTap)
                SmallCard(title: "Save in Gold", symbol: "circle.hexagongrid.fill",
                          tint: Color(hex: 0xD4A017), onTap: onTap)
            }
            .frame(maxWidth: .infinity)
        }
    }
}

private struct SmallCard: View {
    let title: String
    let symbol: String
    var tint: Color = Theme.navy
    let onTap: () -> Void

    var body: some View {
        Button(action: onTap) {
            VStack(alignment: .leading, spacing: 6) {
                Image(systemName: symbol)
                    .font(.system(size: 19))
                    .foregroundStyle(tint)
                Text(title)
                    .font(.system(size: 13, weight: .semibold))
                    .foregroundStyle(Theme.text1)
            }
            .padding(14)
            .frame(maxWidth: .infinity, minHeight: 78, alignment: .topLeading)
            .background(Theme.card, in: Metrics.cardShape)
        }
        .buttonStyle(.plain)
    }
}

// MARK: - 8, 9, 10, 12. Tile sections

/// A titled card with a tile row and optional chips. Four sections share it.
struct TileSection: View {
    let title: String
    let tiles: [HomeConfig.Tile]
    var chips: [HomeConfig.Chip] = []
    var scrolls = false
    let onTile: (HomeConfig.Tile) -> Void
    let onConcept: () -> Void

    var body: some View {
        SectionCard {
            SectionHeader(title: title)

            if scrolls {
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(alignment: .top, spacing: 2) { tileViews }
                }
                .scrollClipDisabled()
            } else {
                HStack(alignment: .top, spacing: 2) { tileViews }
            }

            if !chips.isEmpty {
                ChipRow(chips: chips, onTap: onConcept)
            }
        }
    }

    private var tileViews: some View {
        ForEach(tiles) { tile in
            OutlineTile(tile: tile, onTap: onTile)
        }
    }
}

// MARK: - 11. Free tools

struct FreeToolsSection: View {
    let onTap: () -> Void

    var body: some View {
        SectionCard {
            SectionHeader(title: "Free Tools")
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 10) {
                    ForEach(HomeConfig.toolCards) { card in
                        ToolCardView(card: card, onTap: onTap)
                    }
                }
            }
            .scrollClipDisabled()
        }
    }
}

private struct ToolCardView: View {
    let card: HomeConfig.ToolCard
    let onTap: () -> Void

    var body: some View {
        Button(action: onTap) {
            VStack(alignment: .leading, spacing: 10) {
                Text(card.title)
                    .font(.system(size: 13, weight: .bold))
                    .foregroundStyle(Theme.text1)
                    .multilineTextAlignment(.leading)
                    .fixedSize(horizontal: false, vertical: true)
                Spacer(minLength: 0)
                illustration
            }
            .padding(12)
            // §5.3 item 11: about 130x150.
            .frame(width: 130, height: 150, alignment: .topLeading)
            .background(card.background, in: Metrics.cardShape)
        }
        .buttonStyle(.plain)
    }

    @ViewBuilder
    private var illustration: some View {
        switch card.kind {
        case .creditScore(let score):
            // A placeholder score (§5.3): invented, and labelled as a demo by
            // the concept ribbon above it.
            ZStack {
                Circle()
                    .trim(from: 0.0, to: 0.7)
                    .stroke(Theme.success, style: StrokeStyle(lineWidth: 6, lineCap: .round))
                    .rotationEffect(.degrees(145))
                Text("\(score)")
                    .font(.system(size: 15, weight: .heavy))
                    .foregroundStyle(Theme.text1)
            }
            .frame(width: 54, height: 54)

        case .roundUp:
            Image(systemName: "arrow.up.circle.fill")
                .font(.system(size: 34))
                .foregroundStyle(Color(hex: 0xD4A017))

        case .spends(let amounts):
            HStack(alignment: .bottom, spacing: 5) {
                ForEach(Array(amounts.enumerated()), id: \.offset) { offset, amount in
                    VStack(spacing: 3) {
                        RoundedRectangle(cornerRadius: 2)
                            .fill(Theme.navy.opacity(0.75))
                            .frame(width: 11, height: [18.0, 34.0, 13.0][offset])
                        Text(amount)
                            .font(.system(size: 7, weight: .semibold))
                            .foregroundStyle(Theme.text2)
                    }
                }
            }
        }
    }
}

// MARK: - 13. Promoted

struct PromotedSection: View {
    let onTap: () -> Void

    var body: some View {
        SectionCard {
            SectionHeader(title: "Promoted")
            HStack(spacing: 4) {
                ForEach(HomeConfig.partners) { partner in
                    Button(action: onTap) {
                        VStack(spacing: 7) {
                            Text(partner.initials)
                                .font(.system(size: 17, weight: .bold))
                                .foregroundStyle(.white)
                                .frame(width: Metrics.iconCircle, height: Metrics.iconCircle)
                                .background(partner.colour, in: Circle())
                            Text(partner.name)
                                .font(.system(size: 11, weight: .medium))
                                .foregroundStyle(Theme.text2)
                                .multilineTextAlignment(.center)
                                .lineLimit(2)
                                .fixedSize(horizontal: false, vertical: true)
                        }
                        .frame(maxWidth: .infinity)
                    }
                    .buttonStyle(.plain)
                }
            }
        }
    }
}

// MARK: - 14. Referral card

struct ReferralCard: View {
    let onTap: () -> Void

    var body: some View {
        Button(action: onTap) {
            HStack(spacing: 14) {
                VStack(alignment: .leading, spacing: 5) {
                    Text(HomeConfig.referralTitle)
                        .font(.system(size: 16, weight: .bold))
                        .foregroundStyle(Theme.navy)
                    Text(HomeConfig.referralSubtitle)
                        .font(.system(size: 12, weight: .medium))
                        .foregroundStyle(Theme.text2)
                        .fixedSize(horizontal: false, vertical: true)
                    Text("T&C apply")
                        .font(.system(size: 9))
                        .foregroundStyle(Theme.text3)
                }
                Spacer(minLength: 6)
                GiftGraphic()
            }
            .padding(Metrics.cardPadding)
            .background(Theme.card, in: Metrics.cardShape)
        }
        .buttonStyle(.plain)
    }
}

/// A drawn gift, not an image asset — nothing is imported artwork (§5.1).
private struct GiftGraphic: View {
    var body: some View {
        ZStack {
            RoundedRectangle(cornerRadius: 6)
                .fill(Theme.sky.opacity(0.25))
                .frame(width: 52, height: 40)
            Rectangle()
                .fill(Theme.navy)
                .frame(width: 7, height: 40)
            RoundedRectangle(cornerRadius: 3)
                .fill(Theme.navy)
                .frame(width: 56, height: 8)
                .offset(y: -16)
        }
        .frame(width: 60, height: 52)
    }
}

// MARK: - 15. Floating pill

struct ScanQrPill: View {
    let onTap: () -> Void

    var body: some View {
        Button(action: onTap) {
            HStack(spacing: 10) {
                Image(systemName: "qrcode.viewfinder")
                    .font(.system(size: 21, weight: .medium))
                Text(HomeConfig.scanPillLabel)
                    .font(.system(size: 17, weight: .bold))
            }
            .foregroundStyle(.white)
            // §5.3 item 15: about 220x60, navy gradient, 2pt light-blue border.
            .frame(width: 220, height: 56)
            .background(Theme.navyGradient, in: Capsule())
            .overlay(Capsule().strokeBorder(Theme.sky.opacity(0.65), lineWidth: 2))
            .shadow(color: Theme.navy.opacity(0.28), radius: 12, y: 5)
        }
        .buttonStyle(.plain)
        .padding(.bottom, 10)
    }
}

// MARK: - 16. First-visit tooltip

struct FirstVisitTooltip: View {
    let onTap: () -> Void
    let onDismiss: () -> Void

    var body: some View {
        HStack(spacing: 8) {
            Image(systemName: "sparkles")
                .font(.system(size: 13))
                .foregroundStyle(Theme.badgeNew)
            Text(HomeConfig.tooltipText)
                .font(.system(size: 13, weight: .semibold))
                .foregroundStyle(.white)
            Spacer(minLength: 4)
            Button(action: onDismiss) {
                Image(systemName: "xmark")
                    .font(.system(size: 11, weight: .bold))
                    .foregroundStyle(.white.opacity(0.8))
                    .frame(width: 30, height: 30)
            }
            .buttonStyle(.plain)
            .accessibilityLabel("Dismiss")
        }
        .padding(.leading, 14)
        .padding(.trailing, 4)
        .padding(.vertical, 6)
        .background(Theme.navy, in: Capsule())
        .onTapGesture(perform: onTap)
    }
}
