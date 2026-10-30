import SwiftUI

/// The language choice before the journey starts (build plan §5.6).
///
/// Asked here rather than as the first conversational turn, because the first
/// thing a language-first product should do is let you pick your language - not
/// greet you in one you may not read. The journey then starts with `language`
/// already set and the engine skips its own language card.
struct SpashtIntroView: View {
    let auth: AuthService
    let me: Me

    @State private var selected: Language
    @State private var startsJourney = false

    init(auth: AuthService, me: Me) {
        self.auth = auth
        self.me = me
        // Defaults to the saved preference, so a returning customer taps once.
        _selected = State(initialValue: me.preferredLanguage)
    }

    var body: some View {
        ZStack {
            Theme.loginGradient.ignoresSafeArea()

            VStack(spacing: 0) {
                ScrollView {
                    VStack(spacing: 22) {
                        header

                        VStack(spacing: 11) {
                            ForEach(Language.allCases, id: \.self) { language in
                                LanguageCardButton(
                                    language: language,
                                    isSelected: language == selected,
                                    onTap: { selected = language }
                                )
                            }
                        }

                        promise

                        Spacer(minLength: 10)
                    }
                    .padding(.horizontal, 22)
                    .padding(.top, 18)
                }

                PrimaryButton(title: startLabel) {
                    startsJourney = true
                }
                .padding(.horizontal, 22)
                .padding(.bottom, 10)

                Text("Concept demo · synthetic data only")
                    .font(.system(size: 10))
                    .foregroundStyle(Theme.text3)
                    .padding(.bottom, 8)
            }
        }
        .navigationTitle("Spasht")
        .navigationBarTitleDisplayMode(.inline)
        .navigationDestination(isPresented: $startsJourney) {
            JourneyView(auth: auth, language: selected)
        }
    }

    private var header: some View {
        VStack(spacing: 10) {
            ZStack {
                Circle()
                    .fill(Theme.navy)
                    .frame(width: 64, height: 64)
                Image(systemName: "waveform")
                    .font(.system(size: 26, weight: .medium))
                    .foregroundStyle(.white)
            }

            Text("Spasht")
                .font(.system(size: 27, weight: .heavy))
                .foregroundStyle(Theme.navy)

            Text("Loans you actually understand")
                .font(.system(size: 14, weight: .medium))
                .foregroundStyle(Theme.text2)

            Text("Choose your language")
                .font(.system(size: 12, weight: .semibold))
                .foregroundStyle(Theme.text3)
                .padding(.top, 6)
        }
    }

    /// The one-line promise (§5.6). It is a promise the product keeps: the
    /// journey is short, it is in their language, and the consent lock means
    /// control genuinely stays with them.
    private var promise: some View {
        HStack(spacing: 14) {
            ForEach(
                [
                    ("clock", "2 minutes"),
                    ("character.bubble", "your language"),
                    ("hand.raised", "you stay in control"),
                ],
                id: \.0
            ) { symbol, label in
                VStack(spacing: 5) {
                    Image(systemName: symbol)
                        .font(.system(size: 15))
                        .foregroundStyle(Theme.navy)
                    Text(label)
                        .font(.system(size: 10, weight: .medium))
                        .foregroundStyle(Theme.text2)
                        .multilineTextAlignment(.center)
                        .fixedSize(horizontal: false, vertical: true)
                }
                .frame(maxWidth: .infinity)
            }
        }
        .padding(.vertical, 14)
        .padding(.horizontal, 10)
        .background(.white.opacity(0.7), in: Metrics.cardShape)
    }

    private var startLabel: String {
        switch selected {
        case .marathi: return "सुरू करा"
        case .hindi: return "शुरू करें"
        case .english: return "Start"
        }
    }
}

private struct LanguageCardButton: View {
    let language: Language
    let isSelected: Bool
    let onTap: () -> Void

    var body: some View {
        Button(action: onTap) {
            HStack(spacing: 14) {
                Text(language.nativeName)
                    .font(.system(size: 20, weight: .bold))
                    .foregroundStyle(Theme.text1)
                Spacer()
                Image(systemName: isSelected ? "checkmark.circle.fill" : "circle")
                    .font(.system(size: 22))
                    .foregroundStyle(isSelected ? Theme.navy : Theme.hairline)
            }
            .padding(.horizontal, 18)
            .frame(height: 66)
            .background(.white, in: Metrics.cardShape)
            .overlay(
                Metrics.cardShape.strokeBorder(
                    isSelected ? Theme.navy : Theme.hairline,
                    lineWidth: isSelected ? 2 : 1
                )
            )
        }
        .buttonStyle(.plain)
    }
}
