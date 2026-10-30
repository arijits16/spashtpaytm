import Foundation
import Observation

/// Drives one journey (build plan §5.6, phase 5).
///
/// **It holds no business logic** (plan rule 10). It sends what the customer
/// did, stores the `TurnResponse` that comes back, and exposes it for the views
/// to render. It does not know what step follows which, whether a consent may
/// be given, or what an EMI is.
///
/// Two things it is responsible for, both about reliability rather than rules:
///
/// 1. **Idempotency.** A failed turn keeps its `clientTurnId` so that tapping
///    "retry" replays rather than re-applies. A loan application must not
///    advance twice because a tunnel dropped a response.
/// 2. **Accumulating the conversation.** The backend returns only this turn's
///    messages; the transcript on screen is the running total.
@Observable
@MainActor
final class JourneyViewModel {

    enum Phase: Equatable {
        case idle
        /// A turn is in flight. `Thinking…` appears after 400 ms (§10.4).
        case working
        case failed(String)
    }

    // MARK: - State

    private(set) var response: TurnResponse?

    /// Every bubble so far, oldest first.
    private(set) var transcript: [TurnMessage] = []

    private(set) var phase: Phase = .idle

    /// True once `Thinking…` should be visible. Delayed so a fast turn does not
    /// flash a spinner, which reads as jank rather than as progress.
    private(set) var showsThinking = false

    /// The demo OTP, when the backend chose to reveal one (dev only).
    private(set) var demoOtpCode: String?

    private let client: APIClient
    private let auth: AuthService

    /// Kept across retries so a retry is the *same* turn (§8.3).
    private var pendingTurnId: UUID?

    /// The input a failed turn was carrying, so "retry" needs no arguments.
    private var pendingInput: TurnInput?

    init(client: APIClient = .shared, auth: AuthService) {
        self.client = client
        self.auth = auth
    }

    // MARK: - Derived

    var step: String { response?.step ?? "" }
    var card: Card? { response?.card }
    var language: Language { response?.language ?? .marathi }
    var quickReplies: [QuickReply] { response?.quickReplies ?? [] }
    var acceptEnabled: Bool { response?.locks.acceptEnabled ?? false }
    var lockReason: String? { response?.locks.reason }
    var isDemoMode: Bool { response?.demoMode ?? false }
    var progress: TurnResponse.Progress? { response?.progress }

    var isFinished: Bool { step == "DONE" || step == "RECEIPT" }
    var needsHuman: Bool { response?.status == .needsHuman }

    /// True when a turn can be sent: not already working, and not finished.
    var acceptsInput: Bool {
        if case .working = phase { return false }
        return !isFinished && !needsHuman
    }

    // MARK: - Lifecycle

    /// Start, or resume whatever is already running.
    ///
    /// `POST /journeys` returns the existing active journey rather than
    /// refusing (§8.2), so this is safe to call every time the screen appears -
    /// which is what makes "kill the app and relaunch" land on the right step.
    func start(language: Language) async {
        await perform {
            try await self.client.post(
                Endpoints.journeys,
                body: StartJourneyRequest(language: language),
                as: TurnResponse.self
            )
        }
    }

    /// Re-fetch the current step without advancing it.
    func refresh() async {
        guard let journeyId = response?.journeyId else { return }
        await perform {
            try await self.client.get(Endpoints.journey(journeyId), as: TurnResponse.self)
        }
    }

    // MARK: - Turns

