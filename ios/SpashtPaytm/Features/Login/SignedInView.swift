import SwiftUI

/// Temporary signed-in screen (build plan phase 1, step 2).
///
/// Proves the whole chain works — Google or demo → token → `/api/me` → a real
/// row in Postgres — and shows exactly what the backend decided: the role, the
/// language, the persona and the session kind. Phase 4 replaces it with the
/// Paytm-style home screen.
struct SignedInView: View {
    let auth: AuthService
    let me: Me

    var body: some View {
        VStack(spacing: 0) {
            ConceptRibbon()

            ScrollView {
                VStack(alignment: .leading, spacing: Metrics.cardGap) {
                    profileCard
                    detailsCard
                    nextCard
                }
                .padding(.horizontal, Metrics.screenPadding)
                .padding(.vertical, 20)
            }
            .background(Theme.bg)
        }
        .refreshable { await auth.loadProfile() }
    }

    // MARK: - Pieces

    private var profileCard: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack(spacing: 12) {
                avatar

                VStack(alignment: .leading, spacing: 2) {
                    Text(me.displayLabel)
                        .font(.spashtSection)
                        .foregroundStyle(Theme.text1)
                        .lineLimit(1)

                    Text(me.email ?? "—")
                        .font(.spashtCaption)
                        .foregroundStyle(Theme.text3)
                        .lineLimit(1)
                }

                Spacer(minLength: 0)
            }

            // Wrapping chips: Dynamic Type can make these much wider.
            FlowRow(spacing: 8) {
                Chip(label: "Role", value: me.isAdmin ? "admin" : "customer")
                Chip(label: "Language", value: me.preferredLanguage.nativeName)
                Chip(label: "Persona", value: me.persona?.id ?? "none")
                // Driven by the server's answer, so it cannot claim a demo
                // session while acting as the real user.
                if me.isDemoSession {
                    Chip(label: "Session", value: "demo", highlighted: true)
                }
            }

            Button {
                Task { await auth.signOut() }
            } label: {
                Label("Logout", systemImage: "rectangle.portrait.and.arrow.right")
                    .font(.spashtChip.weight(.semibold))
                    .foregroundStyle(Theme.text2)
                    .padding(.horizontal, 14)
                    .frame(height: Metrics.minimumTapTarget)
                    .overlay(Capsule().strokeBorder(Theme.hairline, lineWidth: 1))
            }
        }
        .spashtCard()
    }

    private var avatar: some View {
        Group {
            if let photo = me.photoUrl, let url = URL(string: photo) {
                AsyncImage(url: url) { image in
                    image.resizable().scaledToFill()
                } placeholder: {
                    initialsCircle
                }
            } else {
                initialsCircle
            }
        }
        .frame(width: Metrics.avatar, height: Metrics.avatar)
        .clipShape(Circle())
    }

    private var initialsCircle: some View {
        ZStack {
            Theme.avatarBackground
            Text(me.initials)
                .font(.spashtBodyBold)
                .foregroundStyle(Theme.text1)
        }
    }

    private var detailsCard: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("Language")
                .font(.spashtBodyBold)
                .foregroundStyle(Theme.text1)

            Text("Saved to your profile with PATCH /api/me.")
                .font(.spashtCaption)
                .foregroundStyle(Theme.text3)

            // The full language sheet arrives in phase 4; this is the same call.
            HStack(spacing: 8) {
                ForEach(Language.allCases, id: \.self) { language in
                    let selected = language == me.preferredLanguage
                    Button {
                        Task { await auth.setLanguage(language) }
                    } label: {
                        Text(language.nativeName)
                            .font(.spashtChip.weight(selected ? .bold : .regular))
                            .foregroundStyle(selected ? .white : Theme.text2)
                            .padding(.horizontal, 14)
                            .frame(minHeight: Metrics.minimumTapTarget)
                            .background(selected ? Theme.navy : Theme.bg, in: Capsule())
                    }
                }
            }
        }
        .spashtCard()
    }

    private var nextCard: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("Phase 1 scaffold")
                .font(.spashtBodyBold)
                .foregroundStyle(Theme.text1)

            Text(
                "The Paytm-style home screen arrives in phase 4 and the Spasht journey in phase 5. "
                    + "This screen exists to prove sign-in works end to end."
            )
            .font(.spashtCaption)
            .foregroundStyle(Theme.text3)

            if let message = auth.errorMessage {
                Text(message)
                    .font(.spashtCaption)
                    .foregroundStyle(Theme.danger)
                    .padding(.top, 4)
            }
        }
        .spashtCard()
    }
}

// MARK: - Small components

private struct Chip: View {
    let label: String
    let value: String
    var highlighted: Bool = false

    var body: some View {
        HStack(spacing: 4) {
            Text(label + ":")
                .foregroundStyle(Theme.text3)
            Text(value)
                .foregroundStyle(Theme.text1)
                .fontWeight(highlighted ? .bold : .regular)
        }
        .font(.system(size: 12))
        .padding(.horizontal, 10)
        .padding(.vertical, 6)
        .background(highlighted ? Theme.badgeNew : Theme.bg, in: Capsule())
    }
}

/// A wrapping horizontal stack.
///
/// `HStack` would push the chips off-screen at larger Dynamic Type sizes, and
/// the journey has to stay usable for someone who has enlarged their text.
private struct FlowRow: Layout {
    var spacing: CGFloat = 8

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        let maxWidth = proposal.width ?? .infinity
        var rowWidth: CGFloat = 0
        var rowHeight: CGFloat = 0
        var totalHeight: CGFloat = 0

        for subview in subviews {
            let size = subview.sizeThatFits(.unspecified)
            if rowWidth > 0, rowWidth + spacing + size.width > maxWidth {
                totalHeight += rowHeight + spacing
                rowWidth = size.width
                rowHeight = size.height
            } else {
                rowWidth += (rowWidth > 0 ? spacing : 0) + size.width
                rowHeight = max(rowHeight, size.height)
            }
        }
        return CGSize(width: maxWidth, height: totalHeight + rowHeight)
    }

    func placeSubviews(
        in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()
    ) {
        var x = bounds.minX
        var y = bounds.minY
        var rowHeight: CGFloat = 0

        for subview in subviews {
            let size = subview.sizeThatFits(.unspecified)
            if x > bounds.minX, x + size.width > bounds.maxX {
                x = bounds.minX
                y += rowHeight + spacing
                rowHeight = 0
            }
            subview.place(at: CGPoint(x: x, y: y), proposal: ProposedViewSize(size))
            x += size.width + spacing
            rowHeight = max(rowHeight, size.height)
        }
    }
}
