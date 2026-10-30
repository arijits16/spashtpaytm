import Foundation

/// Every API path the app uses (build plan §8.2), in one place.
///
/// String paths scattered through view models are how a typo becomes a 404 at
/// demo time. These are relative to `AppConfig.apiBaseURL`, so they all start
/// with `/api`.
enum Endpoints {

    // MARK: - Phase 0

    /// `GET /api/health` — `{status, db, sarvam, version}`.
    static let health = "/api/health"

    // MARK: - Phase 1

    /// `GET` / `PATCH /api/me` — the signed-in profile.
    static let me = "/api/me"

    // MARK: - Phase 3: the journey

    /// `POST /api/journeys` — start, or get the active one back.
    static let journeys = "/api/journeys"

    /// `GET /api/journeys/current` — resume after a relaunch.
    static let currentJourney = "/api/journeys/current"

    /// `GET /api/journeys/{id}` — re-render without advancing.
    static func journey(_ id: UUID) -> String { "/api/journeys/\(id.uuidString.lowercased())" }

    /// `POST /api/journeys/{id}/turn` — one customer turn.
    static func turn(_ id: UUID) -> String { "\(journey(id))/turn" }

    /// `POST /api/journeys/{id}/voice` — a recorded clip (phase 7).
    static func voice(_ id: UUID) -> String { "\(journey(id))/voice" }

    static func otpSend(_ id: UUID) -> String { "\(journey(id))/otp/send" }
    static func otpVerify(_ id: UUID) -> String { "\(journey(id))/otp/verify" }

    // MARK: - Phase 6: receipts

    /// `GET /api/kfs/{id}/file` — the sample KFS PDF.
    static func kfsFile(_ documentId: String) -> String { "/api/kfs/\(documentId)/file" }

    /// `GET /api/receipts/{no}` — the full masked payload, for the owner.
    static func receipt(_ number: String) -> String { "/api/receipts/\(number)" }

    // MARK: - Phase 7: audio

    /// Cached TTS audio. The path arrives in `TurnMessage.audioUrl`, already
    /// built by the backend, so this exists only for the rare direct call.
    static func audio(key: String) -> String { "/api/audio/\(key).mp3" }

    // MARK: - Phase 10: rescue

    /// `GET /api/rescue/pending` — polled while the app is in the foreground.
    static let rescuePending = "/api/rescue/pending"

    static func rescueAccept(_ taskId: UUID) -> String {
        "/api/rescue/\(taskId.uuidString.lowercased())/accept"
    }

    /// `POST /api/rescue/{taskId}/decline` — closes the task so the phone is
    /// never rung twice about the same application.
    static func rescueDecline(_ taskId: UUID) -> String {
        "/api/rescue/\(taskId.uuidString.lowercased())/decline"
    }
}
