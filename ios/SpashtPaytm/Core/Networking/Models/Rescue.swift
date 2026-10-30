import Foundation

/// The rescue-agent wire format (build plan §8.2, phase 10).
///
/// Mirrors `backend/app/api/rescue.py`. `GET /api/rescue/pending` answers with
/// `call: null` rather than a 404 when nothing is waiting - the app polls this
/// every fifteen seconds, and a 404 for the normal case would be indis-
/// tinguishable from a broken route.

/// One simulated incoming call.
struct RescueCall: Decodable, Sendable, Equatable, Identifiable {
    let taskId: UUID
    let journeyId: UUID

    /// `stuck` when the journey just stopped, `human` when it was handed off.
    let kind: String

    /// The step the customer stopped on. Accept resumes **exactly** here.
    let step: String

    let language: Language

    /// "Spasht · Paytm Loans" and "Concept demo · simulated call", both chosen
    /// by the backend so the labels can change without an app release.
    let callerName: String
    let subtitle: String

    /// The `rescue_call` line (§8.6) in the journey's language, and the cached
    /// mp3 for it. `audioUrl` can be nil: the caption is always on screen, so
    /// a cache miss degrades to reading rather than to a silent broken call.
    let line: String
    let audioUrl: String?

    let createdAt: String

    var id: UUID { taskId }
}

/// `GET /api/rescue/pending`.
struct RescuePendingResponse: Decodable, Sendable {
    let call: RescueCall?

    /// How often the backend wants to be polled. Sent rather than hard-coded
    /// so the cadence is the server's decision (plan rule 10).
    let pollSeconds: Int
}

/// `POST /api/rescue/{taskId}/decline`.
struct RescueDeclineResponse: Decodable, Sendable {
    let closed: Bool
}
