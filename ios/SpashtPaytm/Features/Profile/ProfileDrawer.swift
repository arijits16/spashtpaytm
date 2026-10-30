import SwiftUI

/// The profile and QR drawer (build plan §5.4).
///
/// Slides in from the left over a dimmed backdrop, about 90% of the width. Drag
/// it or tap the backdrop to close.
///
/// One row in the settings list actually works - **Profile — Privacy,
/// Notification & Language**, which opens the language sheet and saves through
/// `PATCH /api/me`. The rest open the concept sheet. That is deliberate: the
/// drawer is here to make the app feel real, and the one setting a
/// language-first product must honour is the language.
struct ProfileDrawer: View {
    let auth: AuthService
    let me: Me
    let onClose: () -> Void
    let onProfileCompletion: () -> Void
    let onConcept: (String) -> Void

    @State private var dragOffset: CGFloat = 0
    @State private var showsLanguageSheet = false
    @State private var toast: String?
    @State private var qrPayload = QrCode.demoPayload()

    /// §5.4: about 90% of the screen width.
    private let widthFraction: CGFloat = 0.9

    var body: some View {
        GeometryReader { geometry in
            let panelWidth = geometry.size.width * widthFraction

            ZStack(alignment: .leading) {
                Color.black
                    .opacity(0.35)
                    .ignoresSafeArea()
                    .onTapGesture(perform: close)
                    .accessibilityLabel("Close profile")
                    .accessibilityAddTraits(.isButton)

                panel(width: panelWidth)
                    .frame(width: panelWidth)
                    .offset(x: dragOffset)
                    .gesture(dragGesture(panelWidth: panelWidth))
                    .transition(.move(edge: .leading))
            }
        }
        .sheet(isPresented: $showsLanguageSheet) {
            LanguageSheet(auth: auth, current: me.preferredLanguage)
        }
        .overlay(alignment: .bottom) {
            if let toast {
                Toast(message: toast)
                    .padding(.bottom, 40)
                    .transition(.move(edge: .bottom).combined(with: .opacity))
            }
        }
        .animation(.easeInOut(duration: 0.2), value: toast)
    }

    // MARK: - Panel

    private func panel(width: CGFloat) -> some View {
        VStack(spacing: 0) {
            header
            ScrollView {
                VStack(spacing: Metrics.cardGap) {
                    profileCard
                    qrCard
                    bankRow
                    settingsCard
                    securityRow
                    footer
                }
                .padding(.horizontal, Metrics.screenPadding)
                .padding(.bottom, 28)
            }
        }
        .frame(maxHeight: .infinity, alignment: .top)
        .background(Theme.bg.ignoresSafeArea())
    }

    private var header: some View {
        HStack {
            Button(action: close) {
                Image(systemName: "chevron.left")
                    .font(.system(size: 17, weight: .semibold))
                    .foregroundStyle(Theme.text1)
                    .frame(width: Metrics.minimumTapTarget, height: Metrics.minimumTapTarget)
            }
            .buttonStyle(.plain)
            .accessibilityLabel("Close")

            Spacer()
            Wordmark(size: 19)
            Spacer()

            // Balances the chevron so the wordmark is actually centred.
            Color.clear.frame(width: Metrics.minimumTapTarget, height: 1)
        }
        .padding(.horizontal, 4)
        .padding(.bottom, 4)
    }

    // MARK: - Profile card

    private var profileCard: some View {
        VStack(spacing: 0) {
            Button(action: onProfileCompletion) {
                VStack(spacing: 12) {
                    ZStack(alignment: .bottomTrailing) {
                        Avatar(
                            initials: me.initials,
                            photoURL: me.photoUrl.flatMap(URL.init(string:)),
                            size: 74
                        )
                        .overlay(
                            Circle().strokeBorder(
                                LinearGradient(
                                    colors: [Theme.sky, Theme.navy],
                                    startPoint: .top,
                                    endPoint: .bottom
                                ),
                                lineWidth: 2
                            )
                        )

                        Image(systemName: "camera.fill")
                            .font(.system(size: 9))
                            .foregroundStyle(.white)
                            .frame(width: 24, height: 24)
                            .background(Theme.navy, in: Circle())
                            .overlay(Circle().strokeBorder(.white, lineWidth: 2))
                    }

                    HStack(spacing: 5) {
                        Text(me.displayLabel)
                            .font(.system(size: 17, weight: .bold))
                            .foregroundStyle(Theme.text1)
                        Image(systemName: "checkmark.seal.fill")
                            .font(.system(size: 13))
                            .foregroundStyle(Theme.link)
                    }

                    upiRow
                }
                .frame(maxWidth: .infinity)
                .padding(.top, Metrics.cardPadding)
            }
            .buttonStyle(.plain)

            alertStrip
        }
        .background(Theme.card, in: Metrics.cardShape)
    }

