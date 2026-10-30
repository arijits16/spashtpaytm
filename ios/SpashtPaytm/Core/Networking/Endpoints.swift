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

    // MARK: - Phase 3 onwards
    //
    // Added as each phase lands, so this list always reflects what the app
    // actually calls rather than what it might call one day.
}
