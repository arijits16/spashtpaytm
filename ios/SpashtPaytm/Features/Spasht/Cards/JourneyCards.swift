import SwiftUI

/// Every card the journey can render (build plan §5.6, §8.4).
///
/// One view per card type, all driven entirely by the server's payload. None of
/// them computes anything: an EMI shown here was calculated in
/// `journey/loan_math.py`, and the badge beside it was decided in
/// `journey/offers.py`.

/// Routes a decoded `Card` to its view.
struct CardView: View {
    let card: Card
    let language: Language
    let acceptEnabled: Bool
    let isSending: Bool
    let onAction: (JourneyAction) -> Void
    let onOpenPdf: (String) -> Void

    var body: some View {
        switch card {
        case .language(let data):
            LanguageCardView(data: data, onAction: onAction)
        case .amount(let data):
            AmountCardView(data: data, onAction: onAction)
        case .consent(let data):
            ConsentCardView(data: data, language: language, onAction: onAction)
        case .manualForm(let data):
            ManualFormCardView(data: data, language: language, onAction: onAction)
        case .prefill(let data):
            PrefillCardView(data: data)
        case .confirm(let data):
            ConfirmCardView(data: data, language: language, onAction: onAction)
        case .offers(let data):
            OffersCardView(data: data, language: language, onAction: onAction, onOpenPdf: onOpenPdf)
        case .kfs(let data):
            KfsCardView(data: data, language: language, onOpenPdf: onOpenPdf)
        case .quiz(let data):
            QuizCardView(data: data, isSending: isSending, onAction: onAction)
        case .consentLock(let data):
            ConsentLockCardView(
                data: data, language: language, acceptEnabled: acceptEnabled, onAction: onAction
            )
        case .otp:
            // Presented as a sheet by `JourneyView`, not inline: the OTP needs
            // the keyboard and a focused field, which a card in a scroll view
            // handles badly.
            EmptyView()
        case .receipt(let data):
            ReceiptCardView(data: data)
        case .handoff(let data):
            HandoffCardView(data: data)
        case .unsupported(let type):
            UnsupportedCardView(type: type)
        }
    }
}

// MARK: - Shared chrome

/// The white card every journey card sits in.
struct JourneyCard<Content: View>: View {
    @ViewBuilder var content: Content

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            content
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Theme.card, in: Metrics.cardShape)
        .overlay(Metrics.cardShape.strokeBorder(Theme.hairline, lineWidth: 1))
    }
}

/// A navy primary button, the journey's main affordance.
struct PrimaryButton: View {
    let title: String
    var enabled = true
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            Text(title)
                .font(.system(size: 16, weight: .bold))
                .foregroundStyle(.white)
                .frame(maxWidth: .infinity)
                .frame(height: 50)
                .background(enabled ? Theme.navy : Theme.text3.opacity(0.4), in: Capsule())
        }
        .buttonStyle(.plain)
        .disabled(!enabled)
    }
}

// MARK: - Language

struct LanguageCardView: View {
    let data: LanguageCard
    let onAction: (JourneyAction) -> Void

    var body: some View {
        JourneyCard {
            ForEach(data.options) { option in
                Button {
                    onAction(.setLanguage(option.language))
                } label: {
                    HStack {
                        Text(option.label)
                            .font(.system(size: 17, weight: .semibold))
                            .foregroundStyle(Theme.text1)
                        Spacer()
                        Image(systemName: "chevron.right")
                            .font(.system(size: 12, weight: .semibold))
                            .foregroundStyle(Theme.text3)
                    }
                    .padding(.horizontal, 14)
                    .frame(height: 52)
                    .background(Theme.bg, in: Metrics.cardShape)
                }
                .buttonStyle(.plain)
            }
        }
    }
}

// MARK: - Amount

struct AmountCardView: View {
    let data: AmountCard
    let onAction: (JourneyAction) -> Void

    var body: some View {
        JourneyCard {
            HStack(spacing: 8) {
                ForEach(data.chips, id: \.self) { amount in
                    Button {
                        onAction(.amount(amount))
                    } label: {
                        Text("₹\(Format.rupees(amount))")
                            .font(.system(size: 15, weight: .bold))
                            .foregroundStyle(Theme.navy)
                            .frame(maxWidth: .infinity)
                            .frame(height: 48)
                            .background(Theme.offerStrip.opacity(0.6), in: Capsule())
                            .overlay(Capsule().strokeBorder(Theme.navy.opacity(0.3), lineWidth: 1))
                    }
                    .buttonStyle(.plain)
                }
            }

            Text("₹\(Format.rupees(data.min)) – ₹\(Format.rupees(data.max))")
                .font(.system(size: 11))
                .foregroundStyle(Theme.text3)
        }
    }
}