    private var upiRow: some View {
        HStack(spacing: 6) {
            Text("UPI ID: \(upiId)")
                .font(.system(size: 12, weight: .medium))
                .foregroundStyle(Theme.text3)
            Button {
                // The only use of the pasteboard in the app (§13.11), and the
                // only thing it ever carries is this synthetic id.
                UIPasteboard.general.string = upiId
                toast = "UPI ID copied"
            } label: {
                Image(systemName: "doc.on.doc")
                    .font(.system(size: 11, weight: .medium))
                    .foregroundStyle(Theme.link)
                    .frame(width: 34, height: 34)
            }
            .buttonStyle(.plain)
            .accessibilityLabel("Copy UPI ID")
        }
    }

    /// A synthetic handle on a reserved-looking domain. Never a real VPA.
    private var upiId: String {
        let stem = (me.persona?.id ?? "demo").prefix(6)
        return "\(stem)-\(String(me.uid.suffix(4)))@ptdemo"
    }

    private var alertStrip: some View {
        HStack(spacing: 10) {
            Text("Receive money on Paytm from all UPI apps")
                .font(.system(size: 11.5, weight: .medium))
                .foregroundStyle(Theme.text2)
                .fixedSize(horizontal: false, vertical: true)
            Spacer(minLength: 4)
            Button {
                onConcept("Receive money")
            } label: {
                Text("Enable now")
                    .font(.system(size: 11, weight: .bold))
                    .foregroundStyle(.white)
                    .padding(.horizontal, 11)
                    .padding(.vertical, 7)
                    .background(Theme.navy, in: Capsule())
            }
            .buttonStyle(.plain)
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 10)
        .background(Theme.alertPink)
        .clipShape(
            UnevenRoundedRectangle(
                bottomLeadingRadius: Metrics.cardRadius,
                bottomTrailingRadius: Metrics.cardRadius,
                style: .continuous
            )
        )
        .padding(.top, 14)
    }

    // MARK: - QR card

    private var qrCard: some View {
        SectionCard {
            ZStack {
                // §5.4: the top half of the border is sky, the bottom navy.
                RoundedRectangle(cornerRadius: Metrics.bannerRadius, style: .continuous)
                    .strokeBorder(
                        LinearGradient(
                            stops: [
                                .init(color: Theme.sky, location: 0.5),
                                .init(color: Theme.navy, location: 0.5),
                            ],
                            startPoint: .top,
                            endPoint: .bottom
                        ),
                        lineWidth: 3
                    )

                if let code = QrCode.image(from: qrPayload) {
                    code
                        .interpolation(.none)
                        .resizable()
                        .scaledToFit()
                        .padding(18)
                }
            }
            .frame(height: 210)
            .frame(maxWidth: .infinity)

            Text("Demo QR · not a payment code")
                .font(.system(size: 10.5))
                .foregroundStyle(Theme.text3)
                .frame(maxWidth: .infinity, alignment: .center)
        }
    }

