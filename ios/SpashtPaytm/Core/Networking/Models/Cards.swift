import Foundation

/// The card union (build plan §8.4).
///
/// Decoded by switching on `type`. **An unknown type becomes `.unsupported`**
/// rather than throwing: a newer backend sending a card this build has never
/// heard of must show "please update the app", not fail to decode the whole
/// response and lose the conversation.
enum Card: Decodable, Sendable, Equatable {
    case language(LanguageCard)
    case amount(AmountCard)
    case consent(ConsentCard)
    case manualForm(ManualFormCard)
    case prefill(PrefillCard)
    case confirm(ConfirmCard)
    case offers(OffersCard)
    case kfs(KfsCard)
    case quiz(QuizCard)
    case consentLock(ConsentLockCard)
    case otp(OtpCard)
    case receipt(ReceiptCard)
    case handoff(HandoffCard)

    /// A card type this build does not know. Carries the raw type string so the
    /// message can name it and a bug report is actionable.
    case unsupported(String)

    private enum CodingKeys: String, CodingKey {
        case type, data
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        let type = try container.decode(String.self, forKey: .type)

        switch type {
        case "language":
            self = .language(try container.decode(LanguageCard.self, forKey: .data))
        case "amount":
            self = .amount(try container.decode(AmountCard.self, forKey: .data))
        case "consent":
            self = .consent(try container.decode(ConsentCard.self, forKey: .data))
        case "manual_form":
            self = .manualForm(try container.decode(ManualFormCard.self, forKey: .data))
        case "prefill":
            self = .prefill(try container.decode(PrefillCard.self, forKey: .data))
        case "confirm":
            self = .confirm(try container.decode(ConfirmCard.self, forKey: .data))
        case "offers":
            self = .offers(try container.decode(OffersCard.self, forKey: .data))
        case "kfs":
            self = .kfs(try container.decode(KfsCard.self, forKey: .data))
        case "quiz":
            self = .quiz(try container.decode(QuizCard.self, forKey: .data))
        case "consent_lock":
            self = .consentLock(try container.decode(ConsentLockCard.self, forKey: .data))
        case "otp":
            self = .otp(try container.decode(OtpCard.self, forKey: .data))
        case "receipt":
            self = .receipt(try container.decode(ReceiptCard.self, forKey: .data))
        case "handoff":
            self = .handoff(try container.decode(HandoffCard.self, forKey: .data))
        default:
            self = .unsupported(type)
        }
    }
}

// MARK: - Card payloads

struct LanguageCard: Decodable, Sendable, Equatable {
    struct Option: Decodable, Sendable, Equatable, Identifiable {
        let language: Language
        let label: String
        var id: Language { language }
    }
    let options: [Option]
}

struct AmountCard: Decodable, Sendable, Equatable {
    let chips: [Int]
    let min: Int
    let max: Int
}

struct ConsentCard: Decodable, Sendable, Equatable {
    struct Purpose: Decodable, Sendable, Equatable, Identifiable {
        let id: String
        let title: String
        let detail: String
        /// Always false from the server. The toggle's own state is local and
        /// also starts off, so there is no path on which a consent arrives
        /// pre-granted (§5.6).
        let granted: Bool
    }
    let purposes: [Purpose]
    let why: String
}

struct ManualFormCard: Decodable, Sendable, Equatable {
    struct Field: Decodable, Sendable, Equatable, Identifiable {
        let id: String
        let label: String
        let kind: String
        let required: Bool
    }
    let fields: [Field]
}

struct PrefillCard: Decodable, Sendable, Equatable {
    struct Row: Decodable, Sendable, Equatable, Identifiable {
        let label: String
        let value: String
        /// DigiLocker / CKYC / Account Aggregator / UPI AutoPay. Shown as a tag
        /// beside the value - the provenance is the point of the screen.
        let source: String
        var id: String { "\(source):\(label)" }
    }
    let rows: [Row]
}

struct ConfirmCard: Decodable, Sendable, Equatable {
    struct Field: Decodable, Sendable, Equatable, Identifiable {
        let id: String
        let label: String
        let value: String
    }
    let fields: [Field]
}

struct OffersCard: Decodable, Sendable, Equatable {
    struct Suitability: Decodable, Sendable, Equatable {
        /// A percentage (16.4), not a fraction.
        let foirPct: Double
        let decision: String
        let reasons: [String]
    }

    struct Offer: Decodable, Sendable, Equatable, Identifiable {
        let offerId: String
        let lender: String
        let lenderType: String
        let principal: Int
        let tenureMonths: Int
        let ratePa: Double
        let processingFee: Int
        let gst: Int
        /// The figure the card shows in bold, and the sort key.
        let apr: Double
        let emi: Int
        let totalRepay: Int
        /// Interest plus fee plus GST: what the customer loses.
        let totalCost: Int
        let badges: [String]
        let kfsUrl: String

        var id: String { offerId }

        var isCheapest: Bool { badges.contains("lowest_total_cost") }
        var isLowRateHighFee: Bool { badges.contains("low_rate_high_fee") }
    }

    let suitability: Suitability
    let offers: [Offer]
}

struct KfsCard: Decodable, Sendable, Equatable {
    struct Line: Decodable, Sendable, Equatable, Identifiable {
        let key: String
        let text: String
        /// Rendered in red: the charges a customer is most likely to be
        /// surprised by later.
        let redFlag: Bool
        var id: String { key }
    }

    let offerId: String
    let lender: String
    let version: String
    let lines: [Line]
    let pdfUrl: String
    let sample: Bool
}

struct QuizCard: Decodable, Sendable, Equatable {
    struct Option: Decodable, Sendable, Equatable, Identifiable {
        let id: String
        let text: String
    }

    struct Result: Decodable, Sendable, Equatable {
        let correct: Bool
        let explanation: String?
    }

    let questionId: String
    let index: Int
    let total: Int
    let prompt: String
    let options: [Option]
    let attempt: Int
    let maxAttempts: Int
    /// Present after an answer. Drives the correct / incorrect styling and the
    /// haptic (§5.6).
    let result: Result?
}

struct ConsentLockCard: Decodable, Sendable, Equatable {
    struct Insurance: Decodable, Sendable, Equatable {
        let premium: Int
        let granted: Bool
        let optional: Bool
    }

    let acceptEnabled: Bool
    let reason: String?
    /// One line per thing being agreed to, in the journey's language.
    let terms: [String]
    let insurance: Insurance
}

struct OtpCard: Decodable, Sendable, Equatable {
    let length: Int
    let expiresInSec: Int
    let attemptsLeft: Int
    /// Dev only. Shown in a banner that says it is not a real SMS.
    let demoCode: String?
}

struct ReceiptCard: Decodable, Sendable, Equatable {
    struct Teachback: Decodable, Sendable, Equatable {
        let passed: Int
        let total: Int
    }

    let receiptNo: String
    let lender: String
    let emi: Int
    let tenureMonths: Int
    let totalRepay: Int
    let language: Language
    let teachback: Teachback
    let insuranceTaken: Bool
    /// What the QR code encodes. Built by the backend from `PUBLIC_BASE_URL`,
    /// never by the app, so it cannot be pointed somewhere else.
    let publicUrl: String
    let summaryText: String
    let createdAt: String
}

struct HandoffCard: Decodable, Sendable, Equatable {
    let message: String
    let window: String
}