// MARK: - Consent

struct ConsentCardView: View {
    let data: ConsentCard
    let language: Language
    let onAction: (JourneyAction) -> Void

    /// Local state, initialised **off** for every purpose. The server also
    /// sends `granted: false`, so there are two independent reasons a consent
    /// cannot arrive pre-ticked (§5.6).
    @State private var grants: [String: Bool] = [:]

    var body: some View {
        JourneyCard {
            ForEach(data.purposes) { purpose in
                Toggle(isOn: binding(for: purpose.id)) {
                    VStack(alignment: .leading, spacing: 2) {
                        Text(purpose.title)
                            .font(.system(size: 14, weight: .semibold))
                            .foregroundStyle(Theme.text1)
                        Text(purpose.detail)
                            .font(.system(size: 12))
                            .foregroundStyle(Theme.text3)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                }
                .tint(Theme.navy)
            }

            Text(data.why)
                .font(.system(size: 11.5))
                .foregroundStyle(Theme.text3)
                .fixedSize(horizontal: false, vertical: true)

            PrimaryButton(title: Strings.allow(language)) {
                onAction(
                    .consents(
                        digilocker: grants["fetch_digilocker"] ?? false,
                        accountAggregator: grants["fetch_account_aggregator"] ?? false
                    )
                )
            }

            // "Not now" leads to the manual form, never to a dead end (§9).
            Button {
                onAction(.consents(digilocker: false, accountAggregator: false))
            } label: {
                Text(Strings.notNow(language))
                    .font(.system(size: 13, weight: .medium))
                    .foregroundStyle(Theme.link)
                    .frame(maxWidth: .infinity)
                    .frame(minHeight: Metrics.minimumTapTarget)
            }
            .buttonStyle(.plain)
        }
    }

    private func binding(for id: String) -> Binding<Bool> {
        Binding(
            get: { grants[id] ?? false },
            set: { grants[id] = $0 }
        )
    }
}

// MARK: - Prefill

struct PrefillCardView: View {
    let data: PrefillCard

    /// Drives the staggered fade-in (§5.6): the rows appear one after another,
    /// which is what makes the source tags readable rather than a flash.
    @State private var shown = 0

    var body: some View {
        JourneyCard {
            ForEach(Array(data.rows.enumerated()), id: \.element.id) { index, row in
                HStack(alignment: .top, spacing: 10) {
                    Image(systemName: "checkmark.circle.fill")
                        .font(.system(size: 15))
                        .foregroundStyle(Theme.success)

                    VStack(alignment: .leading, spacing: 2) {
                        Text(row.label)
                            .font(.system(size: 11.5))
                            .foregroundStyle(Theme.text3)
                        Text(row.value)
                            .font(.system(size: 14, weight: .semibold))
                            .foregroundStyle(Theme.text1)
                            .fixedSize(horizontal: false, vertical: true)
                    }

                    Spacer(minLength: 6)

                    Text(row.source)
                        .font(.system(size: 9, weight: .bold))
                        .foregroundStyle(Theme.navy)
                        .padding(.horizontal, 7)
                        .padding(.vertical, 3)
                        .background(Theme.offerStrip, in: Capsule())
                }
                .opacity(index < shown ? 1 : 0)
                .offset(y: index < shown ? 0 : 6)
                .animation(.easeOut(duration: 0.25), value: shown)
            }
        }
        .task {
            for index in data.rows.indices {
                try? await Task.sleep(for: .milliseconds(90))
                shown = index + 1
            }
        }
    }
}

// MARK: - Confirm

struct ConfirmCardView: View {
    let data: ConfirmCard
    let language: Language
    let onAction: (JourneyAction) -> Void

    @State private var values: [String: String] = [:]
    @State private var editing = false

