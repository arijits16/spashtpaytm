import SwiftUI

/// The offers, KFS and quiz cards (build plan §5.6).
///
/// These three carry the product's argument, so they get their own file: the
/// comparison that shows the cheapest rate is not the cheapest loan, the five
/// lines that name the charges, and the questions that decide whether the
/// customer may agree at all.

// MARK: - Offers

struct OffersCardView: View {
    let data: OffersCard
    let language: Language
    let onAction: (JourneyAction) -> Void
    let onOpenPdf: (String) -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            SuitabilityRow(suitability: data.suitability)

            // Already sorted by APR server-side (§9). The app renders the order
            // it was given rather than re-sorting - that decision is not the
            // client's to make.
            ForEach(data.offers) { offer in
                OfferRow(
                    offer: offer,
                    language: language,
                    onChoose: { onAction(.selectOffer(offer.offerId)) },
                    onOpenPdf: { onOpenPdf(offer.kfsUrl) }
                )
            }
        }
    }
}

private struct SuitabilityRow: View {
    let suitability: OffersCard.Suitability

    var body: some View {
        JourneyCard {
            HStack(spacing: 8) {
                Image(systemName: suitability.decision == "suitable"
                    ? "checkmark.seal.fill" : "exclamationmark.triangle.fill")
                    .font(.system(size: 15))
                    .foregroundStyle(suitability.decision == "suitable" ? Theme.success : Theme.warning)
                Text("EMI \(Int(suitability.foirPct.rounded()))% of income")
                    .font(.system(size: 13, weight: .bold))
                    .foregroundStyle(Theme.text1)
            }

            ForEach(suitability.reasons, id: \.self) { reason in
                Text("· \(reason)")
                    .font(.system(size: 12))
                    .foregroundStyle(Theme.text2)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
    }
}

private struct OfferRow: View {
    let offer: OffersCard.Offer
    let language: Language
    let onChoose: () -> Void
    let onOpenPdf: () -> Void

    var body: some View {
        JourneyCard {
            HStack(alignment: .top) {
                VStack(alignment: .leading, spacing: 1) {
                    Text(offer.lender)
                        .font(.system(size: 15, weight: .bold))
                        .foregroundStyle(Theme.text1)
                    Text(offer.lenderType)
                        .font(.system(size: 10, weight: .medium))
                        .foregroundStyle(Theme.text3)
                }
                Spacer()
                VStack(alignment: .trailing, spacing: 0) {
                    // APR in bold, because it is the number that actually
                    // compares two offers (§5.6).
                    Text(Format.percent(offer.apr))
                        .font(.system(size: 19, weight: .heavy))
                        .foregroundStyle(Theme.text1)
                    Text("APR")
                        .font(.system(size: 9, weight: .bold))
                        .foregroundStyle(Theme.text3)
                }
            }

            if !offer.badges.isEmpty {
                HStack(spacing: 6) {
                    if offer.isCheapest {
                        OfferBadge(
                            text: "Lowest total cost",
                            colour: Theme.success,
                            symbol: "checkmark.circle.fill"
                        )
                    }
                    if offer.isLowRateHighFee {
                        // Amber, and worded as a warning. It is the trap, not a
                        // recommendation.
                        OfferBadge(
                            text: "Low rate, but high fees",
                            colour: Theme.warning,
                            symbol: "exclamationmark.circle.fill"
                        )
                    }
                }
            }

            Divider()

            VStack(spacing: 6) {
                FigureRow(label: "Interest rate", value: Format.percent(offer.ratePa))
                FigureRow(
                    label: "Processing fee",
                    value: offer.processingFee == 0
                        ? "None"
                        : "₹\(Format.rupees(offer.processingFee)) + ₹\(Format.rupees(offer.gst)) GST",
                    emphasised: offer.processingFee > 0
                )
                FigureRow(
                    label: "EMI × \(offer.tenureMonths)",
                    value: "₹\(Format.rupees(offer.emi))"
                )
                FigureRow(label: "Total repay", value: "₹\(Format.rupees(offer.totalRepay))")
                FigureRow(
                    label: "Total cost of credit",
                    value: "₹\(Format.rupees(offer.totalCost))",
                    emphasised: true
                )
            }

            HStack(spacing: 10) {
                PrimaryButton(title: Strings.selectOffer(language), action: onChoose)

                Button(action: onOpenPdf) {
                    Text(Strings.viewKfs(language))
                        .font(.system(size: 13, weight: .semibold))
                        .foregroundStyle(Theme.link)
                        .frame(width: 94, height: 50)
                }
                .buttonStyle(.plain)
                .disabled(offer.kfsUrl.isEmpty)
            }
        }
    }
}

private struct OfferBadge: View {
    let text: String
    let colour: Color
    let symbol: String

    var body: some View {
        HStack(spacing: 4) {
            Image(systemName: symbol).font(.system(size: 9, weight: .bold))
            Text(text).font(.system(size: 10, weight: .bold))
        }
        .foregroundStyle(colour)
        .padding(.horizontal, 8)
        .padding(.vertical, 4)
        .background(colour.opacity(0.12), in: Capsule())
    }
}

private struct FigureRow: View {
    let label: String
    let value: String
    var emphasised = false

    var body: some View {
        HStack {
            Text(label)
                .font(.system(size: 12))
                .foregroundStyle(Theme.text3)
            Spacer()
            Text(value)
                .font(.system(size: 13, weight: emphasised ? .bold : .semibold))
                .foregroundStyle(emphasised ? Theme.text1 : Theme.text2)
        }
    }
}

// MARK: - KFS

struct KfsCardView: View {
    let data: KfsCard
    let language: Language
    let onOpenPdf: (String) -> Void

    var body: some View {
        JourneyCard {
            HStack {
                Text(headline)
                    .font(.system(size: 15, weight: .bold))
                    .foregroundStyle(Theme.text1)
                Spacer()
                // The sample tag is mandatory (§5.1): these are invented terms
                // from fictional lenders.
                Text("SAMPLE TERMS")
                    .font(.system(size: 8, weight: .heavy))
                    .foregroundStyle(Theme.text3)
                    .padding(.horizontal, 6)
                    .padding(.vertical, 3)
                    .background(Theme.bg, in: Capsule())
            }

            Text("\(data.lender) · \(data.version)")
                .font(.system(size: 11))
                .foregroundStyle(Theme.text3)

            VStack(alignment: .leading, spacing: 9) {
                ForEach(data.lines) { line in
                    HStack(alignment: .top, spacing: 8) {
                        Circle()
                            .fill(line.redFlag ? Theme.danger : Theme.success)
                            .frame(width: 6, height: 6)
                            .padding(.top, 5)
                        Text(line.text)
                            .font(.system(size: 13, weight: line.redFlag ? .semibold : .regular))
                            .foregroundStyle(line.redFlag ? Theme.danger : Theme.text2)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                }
            }

            Button {
                onOpenPdf(data.pdfUrl)
            } label: {
                HStack(spacing: 6) {
                    Image(systemName: "doc.text")
                    Text(readFullKfs)
                }
                .font(.system(size: 13, weight: .semibold))
                .foregroundStyle(Theme.link)
                .frame(minHeight: Metrics.minimumTapTarget)
            }
            .buttonStyle(.plain)
            .disabled(data.pdfUrl.isEmpty)
        }
    }

    private var headline: String {
        switch language {
        case .marathi: return "तुमचं कर्ज ५ ओळींत"
        case .hindi: return "आपका लोन 5 लाइनों में"
        case .english: return "Your loan in 5 lines"
        }
    }

    private var readFullKfs: String {
        switch language {
        case .marathi: return "संपूर्ण KFS वाचा (PDF)"
        case .hindi: return "पूरा KFS पढ़ें (PDF)"
        case .english: return "Read full KFS (PDF)"
        }
    }
}

// MARK: - Quiz

struct QuizCardView: View {
    let data: QuizCard
    let isSending: Bool
    let onAction: (JourneyAction) -> Void

    /// Which option was just tapped, so it can be styled while the turn is in
    /// flight. Cleared by the new card arriving.
    @State private var chosen: String?

    var body: some View {
        JourneyCard {
            HStack {
                Text("Question \(data.index) of \(data.total)")
                    .font(.system(size: 10, weight: .bold))
                    .foregroundStyle(Theme.text3)
                Spacer()
                if data.attempt > 1 {
                    Text("Attempt \(data.attempt) of \(data.maxAttempts)")
                        .font(.system(size: 10, weight: .semibold))
                        .foregroundStyle(Theme.warning)
                }
            }

            Text(data.prompt)
                .font(.system(size: 16, weight: .semibold))
                .foregroundStyle(Theme.text1)
                .fixedSize(horizontal: false, vertical: true)

            ForEach(data.options) { option in
                QuizOptionButton(
                    option: option,
                    state: state(for: option),
                    enabled: !isSending && data.result == nil,
                    onTap: {
                        chosen = option.id
                        onAction(.quizAnswer(questionId: data.questionId, optionId: option.id))
                    }
                )
            }

            if let result = data.result, !result.correct, let explanation = result.explanation {
                HStack(alignment: .top, spacing: 8) {
                    Image(systemName: "lightbulb.fill")
                        .font(.system(size: 13))
                        .foregroundStyle(Theme.warning)
                    Text(explanation)
                        .font(.system(size: 12.5))
                        .foregroundStyle(Theme.text2)
                        .fixedSize(horizontal: false, vertical: true)
                }
                .padding(11)
                .background(Theme.warning.opacity(0.1), in: RoundedRectangle(cornerRadius: 12))
            }
        }
        // §5.6: a success haptic on a correct answer.
        .sensoryFeedback(.success, trigger: data.result?.correct == true)
        .sensoryFeedback(.error, trigger: data.result?.correct == false)
        .onChange(of: data.questionId) { chosen = nil }
    }

    enum OptionState {
        case plain, chosen, correct, wrong
    }

    private func state(for option: QuizCard.Option) -> OptionState {
        guard let result = data.result else {
            return option.id == chosen ? .chosen : .plain
        }
        // Only the tapped option is styled by the result: the server never says
        // which option was correct, so a wrong answer cannot be used to reveal
        // the right one without actually understanding it.
        guard option.id == chosen else { return .plain }
        return result.correct ? .correct : .wrong
    }
}

private struct QuizOptionButton: View {
    let option: QuizCard.Option
    let state: QuizCardView.OptionState
    let enabled: Bool
    let onTap: () -> Void

    var body: some View {
        Button(action: onTap) {
            HStack(alignment: .top, spacing: 10) {
                Image(systemName: symbol)
                    .font(.system(size: 16))
                    .foregroundStyle(tint)
                Text(option.text)
                    .font(.system(size: 14))
                    .foregroundStyle(Theme.text1)
                    .multilineTextAlignment(.leading)
                    .fixedSize(horizontal: false, vertical: true)
                Spacer(minLength: 0)
            }
            .padding(13)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(background, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
            .overlay(
                RoundedRectangle(cornerRadius: 14, style: .continuous)
                    .strokeBorder(border, lineWidth: 1.5)
            )
        }
        .buttonStyle(.plain)
        .disabled(!enabled)
    }

    private var symbol: String {
        switch state {
        case .plain, .chosen: return "circle"
        case .correct: return "checkmark.circle.fill"
        case .wrong: return "xmark.circle.fill"
        }
    }

    private var tint: Color {
        switch state {
        case .plain: return Theme.hairline
        case .chosen: return Theme.navy
        case .correct: return Theme.success
        case .wrong: return Theme.danger
        }
    }

    private var background: Color {
        switch state {
        case .plain: return Theme.bg
        case .chosen: return Theme.offerStrip.opacity(0.5)
        case .correct: return Theme.success.opacity(0.1)
        case .wrong: return Theme.danger.opacity(0.08)
        }
    }

    private var border: Color {
        switch state {
        case .plain: return .clear
        case .chosen: return Theme.navy.opacity(0.5)
        case .correct: return Theme.success
        case .wrong: return Theme.danger
        }
    }
}