    private var bankRow: some View {
        SectionCard(padding: 14) {
            HStack(spacing: 10) {
                Image(systemName: "building.columns.fill")
                    .font(.system(size: 15))
                    .foregroundStyle(Theme.navy)
                VStack(alignment: .leading, spacing: 1) {
                    Text("Demo Bank – 1234")
                        .font(.system(size: 13, weight: .semibold))
                        .foregroundStyle(Theme.text1)
                    Text("Change Bank")
                        .font(.system(size: 11))
                        .foregroundStyle(Theme.link)
                }
                Spacer()
            }

            HStack(spacing: 8) {
                ForEach(["Share QR", "Download"], id: \.self) { label in
                    Button {
                        onConcept(label)
                    } label: {
                        Text(label)
                            .font(.system(size: 12, weight: .semibold))
                            .foregroundStyle(Theme.navy)
                            .frame(maxWidth: .infinity)
                            .frame(height: 38)
                            .background(
                                Capsule().strokeBorder(Theme.navy.opacity(0.4), lineWidth: 1)
                            )
                    }
                    .buttonStyle(.plain)
                }
            }
        }
    }

    // MARK: - Settings

    private var settingsCard: some View {
        SectionCard(padding: 0) {
            HStack {
                Text("Settings")
                    .font(.system(size: 16, weight: .bold))
                    .foregroundStyle(Theme.text1)
                Spacer()
                Button {
                    onConcept("Search settings")
                } label: {
                    Image(systemName: "magnifyingglass")
                        .font(.system(size: 15, weight: .medium))
                        .foregroundStyle(Theme.text2)
                        .frame(width: Metrics.minimumTapTarget, height: Metrics.minimumTapTarget)
                }
                .buttonStyle(.plain)
                .accessibilityLabel("Search settings")
            }
            .padding(.leading, Metrics.cardPadding)
            .padding(.trailing, 4)
            .padding(.top, 12)

            VStack(spacing: 0) {
                ForEach(SettingsRow.all) { row in
                    SettingsRowView(row: row) {
                        if row.isLanguageRow {
                            showsLanguageSheet = true
                        } else {
                            onConcept(row.title)
                        }
                    }
                    if row.id != SettingsRow.all.last?.id {
                        Divider().padding(.leading, 60)
                    }
                }
            }
            .padding(.bottom, 6)
        }
    }

    private var securityRow: some View {
        SectionCard(padding: 14) {
            HStack(spacing: 12) {
                Image(systemName: "shield.lefthalf.filled")
                    .font(.system(size: 19))
                    .foregroundStyle(Theme.success)
                VStack(alignment: .leading, spacing: 1) {
                    Text("Security Shield")
                        .font(.system(size: 14, weight: .semibold))
                        .foregroundStyle(Theme.text1)
                    Text("Protect your account")
                        .font(.system(size: 11.5))
                        .foregroundStyle(Theme.text3)
                }
                Spacer()
                Button {
                    onConcept("Security Shield")
                } label: {
                    Text("Activate")
                        .font(.system(size: 12, weight: .bold))
                        .foregroundStyle(.white)
                        .padding(.horizontal, 14)
                        .padding(.vertical, 8)
                        .background(Theme.navy, in: Capsule())
                }
                .buttonStyle(.plain)
            }
        }
    }

    // MARK: - Footer

    private var footer: some View {
        VStack(spacing: 14) {
            DevSettingsTrigger()

            VStack(spacing: 5) {
                Text("Crafted & Owned by India")
                    .font(.system(size: 11, weight: .medium))
                    .foregroundStyle(Theme.text3)
                HStack(spacing: 0) {
                    ForEach(
                        [Color(hex: 0xFF9933), Color.white, Color(hex: 0x138808)],
                        id: \.description
                    ) { stripe in
                        Rectangle().fill(stripe).frame(width: 22, height: 2)
                    }
                }
                .overlay(Rectangle().strokeBorder(Theme.hairline, lineWidth: 0.5))
            }

            HStack(spacing: 14) {
                ForEach(["Privacy Policy", "Terms"], id: \.self) { link in
                    Button {
                        onConcept(link)
                    } label: {
                        Text(link)
                            .font(.system(size: 11))
                            .foregroundStyle(Theme.link)
                    }
                    .buttonStyle(.plain)
                }
            }

            Button {
                Task { await auth.signOut() }
            } label: {
                Text("Logout")
                    .font(.system(size: 15, weight: .semibold))
                    .foregroundStyle(Theme.danger)
                    .frame(maxWidth: .infinity)
                    .frame(height: 48)
                    .background(
                        Capsule().strokeBorder(Theme.danger.opacity(0.35), lineWidth: 1)
                    )
            }
            .buttonStyle(.plain)

            Text("Concept prototype · not the live Paytm app")
                .font(.system(size: 10))
                .foregroundStyle(Theme.text3)
        }
        .padding(.top, 8)
    }

