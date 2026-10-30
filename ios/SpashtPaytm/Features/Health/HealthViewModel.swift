import Foundation
import Observation

/// View model behind `HealthView` (build plan phase 0).
///
/// `@Observable` + `@MainActor` (plan rule 14): state is only ever mutated on
/// the main actor, so SwiftUI never observes a half-updated value, and the
/// `await` hop happens off it.
@MainActor
@Observable
final class HealthViewModel {

    enum State {
        case loading
        case loaded(Health)
        case failed(APIError)

        var isLoading: Bool {
            if case .loading = self { return true }
            return false
        }
    }

    private(set) var state: State = .loading

    private let client: APIClient

    init(client: APIClient = .shared) {
        self.client = client
    }

    /// The one line the phase-0 acceptance check reads: `Backend: OK · DB: OK`.
    var summaryLine: String {
        switch state {
        case .loading:
            return "Checking…"
        case .failed:
            return "Backend: FAIL · DB: ?"
        case .loaded(let health):
            let backend = health.status == .ok ? "OK" : "DEGRADED"
            let database = health.isDatabaseHealthy ? "OK" : "FAIL"
            return "Backend: \(backend) · DB: \(database)"
        }
    }

    /// Fetch `/api/health`.
    ///
    /// A failure here is never fatal: the view shows the reason and a Retry
    /// button, because the most likely cause during a demo is that the tunnel
    /// moved or the laptop slept — both recoverable without relaunching.
    func load() async {
        state = .loading
        do {
            state = .loaded(try await client.get(Endpoints.health, as: Health.self))
        } catch let error as APIError {
            state = .failed(error)
        } catch {
            // `APIClient` only throws `APIError`; this keeps the compiler happy
            // without an unsafe cast.
            state = .failed(.transport(URLError(.unknown)))
        }
    }
}
