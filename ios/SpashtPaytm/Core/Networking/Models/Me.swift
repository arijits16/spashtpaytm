import Foundation

/// `GET /api/me` (build plan §8.2).
///
/// Mirrors `backend/app/api/me.py` and `contracts/fixtures/me.json`, which
/// `ContractTests` decodes. A backend field rename fails the iOS build rather
/// than the demo.
struct Me: Decodable, Equatable, Sendable {

    /// The Firebase uid, or `demo:<identity>` for a dev demo session.
    let uid: String

    let email: String?
    let displayName: String?
    let photoUrl: String?

    /// `mr-IN` | `hi-IN` | `en-IN`.
    let preferredLanguage: Language

    /// Whether this user may open the compliance dashboard. Decided entirely by
    /// the backend from a **verified** allowlisted email; the app only displays
    /// it, and the website's route guard is cosmetic on top of the same check.
    let isAdmin: Bool

    /// How this request authenticated.
    ///
    /// The demo badge is driven from this rather than from the app's own state,
    /// so it can never claim a demo session while acting as the real user.
    let session: SessionKind

    /// The linked synthetic customer. Null for `demo-admin`, who has no journey.
    let persona: Persona?

    enum SessionKind: String, Decodable, Sendable {
        case firebase
        case demo
    }

    /// The linked synthetic customer. Masked values only: the persona's real
    /// name stays on the backend, where the assistant uses it to build the
    /// spoken honorific.
    struct Persona: Decodable, Equatable, Sendable {
        let id: String
        let displayNameMasked: String?
        let language: Language?
        let city: String?
        let occupation: String?
        let mobileMasked: String?
    }

    /// True for a dev demo session rather than a real Google sign-in.
    var isDemoSession: Bool { session == .demo }

    /// What to show as the user's name, falling back through what we have.
    var displayLabel: String {
        displayName ?? email ?? "Signed in"
    }

    /// Up to two initials for the avatar when there is no photo (§5.3).
    var initials: String {
        let source = displayName ?? email ?? "?"
        let letters =
            source
            .split(whereSeparator: { $0 == " " || $0 == "." || $0 == "@" })
            .prefix(2)
            .compactMap { $0.first }
            .map { String($0).uppercased() }
        return letters.isEmpty ? "?" : letters.joined()
    }
}

/// The three languages the journey supports (§8.3).
///
/// `Decodable` by raw value, so an unknown locale from a newer backend throws
/// rather than silently becoming Marathi — the wrong language is worse than a
/// visible error in a product whose whole point is being understood.
enum Language: String, Codable, CaseIterable, Sendable {
    case marathi = "mr-IN"
    case hindi = "hi-IN"
    case english = "en-IN"

    /// The name of the language, written in that language (§5.6).
    var nativeName: String {
        switch self {
        case .marathi: return "मराठी"
        case .hindi: return "हिंदी"
        case .english: return "English"
        }
    }
}

/// Body of `PATCH /api/me`.
struct MePatch: Encodable, Sendable {
    let preferredLanguage: Language
}
