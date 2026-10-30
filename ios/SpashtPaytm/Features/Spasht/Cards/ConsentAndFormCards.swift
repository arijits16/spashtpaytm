import SwiftUI

/// The consent lock, manual form, handoff and receipt cards (build plan §5.6, §5.7).

// MARK: - Consent lock

/// The agreement screen (§5.6 "Consent lock").
///
/// Two separate decisions, deliberately not one: the loan terms, and the
/// optional insurance. Bundling them is the practice this product exists to
/// argue against, so the insurance toggle sits apart, starts at **No**, and
/// says it is optional in its own label.
///
/// The agree button is disabled until the backend says `acceptEnabled`. That is
/// a courtesy, not the control - the backend re-checks it when the tap arrives
/// (§9), so a patched client gains nothing.
struct ConsentLockCardView: View {
    let data: ConsentLockCard
    let language: Language
    let acceptEnabled: Bool
    let onAction: (JourneyAction) -> Void

    @State private var insuranceOn: Bool

    init(
        data: ConsentLockCard,
        language: Language,
        acceptEnabled: Bool,
        onAction: @escaping (JourneyAction) -> Void
    ) {
        self.data = data
        self.language = language
        self.acceptEnabled = acceptEnabled
        self.onAction = onAction
        // Seeded from the server, which always says false until the customer
        // turns it on themselves.
        _insuranceOn = State(initialValue: data.insurance.granted)
    }

