import Foundation

/// Pre-warming before the demo's first turn (build plan §10.4, phase 12).
///
/// The first request of a session is the slowest one of the session, and on
/// stage it is the one everybody watches. Four things are cold at launch:
///
/// 1. the ngrok tunnel, which has to establish a connection to the laptop;
/// 2. the TLS handshake and the HTTP/2 connection to that host;
/// 3. the backend's SQLAlchemy pool, which opens its first connection lazily;
/// 4. the audio session, whose first activation takes a beat.
///
/// A `GET /api/health` warms the first three in one request that costs nothing
/// and cannot fail visibly: the result is discarded, and a failure here means
/// the journey's own error handling will report it properly a moment later.
///
/// The first *audio* lines are pre-warmed server-side by `make tts-cache`, and
/// on the client by `SpeechPlayer`, which downloads every line of a turn before
/// it starts speaking and keeps the bytes - the cache keys are a hash of the
/// text, so a replayed line never costs a second fetch.
enum Prewarm {

    /// Ping the backend, ignoring the outcome. Safe to call repeatedly.
    static func ping() {
        Task.detached(priority: .utility) {
            _ = try? await APIClient.shared.get(Endpoints.health, as: Health.self)
        }
    }
}
