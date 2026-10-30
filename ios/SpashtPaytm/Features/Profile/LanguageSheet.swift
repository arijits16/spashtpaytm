import SwiftUI

/// Choosing the language Spasht speaks (build plan §5.4).
///
/// The one functional setting in the drawer. It saves through `PATCH /api/me`,
/// so the choice survives a reinstall and the journey starts in the right
/// language without being asked again.
///
/// Each language is named **in that language** - मराठी, not "Marathi". Someone
/// who reads only Marathi cannot be expected to find their language in a list
/// written in English, and this is a product about not excluding that person.
struct LanguageSheet: View {
    let auth: AuthService
    let current: Language

    @Environment(\.dismiss) private var dismiss
    @State private var selected: Language
    @State private var saving = false
    @State private var error: String?

    init(auth: AuthService, current: Language) {
        self.auth = auth
        self.current = current
        _selected = State(initialValue: current)
    }

    var body: some View {
        VStack(spacing: 0) {
            Capsule()
                .fill(Theme.hairline)
                .frame(width: 38, height: 4)
                .padding(.top, 10)

            Text("Language")
                .font(.system(size: 19, weight: .bold))
                .foregroundStyle(Theme.text1)
                .padding(.top, 18)

            Text("Spasht will speak and write in this language")
                .font(.system(size: 13))
                .foregroundStyle(Theme.text3)
                .padding(.top, 3)

            VStack(spacing: 10) {
                ForEach(Language.allCases, id: \.self) { language in
                    LanguageRow(
                        language: language,
                        isSelected: language == selected,
                        onTap: { selected = language }
                    )
                }
            }
            .padding(.horizontal, 20)
            .padding(.top, 22)

            if let error {
                Text(error)
                    .font(.system(size: 12))
                    .foregroundStyle(Theme.danger)
                    .multilineTextAlignment(.center)
                    .padding(.horizontal, 24)
                    .padding(.top, 12)
            }

            Button(action: save) {
                ZStack {
                    if saving {
                        ProgressView().tint(.white)
                    } else {
                        Text("Save")
                            .font(.system(size: 16, weight: .bold))
                    }
                }
                .foregroundStyle(.white)
                .frame(maxWidth: .infinity)
                .frame(height: 52)
                .background(Theme.navy, in: Capsule())
            }
            .buttonStyle(.plain)
            .disabled(saving)
            .padding(.horizontal, 20)
            .padding(.top, 20)

            Spacer(minLength: 0)
        }
        .frame(maxWidth: .infinity)
        .background(Theme.card)
        .presentationDetents([.height(430)])
    }

    private func save() {
        guard selected != current else {
            dismiss()
            return
        }
        saving = true
        error = nil

        Task {
            do {
                try await auth.updateLanguage(selected)
                dismiss()
            } catch {
                // Kept on screen rather than dismissed: silently failing to
                // save a language in a language-first product is the worst
                // possible outcome.
                self.error = "Could not save. Please check the connection and try again."
            }
            saving = false
        }
    }
}

private struct LanguageRow: View {
    let language: Language
    let isSelected: Bool
    let onTap: () -> Void

    var body: some View {
        Button(action: onTap) {
            HStack(spacing: 14) {
                Text(language.nativeName)
                    .font(.system(size: 17, weight: .semibold))
                    .foregroundStyle(Theme.text1)

                Text(language.englishName)
                    .font(.system(size: 12))
                    .foregroundStyle(Theme.text3)

                Spacer()

                Image(systemName: isSelected ? "checkmark.circle.fill" : "circle")
                    .font(.system(size: 20))
                    .foregroundStyle(isSelected ? Theme.navy : Theme.hairline)
            }
            .padding(.horizontal, 16)
            .frame(height: 58)
            .background(
                Metrics.cardShape
                    .fill(isSelected ? Theme.offerStrip.opacity(0.55) : Theme.bg)
            )
            .overlay(
                Metrics.cardShape.strokeBorder(
                    isSelected ? Theme.navy : .clear,
                    lineWidth: 1.5
                )
            )
        }
        .buttonStyle(.plain)
    }
}

extension Language {
    /// The English name, shown small beside the native one so a mixed-language
    /// team can also navigate the sheet.
    var englishName: String {
        switch self {
        case .marathi: return "Marathi"
        case .hindi: return "Hindi"
        case .english: return "English"
        }
    }
}
