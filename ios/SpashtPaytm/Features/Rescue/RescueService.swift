import Foundation
import Observation

/// Polls for a waiting rescue call (build plan §12, phase 10).
///
/// `GET /api/rescue/pending` every fifteen seconds **while the app is in the
/// foreground**. Polling rather than a push: a concept demo should not need
/// APNs certificates to work on a loaned device, and a fifteen-second poll on
/// one route is cheaper than the certificate dance is to explain.
///
/// The loop stops the moment the app is backgrounded, which is both battery
/// manners and the honest behaviour - the screen it would show cannot be shown
/// from the background anyway.
///
/// **It decides nothing.** Whether a call may be placed - the contact window,
/// DND, the consent to callbacks - is the backend's judgement, re-checked on
/// every poll (§9). This type shows what it is given.
@Observable
@MainActor
final class RescueService {

    /// The call to ring, or nil. The view presents on this changing.
    private(set) var call: RescueCall?

    /// True while Accept or Decline is in flight, so the buttons can disable.
    private(set) var isWorking = false

    private let client: APIClient
    private var poller: Task<Void, Never>?

    /// Default cadence (§12). The backend's `pollSeconds` overrides it.
    private var interval: Duration = .seconds(15)

    /// Tasks already answered on this device, so a poll that races a decline
    /// cannot put the call straight back on screen.
    private var dismissed: Set<UUID> = []

    init(client: APIClient = .shared) {
        self.client = client
    }

    // MARK: - Lifecycle

    /// Start polling. Safe to call repeatedly: a second call is ignored.
    func start() {
        guard poller == nil else { return }

        poller = Task { [weak self] in
            while !Task.isCancelled {
                await self?.pollOnce()
                guard let interval = self?.interval else { return }
                try? await Task.sleep(for: interval)
            }
        }
    }

    func stop() {
        poller?.cancel()
        poller = nil
    }

    private func pollOnce() async {
        // Nothing to poll for while a call is already on screen, and a poll
        // landing mid-decision would be a second ring over the first.
        guard call == nil, !isWorking else { return }

        do {
            let pending: RescuePendingResponse = try await client.get(
                Endpoints.rescuePending, as: RescuePendingResponse.self
            )

            if pending.pollSeconds > 0 {
                interval = .seconds(pending.pollSeconds)
            }

            if let incoming = pending.call, !dismissed.contains(incoming.taskId) {
                call = incoming
            }
        } catch {
            // Signed out, tunnel down, backend restarting: all of them mean
            // "no call right now". A polling loop that surfaces every transient
            // failure would paper the home screen with error toasts.
            return
        }
    }

    // MARK: - Answering

    /// Accept the call. Returns the journey screen for **the exact step the
    /// customer stopped on**, built by the backend's `resume()`.
    func accept(_ incoming: RescueCall) async -> TurnResponse? {
        isWorking = true
        defer { isWorking = false }

        dismissed.insert(incoming.taskId)

        do {
            let response: TurnResponse = try await client.post(
                Endpoints.rescueAccept(incoming.taskId),
                body: Optional<Never>.none,
                as: TurnResponse.self
            )
            call = nil
            return response
        } catch {
            // The call closes rather than hanging on a failed resume: the
            // journey is still there, and the customer can open it from home.
            call = nil
            return nil
        }
    }

    /// Decline. The backend closes the task, so it is never rung again - a task
    /// left open would ring fifteen seconds later, which is the harassment the
    /// contact-window rules exist to prevent.
    func decline(_ incoming: RescueCall) async {
        isWorking = true
        defer { isWorking = false }

        dismissed.insert(incoming.taskId)
        call = nil

        _ = try? await client.post(
            Endpoints.rescueDecline(incoming.taskId),
            body: Optional<Never>.none,
            as: RescueDeclineResponse.self
        )
    }
}