    func send(text: String) async {
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return }
        await takeTurn(.text(trimmed))
    }

    func send(action: JourneyAction) async {
        await takeTurn(.tap(action))
    }

    /// Send a backend-composed quick reply.
    ///
    /// The action half is relayed opaquely: the backend built it for this step,
    /// so the app does not need to understand it and a new chip needs no app
    /// release.
    func send(quickReply: QuickReply) async {
        if quickReply.send.type == "text", let text = quickReply.send.text {
            await send(text: text)
        } else if let raw = quickReply.send.action {
            await takeTurn(.tap(.relay(raw)))
        }
    }

    /// Re-send the turn that failed, with its original id.
    func retry() async {
        guard let input = pendingInput else {
            await refresh()
            return
        }
        await takeTurn(input, reusingId: true)
    }

    private func takeTurn(_ input: TurnInput, reusingId: Bool = false) async {
        guard let journeyId = response?.journeyId else { return }
        guard acceptsInput || reusingId else { return }

        // A retry must carry the id the server already saw, or it is a new turn.
        let turnId = (reusingId ? pendingTurnId : nil) ?? UUID()
        pendingTurnId = turnId
        pendingInput = input

        // The customer's own words appear immediately rather than after the
        // round trip: a chat that lags behind your typing feels broken.
        if case .text(let spoken) = input {
            appendLocalUserBubble(spoken)
        }

        let request = TurnRequest(
            clientTurnId: turnId,
            expectedVersion: response?.version,
            input: input
        )

        await perform {
            try await self.client.post(
                Endpoints.turn(journeyId), body: request, as: TurnResponse.self
            )
        } onSuccess: {
            // Only cleared on success, so a failure keeps the id for a retry.
            self.pendingTurnId = nil
            self.pendingInput = nil
        }
    }

    // MARK: - OTP

    /// Ask for a code. Returns the demo code when the backend reveals one.
    func sendOtp() async -> String? {
        guard let journeyId = response?.journeyId else { return nil }
        phase = .working
        defer { phase = .idle }

        do {
            let sent: OtpSendResponse = try await client.post(
                Endpoints.otpSend(journeyId), body: Optional<Never>.none, as: OtpSendResponse.self
            )
            demoOtpCode = sent.demoCode
            return sent.demoCode
        } catch {
            phase = .failed(message(for: error))
            return nil
        }
    }

    /// Verify the code. On success the response carries the receipt card.
    func verifyOtp(code: String) async {
        guard let journeyId = response?.journeyId else { return }
        await perform {
            try await self.client.post(
                Endpoints.otpVerify(journeyId),
                body: OtpVerifyRequest(code: code),
                as: TurnResponse.self
            )
        }
    }

    // MARK: - Plumbing

    /// Run a request, managing the phase, the thinking indicator and errors.
    private func perform(
        _ work: @escaping () async throws -> TurnResponse,
        onSuccess: (() -> Void)? = nil
    ) async {
        phase = .working

        // §10.4: show `Thinking…` only after 400 ms.
        let thinking = Task { @MainActor in
            try? await Task.sleep(for: .milliseconds(400))
            guard !Task.isCancelled else { return }
            if case .working = self.phase { self.showsThinking = true }
        }

        do {
            let next = try await work()
            apply(next)
            phase = .idle
            onSuccess?()
        } catch {
            phase = .failed(message(for: error))
        }

        thinking.cancel()
        showsThinking = false
    }

    /// Merge a response into the on-screen state.
    private func apply(_ next: TurnResponse) {
        response = next
        demoOtpCode = demoOtpCode ?? (next.card.flatMap(Self.demoCode))

        // Server messages replace any optimistic bubble with the same role and
        // text, so a locally-echoed utterance is not shown twice.
        for message in next.messages {
            if let index = transcript.firstIndex(where: {
                $0.id.hasPrefix("local:") && $0.role == message.role && $0.text == message.text
            }) {
                transcript[index] = message
            } else if !transcript.contains(where: { $0.id == message.id }) {
                transcript.append(message)
            }
        }
    }

    private static func demoCode(from card: Card) -> String? {
        if case .otp(let otp) = card { return otp.demoCode }
        return nil
    }

    private func appendLocalUserBubble(_ text: String) {
        transcript.append(
            TurnMessage(
                id: "local:\(UUID().uuidString)",
                role: .user,
                text: text,
                audioUrl: nil
            )
        )
    }

    private func message(for error: Error) -> String {
        guard let apiError = error as? APIError else {
            return "Something went wrong. Please try again."
        }
        if apiError.isUnauthorized {
            Task { await auth.signOut() }
            return "Your session has expired. Please sign in again."
        }
        return apiError.userMessage
    }
}