    // MARK: - Gestures

    private func dragGesture(panelWidth: CGFloat) -> some Gesture {
        DragGesture()
            .onChanged { value in
                // Leftward only: dragging right would pull the panel away from
                // its own edge, which looks broken.
                dragOffset = min(0, value.translation.width)
            }
            .onEnded { value in
                // A third of the way, or a decisive flick, counts as a close.
                let flicked = value.predictedEndTranslation.width < -panelWidth / 2
                if value.translation.width < -panelWidth / 3 || flicked {
                    close()
                } else {
                    withAnimation(.spring(response: 0.3, dampingFraction: 0.85)) {
                        dragOffset = 0
                    }
                }
            }
    }

    private func close() {
        dragOffset = 0
        onClose()
    }
}

/// One row of the §5.4 settings list.
struct SettingsRow: Identifiable, Equatable {
    let id: String
    let symbol: String
    let title: String
    let subtitle: String
    var badge: String?

    /// The one row that does something. Matched by id, not by title, so
    /// rewording the label cannot silently turn it into a concept sheet.
    var isLanguageRow: Bool { id == "set.profile" }

    static let all: [SettingsRow] = [
        SettingsRow(id: "set.pocket", symbol: "indianrupeesign.circle",
                    title: "Pocket Money", subtitle: "For your family", badge: "New"),
        SettingsRow(id: "set.upi", symbol: "arrow.left.arrow.right.circle",
                    title: "UPI & Payment Settings", subtitle: "Manage UPI and accounts"),
        SettingsRow(id: "set.auto", symbol: "clock.arrow.circlepath",
                    title: "Automatic Payments", subtitle: "Mandates and subscriptions"),
        SettingsRow(id: "set.orders", symbol: "bag",
                    title: "Orders & Bookings", subtitle: "Your purchases"),
        SettingsRow(id: "set.profile", symbol: "person.text.rectangle",
                    title: "Profile — Privacy, Notification & Language",
                    subtitle: "Change the language Spasht speaks"),
        SettingsRow(id: "set.refer", symbol: "person.2",
                    title: "Refer & Win", subtitle: "Invite and earn"),
        SettingsRow(id: "set.help", symbol: "questionmark.circle",
                    title: "Help & Support", subtitle: "We are here to help"),
        SettingsRow(id: "set.myupi", symbol: "qrcode",
                    title: "MyUPI", subtitle: "Your UPI identity"),
        SettingsRow(id: "set.appearance", symbol: "paintbrush",
                    title: "Appearance", subtitle: "Light mode only in this demo"),
    ]
}

private struct SettingsRowView: View {
    let row: SettingsRow
    let onTap: () -> Void

    var body: some View {
        Button(action: onTap) {
            HStack(spacing: 14) {
                Image(systemName: row.symbol)
                    .font(.system(size: 17, weight: .regular))
                    .foregroundStyle(Theme.iconLine)
                    .frame(width: 30)

                VStack(alignment: .leading, spacing: 2) {
                    HStack(spacing: 6) {
                        Text(row.title)
                            .font(.system(size: 13.5, weight: .semibold))
                            .foregroundStyle(Theme.text1)
                            .multilineTextAlignment(.leading)
                            .fixedSize(horizontal: false, vertical: true)
                        if let badge = row.badge {
                            BadgePill(text: badge)
                        }
                    }
                    Text(row.subtitle)
                        .font(.system(size: 11.5))
                        .foregroundStyle(Theme.text3)
                }

                Spacer(minLength: 4)

                Image(systemName: "chevron.right")
                    .font(.system(size: 11, weight: .semibold))
                    .foregroundStyle(Theme.text3)
            }
            .padding(.horizontal, Metrics.cardPadding)
            .padding(.vertical, 11)
            .frame(minHeight: Metrics.minimumTapTarget)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
    }
}
