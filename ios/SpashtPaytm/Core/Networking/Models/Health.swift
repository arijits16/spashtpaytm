import Foundation

/// `GET /api/health` (build plan §8.2).
///
/// Mirrors `backend/app/api/health.py` and the committed fixture
/// `contracts/fixtures/health.json`, which `HealthContractTests` decodes — so
/// if the backend renames a field, the iOS build fails rather than the demo.
struct Health: Decodable, Equatable, Sendable {

    /// `ok` when the database answered, `degraded` when it did not.
    let status: Status

    /// `"ok"`, or `"error: <type>"`. A string, not a bool, because the reason
    /// is what makes the failure fixable on stage.
    let db: String

    /// Whether a Sarvam key is configured, or the backend is in demo mode.
    let sarvam: Sarvam

    /// Backend version, e.g. `0.2.0`.
    let version: String

    /// `dev` | `test` | `prod`.
    let env: String

    /// True when `DEMO_MODE=true`; the app shows the "Demo mode" chip (§10.6).
    let demoMode: Bool

    enum Status: String, Decodable, Sendable {
        case ok
        case degraded
    }

    enum Sarvam: String, Decodable, Sendable {
        case configured
        case demo
    }

    /// True when the database is reachable.
    var isDatabaseHealthy: Bool { status == .ok }
}
