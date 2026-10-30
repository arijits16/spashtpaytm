import Foundation

/// The single door between the app and the backend (build plan §8, §13).
///
/// Every request goes through here so that the cross-cutting concerns live in
/// exactly one place: the auth header, the ngrok warning-page header, the
/// request id, the timeout, and turning a non-2xx into a typed `APIError`.
///
/// The app holds **no business logic** (plan rule 10). This type does not know
/// what a journey or a receipt is; it moves `Codable` values over HTTP.
///
/// Thread-safety: an `actor` because `authTokenProvider` is mutable state that
/// `AuthService` writes while views read it from arbitrary tasks.
actor APIClient {

    /// Supplies a fresh Firebase ID token, or nil when signed out.
    ///
    /// A closure rather than a reference to `AuthService` so that networking
    /// does not depend on auth — which would be a cycle, since auth calls
    /// `/api/me` through this client.
    typealias TokenProvider = @Sendable () async -> String?

    /// Supplies the dev demo identity, or nil. Debug builds only.
    typealias DemoProvider = @Sendable () async -> (persona: String, key: String)?

    static let shared = APIClient()

    private let session: URLSession
    private let decoder: JSONDecoder
    private let encoder: JSONEncoder

    private var authTokenProvider: TokenProvider = { nil }
    private var demoProvider: DemoProvider = { nil }

    /// §13.4: the app always announces itself so ngrok does not serve its HTML
    /// interstitial instead of our JSON.
    private static let ngrokSkipHeader = "ngrok-skip-browser-warning"

    /// 15 s (phase 0 brief). Long enough for a cold Sarvam call on venue Wi-Fi,
    /// short enough that a dead backend does not hang the UI for a minute.
    private static let requestTimeout: TimeInterval = 15

    init(session: URLSession? = nil) {
        if let session {
            self.session = session
        } else {
            let configuration = URLSessionConfiguration.ephemeral
            configuration.timeoutIntervalForRequest = Self.requestTimeout
            configuration.timeoutIntervalForResource = Self.requestTimeout * 2
            // Always ask the backend; a cached /api/health would be a lie.
            configuration.requestCachePolicy = .reloadIgnoringLocalCacheData
            configuration.waitsForConnectivity = false
            self.session = URLSession(configuration: configuration)
        }

        decoder = JSONDecoder()
        encoder = JSONEncoder()
        // The API is camelCase on the wire (§8.1) and so are the Swift models,
        // so no key conversion strategy is set on purpose.
    }

    // MARK: - Wiring

    /// Install the token source. `AuthService` calls this once at startup.
    func setAuthTokenProvider(_ provider: @escaping TokenProvider) {
        authTokenProvider = provider
    }

    /// Install the demo-identity source (Debug only).
    func setDemoProvider(_ provider: @escaping DemoProvider) {
        demoProvider = provider
    }

    // MARK: - Requests

    /// `GET path` decoded as `T`.
    func get<T: Decodable>(_ path: String, as type: T.Type = T.self) async throws -> T {
        try await send(path: path, method: "GET", body: Optional<Never>.none, as: type)
    }

    /// `POST path` with an optional JSON body, decoded as `T`.
    func post<Body: Encodable, T: Decodable>(
        _ path: String,
        body: Body?,
        as type: T.Type = T.self
    ) async throws -> T {
        try await send(path: path, method: "POST", body: body, as: type)
    }

    /// `PATCH path` with a JSON body, decoded as `T`.
    func patch<Body: Encodable, T: Decodable>(
        _ path: String,
        body: Body,
        as type: T.Type = T.self
    ) async throws -> T {
        try await send(path: path, method: "PATCH", body: body, as: type)
    }

    /// POST a `multipart/form-data` body: a recorded voice turn (§8.2, phase 7).
    ///
    /// Built by hand rather than with a library: it is one file part and a
    /// couple of text fields, and the alternative is a dependency on the
    /// critical path of the product's main interaction.
    ///
    /// The timeout is the session's 15 s, which is the §10.4 budget for a voice
    /// turn end to end - upload, transcribe, engine, synthesise.
    func upload<T: Decodable>(
        _ path: String,
        fileField: String,
        fileName: String,
        mimeType: String,
        fileData: Data,
        fields: [String: String] = [:],
        as type: T.Type = T.self
    ) async throws -> T {
        var request = try await makeRequest(path: path, method: "POST", body: Optional<Never>.none)

        let boundary = "spasht.\(UUID().uuidString)"
        request.setValue(
            "multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "Content-Type"
        )

        var body = Data()
        func append(_ text: String) {
            body.append(Data(text.utf8))
        }

        for (name, value) in fields {
            append("--\(boundary)\r\n")
            append("Content-Disposition: form-data; name=\"\(name)\"\r\n\r\n")
            append("\(value)\r\n")
        }

        append("--\(boundary)\r\n")
        append(
            "Content-Disposition: form-data; name=\"\(fileField)\"; filename=\"\(fileName)\"\r\n"
        )
        append("Content-Type: \(mimeType)\r\n\r\n")
        body.append(fileData)
        append("\r\n--\(boundary)--\r\n")

        request.httpBody = body

        let (data, response) = try await perform(request)
        try check(response: response, data: data)

        do {
            return try decoder.decode(type, from: data)
        } catch let error as DecodingError {
            throw APIError.decoding(error, requestId: requestId(from: response))
        }
    }

    /// Fetch raw bytes (cached TTS audio, a KFS PDF) with the same headers.
    ///
    /// Going through the client rather than handing a URL to `AVPlayer` means
    /// the tunnel and auth headers are present — without them ngrok returns its
    /// warning page and the audio silently fails to play.
    func data(_ path: String) async throws -> Data {
        let request = try await makeRequest(path: path, method: "GET", body: Optional<Never>.none)
        let (data, response) = try await perform(request)
        try check(response: response, data: data)
        return data
    }

    // MARK: - Implementation

    private func send<Body: Encodable, T: Decodable>(
        path: String,
        method: String,
        body: Body?,
        as type: T.Type
    ) async throws -> T {
        let request = try await makeRequest(path: path, method: method, body: body)
        let (data, response) = try await perform(request)
        try check(response: response, data: data)

        do {
            return try decoder.decode(type, from: data)
        } catch let error as DecodingError {
            throw APIError.decoding(error, requestId: requestId(from: response))
        }
    }

    private func makeRequest<Body: Encodable>(
        path: String,
        method: String,
        body: Body?
    ) async throws -> URLRequest {
        let base = AppConfig.apiBaseURL
        guard let url = URL(string: path, relativeTo: base) else {
            throw APIError.badURL(path)
        }

        var request = URLRequest(url: url)
        request.httpMethod = method
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        request.setValue("1", forHTTPHeaderField: Self.ngrokSkipHeader)

        if let body {
            request.httpBody = try encoder.encode(body)
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        }

        // A real token always wins over the demo headers, mirroring the
        // backend's own precedence in `app/deps.py`. Sending both would let the
        // UI claim a demo session while acting as the real user.
        if let token = await authTokenProvider() {
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        } else if let demo = await demoProvider() {
            request.setValue(demo.persona, forHTTPHeaderField: "X-Demo-User")
            request.setValue(demo.key, forHTTPHeaderField: "X-Demo-Key")
        }

        return request
    }

    private func perform(_ request: URLRequest) async throws -> (Data, URLResponse) {
        do {
            return try await session.data(for: request)
        } catch let error as URLError {
            throw APIError.transport(error)
        }
    }

    /// Turn a non-2xx into a typed error, preferring the backend's envelope.
    private func check(response: URLResponse, data: Data) throws {
        guard let http = response as? HTTPURLResponse else { return }
        guard !(200..<300).contains(http.statusCode) else { return }

        if let body = try? decoder.decode(APIErrorBody.self, from: data) {
            throw APIError.api(status: http.statusCode, body: body)
        }
        // No envelope: something between us and the backend answered — the
        // ngrok interstitial, a proxy timeout page.
        throw APIError.unexpectedStatus(
            status: http.statusCode,
            requestId: requestId(from: response)
        )
    }

    private func requestId(from response: URLResponse) -> String? {
        (response as? HTTPURLResponse)?.value(forHTTPHeaderField: "X-Request-ID")
    }
}
