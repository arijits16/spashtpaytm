import Foundation

/// The backend's error envelope (build plan §8.1).
///
/// Every failure from the API looks like this, including ones the route never
/// saw (404 on an unknown path, 422 from validation), so one decode covers all
/// of them:
///
///     {"error": {"code": "...", "message": "...", "requestId": "..."}}
struct APIErrorBody: Decodable, Equatable, Sendable {
    let code: String
    let message: String
    let requestId: String

    private enum Outer: String, CodingKey { case error }
    private enum Inner: String, CodingKey { case code, message, requestId }

    init(from decoder: Decoder) throws {
        let outer = try decoder.container(keyedBy: Outer.self)
        let inner = try outer.nestedContainer(keyedBy: Inner.self, forKey: .error)
        code = try inner.decode(String.self, forKey: .code)
        message = try inner.decode(String.self, forKey: .message)
        requestId = try inner.decode(String.self, forKey: .requestId)
    }

    /// Memberwise init for tests and for synthesising an error locally.
    init(code: String, message: String, requestId: String) {
        self.code = code
        self.message = message
        self.requestId = requestId
    }
}

/// Everything that can go wrong on the way to a decoded response.
///
/// Carries enough for the UI to react differently to "sign in again" versus
/// "the venue Wi-Fi died" — during the demo those need very different
/// handling, and a single `.failed` case would collapse them.
enum APIError: Error, Sendable {

    /// The backend answered with a non-2xx and the standard envelope.
    case api(status: Int, body: APIErrorBody)

    /// A non-2xx that did not carry the envelope — a proxy or tunnel error page.
    case unexpectedStatus(status: Int, requestId: String?)

    /// `URLSession` failed: no network, DNS, TLS, timeout, cancelled.
    case transport(URLError)

    /// 2xx, but the body did not match the model. This is a contract drift bug,
    /// which is what `contracts/fixtures` exists to catch before a demo.
    case decoding(DecodingError, requestId: String?)

    /// A URL could not be built from `AppConfig` plus the path.
    case badURL(String)

    // MARK: - Presentation

    /// True when the session is gone and the app must return to login (§13.2).
    var isUnauthorized: Bool {
        if case .api(let status, _) = self { return status == 401 }
        return false
    }

    /// True when retrying the same request could plausibly work.
    var isRetryable: Bool {
        switch self {
        case .transport(let error):
            return error.code != .cancelled
        case .api(let status, _):
            return status == 429 || status >= 500
        case .unexpectedStatus(let status, _):
            return status >= 500
        case .decoding, .badURL:
            return false
        }
    }

    /// The backend's `code`, when there was one. Lets a view branch on
    /// `consent_locked` without re-deriving it from the status.
    var code: String? {
        if case .api(_, let body) = self { return body.code }
        return nil
    }

    /// The request id, for showing in an error state so a log line can be found.
    var requestId: String? {
        switch self {
        case .api(_, let body): return body.requestId
        case .unexpectedStatus(_, let id): return id
        case .decoding(_, let id): return id
        case .transport, .badURL: return nil
        }
    }

    /// A message safe and useful to show a customer.
    ///
    /// The backend's own message is preferred: it is written for a person and
    /// already free of internals. Transport failures get our own wording,
    /// because `URLError`'s text is not something to show in a demo.
    var userMessage: String {
        switch self {
        case .api(_, let body):
            return body.message
        case .unexpectedStatus(let status, _):
            return "The server replied unexpectedly (\(status)). Please try again."
        case .transport(let error) where error.code == .notConnectedToInternet:
            return "No internet connection."
        case .transport(let error) where error.code == .timedOut:
            return "The server took too long to reply. Please try again."
        case .transport(let error) where error.code == .cannotConnectToHost:
            return "Could not reach the server. Is the backend running?"
        case .transport:
            return "Network problem. Please try again."
        case .decoding:
            return "The app could not read the server's reply. Please update the app."
        case .badURL:
            return "The app is misconfigured. Check the API address in Dev settings."
        }
    }
}
