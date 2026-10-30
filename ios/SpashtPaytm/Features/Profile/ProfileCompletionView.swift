import SwiftUI

/// The profile-completion page (build plan §5.4).
///
/// Four coloured cards, each at 0%, and a data-sharing checkbox that starts
/// **unticked**. The checkbox is the reason this screen is worth building: a
/// pre-ticked consent box is how real apps collect permission nobody gave, and
/// showing it off by default is the clearest possible statement of what this
/// product is arguing for.
struct ProfileCompletionView: View {
    let me: Me

    @Environment(\.dismiss) private var dismiss
    @State private var sharesData = false
    @State private var showsConcept = false

    private struct Card: Identifiable {
        let id: String
        let title: String
        let minutes: Int
        let colour: Color
        let symbol: String
    }

    private var cards: [Card] {
        [
            Card(id: "personal", title: "Personal info", minutes: 2,
                 colour: Theme.profileTiles[0], symbol: "person.fill"),
            Card(id: "financial", title: "Financial preferences", minutes: 3,
                 colour: Theme.profileTiles[1], symbol: "chart.pie.fill"),
            Card(id: "lifestyle", title: "Lifestyle preferences", minutes: 2,
                 colour: Theme.profileTiles[2], symbol: "heart.fill"),
            Card(id: "other", title: "Other preferences", minutes: 1,
                 colour: Theme.profileTiles[3], symbol: "slider.horizontal.3"),
        ]
    }

    var body: some View {
        ZStack {
            Theme.bg.ignoresSafeArea()

            ScrollView {
                VStack(spacing: 18) {
                    VStack(spacing: 10) {
                        Avatar(
                            initials: me.initials,
                            photoURL: me.photoUrl.flatMap(URL.init(string:)),
                            size: 72
                        )
                        Text(me.displayLabel)
                            .font(.system(size: 17, weight: .bold))
                            .foregroundStyle(Theme.text1)
                    }
                    .padding(.top, 8)

                    progressBar

                    LazyVGrid(
                        columns: [GridItem(spacing: 12), GridItem(spacing: 12)],
                        spacing: 12
                    ) {
                        ForEach(cards) { card in
                            cardView(card)
                        }
                    }

                    dataSharingBox

                    Spacer(minLength: 20)
                }
                .padding(.horizontal, Metrics.screenPadding)
            }
        }
        .navigationTitle("Complete your profile")
        .navigationBarTitleDisplayMode(.inline)
        .sheet(isPresented: $showsConcept) {
            ConceptSheet(subject: "Profile completion") { showsConcept = false }
        }
    }

    private var progressBar: some View {
        VStack(spacing: 7) {
            HStack {
                Text("Profile completion")
                    .font(.system(size: 12, weight: .medium))
                    .foregroundStyle(Theme.text2)
                Spacer()
                Text("0%")
                    .font(.system(size: 12, weight: .bold))
                    .foregroundStyle(Theme.text1)
            }
            // Zero progress, honestly: nothing here is filled in, and a
            // fake-progress bar to encourage completion is the pattern this
            // product exists to argue against.
            GeometryReader { geometry in
                ZStack(alignment: .leading) {
                    Capsule().fill(Theme.hairline)
                    Capsule().fill(Theme.navy).frame(width: geometry.size.width * 0)
                }
            }
            .frame(height: 7)
        }
        .padding(14)
        .background(Theme.card, in: Metrics.cardShape)
    }

    private func cardView(_ card: Card) -> some View {
        Button {
            showsConcept = true
        } label: {
            VStack(alignment: .leading, spacing: 10) {
                HStack {
                    Image(systemName: card.symbol)
                        .font(.system(size: 17))
                        .foregroundStyle(.white)
                    Spacer()
                    ZeroRing()
                }
                Spacer(minLength: 8)
                Text(card.title)
                    .font(.system(size: 14, weight: .bold))
                    .foregroundStyle(.white)
                    .multilineTextAlignment(.leading)
                    .fixedSize(horizontal: false, vertical: true)
                Text("about \(card.minutes) min")
                    .font(.system(size: 11))
                    .foregroundStyle(.white.opacity(0.8))
            }
            .padding(14)
            .frame(height: 142, alignment: .topLeading)
            .frame(maxWidth: .infinity)
            .background(card.colour, in: Metrics.cardShape)
        }
        .buttonStyle(.plain)
    }

    private var dataSharingBox: some View {
        Button {
            sharesData.toggle()
        } label: {
            HStack(alignment: .top, spacing: 12) {
                Image(systemName: sharesData ? "checkmark.square.fill" : "square")
                    .font(.system(size: 20))
                    .foregroundStyle(sharesData ? Theme.navy : Theme.text3)

                Text("I agree to share my profile information with Paytm's partners for personalised offers.")
                    .font(.system(size: 12.5))
                    .foregroundStyle(Theme.text2)
                    .multilineTextAlignment(.leading)
                    .fixedSize(horizontal: false, vertical: true)
            }
            .padding(14)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(Theme.card, in: Metrics.cardShape)
        }
        .buttonStyle(.plain)
        .accessibilityAddTraits(sharesData ? [.isButton, .isSelected] : .isButton)
    }
}

/// The 0% ring on each card.
private struct ZeroRing: View {
    var body: some View {
        ZStack {
            Circle().strokeBorder(.white.opacity(0.35), lineWidth: 2.5)
            Text("0%")
                .font(.system(size: 8, weight: .heavy))
                .foregroundStyle(.white)
        }
        .frame(width: 30, height: 30)
    }
}