    var body: some View {
        JourneyCard {
            HStack(spacing: 8) {
                Image(systemName: acceptEnabled ? "lock.open.fill" : "lock.fill")
                    .font(.system(size: 15))
                    .foregroundStyle(acceptEnabled ? Theme.success : Theme.text3)
                Text(acceptEnabled ? unlockedTitle : lockedTitle)
                    .font(.system(size: 14, weight: .bold))
                    .foregroundStyle(Theme.text1)
            }

            // Each line states exactly one thing being agreed to (§5.6).
            VStack(alignment: .leading, spacing: 8) {
                ForEach(data.terms, id: \.self) { term in
                    HStack(alignment: .top, spacing: 8) {
                        Image(systemName: "checkmark")
                            .font(.system(size: 10, weight: .bold))
                            .foregroundStyle(Theme.navy)
                            .padding(.top, 3)
                        Text(term)
                            .font(.system(size: 13))
                            .foregroundStyle(Theme.text2)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                }
            }

            Divider()

            insuranceSection

            if let reason = data.reason, !acceptEnabled {
                Text(reason)
                    .font(.system(size: 12))
                    .foregroundStyle(Theme.warning)
                    .fixedSize(horizontal: false, vertical: true)
            }

            PrimaryButton(title: Strings.agree(language), enabled: acceptEnabled) {
                onAction(.acceptTerms)
            }
            // §5.6: an impact haptic when the lock opens.
            .sensoryFeedback(.impact(weight: .medium), trigger: acceptEnabled)
        }
    }

    private var insuranceSection: some View {
        VStack(alignment: .leading, spacing: 6) {
            Toggle(isOn: Binding(
                get: { insuranceOn },
                set: { newValue in
                    insuranceOn = newValue
                    onAction(.insuranceAddon(newValue))
                }
            )) {
                VStack(alignment: .leading, spacing: 2) {
                    HStack(spacing: 6) {
                        Text(insuranceTitle)
                            .font(.system(size: 13.5, weight: .semibold))
                            .foregroundStyle(Theme.text1)
                        Text(optionalTag)
                            .font(.system(size: 9, weight: .heavy))
                            .foregroundStyle(Theme.success)
                            .padding(.horizontal, 5)
                            .padding(.vertical, 2)
                            .background(Theme.success.opacity(0.12), in: Capsule())
                    }
                    Text(insuranceDetail)
                        .font(.system(size: 11.5))
                        .foregroundStyle(Theme.text3)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
            .tint(Theme.navy)
        }
    }

    private var lockedTitle: String {
        switch language {
        case .marathi: return "आधी प्रश्न पूर्ण करा"
        case .hindi: return "पहले सवाल पूरे करें"
        case .english: return "Finish the questions first"
        }
    }

    private var unlockedTitle: String {
        switch language {
        case .marathi: return "तुम्ही सहमती देऊ शकता"
        case .hindi: return "आप सहमति दे सकते हैं"
        case .english: return "You can now agree"
        }
    }

    private var insuranceTitle: String {
        switch language {
        case .marathi: return "कर्ज विमा"
        case .hindi: return "लोन बीमा"
        case .english: return "Credit-life insurance"
        }
    }

    private var optionalTag: String {
        switch language {
        case .marathi: return "ऐच्छिक"
        case .hindi: return "वैकल्पिक"
        case .english: return "OPTIONAL"
        }
    }

    private var insuranceDetail: String {
        let premium = "₹\(Format.rupees(data.insurance.premium))"
        switch language {
        case .marathi:
            return "एक वेळचा हप्ता \(premium). न घेताही कर्ज मंजूर होईल."
        case .hindi:
            return "एक बार का प्रीमियम \(premium)। न लेने पर भी लोन मंज़ूर होगा।"
        case .english:
            return "A one-time premium of \(premium). Your loan is approved either way."
        }
    }
}

// MARK: - Manual form

struct ManualFormCardView: View {
    let data: ManualFormCard
    let language: Language
    let onAction: (JourneyAction) -> Void

    @State private var values: [String: String] = [:]

    var body: some View {
        JourneyCard {
            ForEach(data.fields) { field in
                VStack(alignment: .leading, spacing: 4) {
                    Text(field.label)
                        .font(.system(size: 11.5))
                        .foregroundStyle(Theme.text3)

                    TextField(field.label, text: binding(for: field.id))
                        .font(.system(size: 14))
                        .padding(.horizontal, 12)
                        .frame(height: 46)
                        .background(Theme.bg, in: RoundedRectangle(cornerRadius: 10))
                        .keyboardType(keyboard(for: field.kind))
                        .textInputAutocapitalization(field.kind == "text" ? .words : .never)
                        .autocorrectionDisabled(field.kind != "text")
                }
            }

            Text(hint)
                .font(.system(size: 11))
                .foregroundStyle(Theme.text3)
                .fixedSize(horizontal: false, vertical: true)

            PrimaryButton(title: Strings.submit(language), enabled: isComplete) {
                onAction(
                    .manualForm(
                        ManualFormValues(
                            fullName: values["fullName"] ?? "",
                            dob: values["dob"] ?? "",
                            monthlyIncome: Int(values["monthlyIncome"] ?? "") ?? 0,
                            shopAddress: values["shopAddress"] ?? "",
                            mobile: values["mobile"] ?? ""
                        )
                    )
                )
            }
        }
    }

    /// Enabled only when every required field has something in it. The server
    /// validates properly; this just avoids a guaranteed 422.
    private var isComplete: Bool {
        data.fields.filter(\.required).allSatisfy { field in
            !(values[field.id] ?? "").trimmingCharacters(in: .whitespaces).isEmpty
        }
    }

    private var hint: String {
        switch language {
        case .marathi: return "जन्मतारीख YYYY-MM-DD, मोबाईल १० अंकी."
        case .hindi: return "जन्म तारीख YYYY-MM-DD, मोबाइल 10 अंकों का।"
        case .english: return "Date of birth as YYYY-MM-DD, mobile as 10 digits."
        }
    }

    private func binding(for id: String) -> Binding<String> {
        Binding(
            get: { values[id] ?? "" },
            set: { values[id] = $0 }
        )
    }

    private func keyboard(for kind: String) -> UIKeyboardType {
        switch kind {
        case "number": return .numberPad
        case "phone": return .numberPad
        case "date": return .numbersAndPunctuation
        default: return .default
        }
    }
}

// MARK: - Handoff

struct HandoffCardView: View {
    let data: HandoffCard

    var body: some View {
        JourneyCard {
            HStack(spacing: 10) {
                Image(systemName: "phone.badge.waveform.fill")
                    .font(.system(size: 20))
                    .foregroundStyle(Theme.navy)
                    .frame(width: 46, height: 46)
                    .background(Theme.offerStrip, in: Circle())

                VStack(alignment: .leading, spacing: 3) {
                    Text(data.message)
                        .font(.system(size: 14, weight: .semibold))
                        .foregroundStyle(Theme.text1)
                        .fixedSize(horizontal: false, vertical: true)
                    Text(data.window)
                        .font(.system(size: 11.5))
                        .foregroundStyle(Theme.text3)
                }
            }
        }
    }
}