    var body: some View {
        JourneyCard {
            ForEach(data.fields) { field in
                VStack(alignment: .leading, spacing: 4) {
                    Text(field.label)
                        .font(.system(size: 11.5))
                        .foregroundStyle(Theme.text3)

                    if editing {
                        TextField(field.label, text: binding(for: field))
                            .font(.system(size: 14))
                            .padding(.horizontal, 12)
                            .frame(height: 44)
                            .background(Theme.bg, in: RoundedRectangle(cornerRadius: 10))
                            .keyboardType(field.id == "mobile" ? .numberPad : .default)
                    } else {
                        Text(field.value)
                            .font(.system(size: 14, weight: .semibold))
                            .foregroundStyle(Theme.text1)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                }
            }

            HStack(spacing: 10) {
                PrimaryButton(title: Strings.yes(language)) {
                    if editing {
                        onAction(
                            .confirmDetails(
                                shopAddress: changed("shopAddress"),
                                mobile: changed("mobile")
                            )
                        )
                    } else {
                        onAction(.confirmDetails(shopAddress: nil, mobile: nil))
                    }
                }

                Button {
                    // Seeded with the current values so editing one field does
                    // not blank the other.
                    for field in data.fields where values[field.id] == nil {
                        values[field.id] = field.value
                    }
                    editing = true
                } label: {
                    Text(Strings.edit(language))
                        .font(.system(size: 15, weight: .semibold))
                        .foregroundStyle(Theme.navy)
                        .frame(width: 92, height: 50)
                        .background(Capsule().strokeBorder(Theme.navy.opacity(0.4), lineWidth: 1))
                }
                .buttonStyle(.plain)
                .opacity(editing ? 0.4 : 1)
                .disabled(editing)
            }
        }
    }

    private func binding(for field: ConfirmCard.Field) -> Binding<String> {
        Binding(
            get: { values[field.id] ?? field.value },
            set: { values[field.id] = $0 }
        )
    }

    /// Only send a field that actually changed, so an untouched value is not
    /// re-validated and rejected for a format the server itself produced.
    private func changed(_ id: String) -> String? {
        guard let edited = values[id],
            let original = data.fields.first(where: { $0.id == id })?.value,
            edited != original
        else { return nil }
        return edited
    }
}

// MARK: - Unsupported

struct UnsupportedCardView: View {
    let type: String

    var body: some View {
        JourneyCard {
            HStack(spacing: 10) {
                Image(systemName: "arrow.down.circle")
                    .font(.system(size: 18))
                    .foregroundStyle(Theme.warning)
                VStack(alignment: .leading, spacing: 2) {
                    Text("Please update the app")
                        .font(.system(size: 14, weight: .semibold))
                        .foregroundStyle(Theme.text1)
                    Text("This step needs a newer version (card: \(type)).")
                        .font(.system(size: 12))
                        .foregroundStyle(Theme.text3)
                }
            }
        }
    }
}

// MARK: - Localised button labels

/// The handful of button words the app supplies itself.
///
/// Everything the *assistant* says comes from the backend's templates (§7.4).
/// These are chrome - "Allow", "Edit" - that belongs to the client, and they
/// are still localised because a Marathi journey with an English button is
/// exactly the failure this product is about.
enum Strings {
    static func yes(_ language: Language) -> String {
        switch language {
        case .marathi: return "हो"
        case .hindi: return "हाँ"
        case .english: return "Yes"
        }
    }

    static func allow(_ language: Language) -> String {
        switch language {
        case .marathi: return "परवानगी देते"
        case .hindi: return "अनुमति देती हूँ"
        case .english: return "Allow"
        }
    }

    static func notNow(_ language: Language) -> String {
        switch language {
        case .marathi: return "आता नको — मी स्वतः भरते"
        case .hindi: return "अभी नहीं — मैं खुद भर दूँगी"
        case .english: return "Not now — I'll fill it myself"
        }
    }

    static func edit(_ language: Language) -> String {
        switch language {
        case .marathi: return "बदला"
        case .hindi: return "बदलें"
        case .english: return "Edit"
        }
    }

    static func agree(_ language: Language) -> String {
        switch language {
        case .marathi: return "मी सहमत आहे"
        case .hindi: return "मैं सहमत हूँ"
        case .english: return "I agree"
        }
    }

    static func submit(_ language: Language) -> String {
        switch language {
        case .marathi: return "पाठवा"
        case .hindi: return "भेजें"
        case .english: return "Submit"
        }
    }

    static func viewKfs(_ language: Language) -> String {
        switch language {
        case .marathi: return "KFS बघा"
        case .hindi: return "KFS देखें"
        case .english: return "View KFS"
        }
    }

    static func selectOffer(_ language: Language) -> String {
        switch language {
        case .marathi: return "हे निवडा"
        case .hindi: return "यह चुनें"
        case .english: return "Choose this"
        }
    }

    static func backToPaytm(_ language: Language) -> String {
        switch language {
        case .marathi: return "Paytm वर परत"
        case .hindi: return "Paytm पर वापस"
        case .english: return "Back to Paytm"
        }
    }
}

/// Number formatting for display. Indian digit grouping.
enum Format {
    /// `55200` -> `55,200`. Matches the backend's `format_rupees`, so the app
    /// and the receipt read identically.
    static func rupees(_ value: Int) -> String {
        let formatter = NumberFormatter()
        formatter.numberStyle = .decimal
        formatter.locale = Locale(identifier: "en_IN")
        formatter.groupingSeparator = ","
        return formatter.string(from: NSNumber(value: value)) ?? "\(value)"
    }

    /// `18.67` -> `18.67%`.
    static func percent(_ value: Double) -> String {
        String(format: "%.2f%%", value)
    }
}
