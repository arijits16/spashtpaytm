import SwiftUI

/// The OTP sheet (build plan §5.6, §13.6).
///
/// Six boxes over **one hidden field**, which is the only way to get iOS's
/// `oneTimeCode` autofill - six separate `TextField`s look right and then
/// nothing autofills, which is worse.
///
/// **Typed only.** There is no voice path to this screen on purpose: the
/// assistant's own OTP line tells the customer never to say a code aloud, and a
/// product that then offered to listen for one would be teaching the habit that
/// gets people robbed.
struct OtpSheet: View {
    let language: Language
    let card: OtpCard
    let demoCode: String?
    let isVerifying: Bool
    let onVerify: (String) -> Void
    let onResend: () -> Void

    @State private var code = ""
    @FocusState private var focused: Bool

    private let length = 6

    var body: some View {
        VStack(spacing: 0) {
            if let demoCode {
                DemoOtpBanner(code: demoCode)
                    .padding(.horizontal, 14)
                    .padding(.top, 12)
            }

            VStack(spacing: 18) {
                Text(title)
                    .font(.system(size: 18, weight: .bold))
                    .foregroundStyle(Theme.text1)

                Text(subtitle)
                    .font(.system(size: 13))
                    .foregroundStyle(Theme.text3)
                    .multilineTextAlignment(.center)
                    .fixedSize(horizontal: false, vertical: true)

                boxes

                if card.attemptsLeft < 3 {
                    Text("\(card.attemptsLeft) attempt\(card.attemptsLeft == 1 ? "" : "s") left")
                        .font(.system(size: 11, weight: .semibold))
                        .foregroundStyle(Theme.warning)
                }

                PrimaryButton(
                    title: isVerifying ? "…" : confirmTitle,
                    enabled: code.count == length && !isVerifying
                ) {
                    onVerify(code)
                }

                Button(action: onResend) {
                    Text(resendTitle)
                        .font(.system(size: 13, weight: .medium))
                        .foregroundStyle(Theme.link)
                        .frame(minHeight: Metrics.minimumTapTarget)
                }
                .buttonStyle(.plain)
            }
            .padding(.horizontal, 26)
            .padding(.top, 22)

            Spacer(minLength: 0)
        }
        .frame(maxWidth: .infinity)
        .background(Theme.card)
        .presentationDetents([.height(demoCode == nil ? 400 : 470)])
        .onAppear { focused = true }
    }

    private var boxes: some View {
        ZStack {
            // The real field: invisible, focused, and the only thing iOS sees.
            TextField("", text: $code)
                .keyboardType(.numberPad)
                .textContentType(.oneTimeCode)
                .focused($focused)
                .opacity(0.01)
                .frame(height: 1)
                .onChange(of: code) { _, newValue in
                    // Digits only, capped. A pasted "OTP is 482913" becomes
                    // 482913 rather than being rejected.
                    let digits = newValue.filter(\.isNumber)
                    code = String(digits.prefix(length))
                }

            HStack(spacing: 9) {
                ForEach(0..<length, id: \.self) { index in
                    OtpBox(
                        digit: digit(at: index),
                        isActive: focused && index == code.count
                    )
                }
            }
            .onTapGesture { focused = true }
        }
    }

    private func digit(at index: Int) -> String {
        guard index < code.count else { return "" }
        return String(Array(code)[index])
    }

    private var title: String {
        switch language {
        case .marathi: return "OTP टाइप करा"
        case .hindi: return "OTP टाइप कीजिए"
        case .english: return "Type the OTP"
        }
    }

    private var subtitle: String {
        switch language {
        case .marathi: return "तुमच्या मोबाईलवर आलेला ६ अंकी कोड. तो कधीच बोलून सांगू नका."
        case .hindi: return "आपके मोबाइल पर आया 6 अंकों का कोड। इसे कभी बोलकर न बताएँ।"
        case .english: return "The 6-digit code sent to your phone. Never say it out loud."
        }
    }

    private var confirmTitle: String {
        switch language {
        case .marathi: return "पुष्टी करा"
        case .hindi: return "पुष्टि करें"
        case .english: return "Confirm"
        }
    }

    private var resendTitle: String {
        switch language {
        case .marathi: return "नवीन कोड पाठवा"
        case .hindi: return "नया कोड भेजें"
        case .english: return "Send a new code"
        }
    }
}

private struct OtpBox: View {
    let digit: String
    let isActive: Bool

    var body: some View {
        Text(digit)
            .font(.system(size: 21, weight: .bold, design: .monospaced))
            .foregroundStyle(Theme.text1)
            .frame(width: 44, height: 54)
            .background(Theme.bg, in: RoundedRectangle(cornerRadius: 11))
            .overlay(
                RoundedRectangle(cornerRadius: 11)
                    .strokeBorder(isActive ? Theme.navy : Theme.hairline, lineWidth: isActive ? 2 : 1)
            )
            .animation(.easeOut(duration: 0.15), value: isActive)
    }
}

/// The demo-OTP banner (§5.6).
///
/// Styled like a notification and labelled "not a real SMS", because during a
/// demo the code has to be visible on the projector and nobody watching should
/// be left thinking an SMS gateway is involved.
private struct DemoOtpBanner: View {
    let code: String

    var body: some View {
        HStack(spacing: 11) {
            Image(systemName: "bell.badge.fill")
                .font(.system(size: 15))
                .foregroundStyle(Theme.navy)

            VStack(alignment: .leading, spacing: 1) {
                Text("Demo OTP: \(code)")
                    .font(.system(size: 14, weight: .bold, design: .monospaced))
                    .foregroundStyle(Theme.text1)
                Text("not a real SMS")
                    .font(.system(size: 10, weight: .semibold))
                    .foregroundStyle(Theme.danger)
            }
            Spacer()
        }
        .padding(12)
        .background(Theme.badgeNew.opacity(0.35), in: RoundedRectangle(cornerRadius: 14))
        .overlay(
            RoundedRectangle(cornerRadius: 14)
                .strokeBorder(Theme.badgeNew, lineWidth: 1)
        )
    }
}
