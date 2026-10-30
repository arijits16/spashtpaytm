import XCTest

@testable import SpashtPaytm

/// `APIClient` behaviour, against a stubbed `URLProtocol` (build plan phase 0/1).
///
/// No network and no backend: the point is to pin down the headers the client
/// sends and how it turns responses into typed errors. Those are the rules that
/// quietly break a demo — a missing ngrok header means the app gets an HTML
/// warning page instead of JSON, and nothing in the UI explains why.
final class APIClientTests: XCTestCase {

    private var client: APIClient!

    override func setUp() {
        super.setUp()
        StubURLProtocol.reset()

        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [StubURLProtocol.self]
        client = APIClient(session: URLSession(configuration: configuration))
    }

    override func tearDown() {
        StubURLProtocol.reset()
        client = nil
        super.tearDown()
    }

    // MARK: - Headers

    func testSendsNgrokSkipHeader() async throws {
        StubURLProtocol.respond(json: #"{"ok": true}"#)

        _ = try? await client.get("/api/health", as: Empty.self)

        let request = try XCTUnwrap(StubURLProtocol.lastRequest)
        XCTAssertEqual(
            request.value(forHTTPHeaderField: "ngrok-skip-browser-warning"),
            "1",
            "Without this header ngrok serves its interstitial instead of our JSON."
        )
    }

    func testAddsBearerTokenWhenSignedIn() async throws {
        await client.setAuthTokenProvider { "fake-id-token" }
        StubURLProtocol.respond(json: #"{"ok": true}"#)

        _ = try? await client.get("/api/me", as: Empty.self)

        let request = try XCTUnwrap(StubURLProtocol.lastRequest)
        XCTAssertEqual(request.value(forHTTPHeaderField: "Authorization"), "Bearer fake-id-token")
        XCTAssertNil(request.value(forHTTPHeaderField: "X-Demo-User"))
    }

    func testSendsNoAuthHeaderWhenSignedOut() async throws {
        StubURLProtocol.respond(json: #"{"ok": true}"#)

        _ = try? await client.get("/api/health", as: Empty.self)

        let request = try XCTUnwrap(StubURLProtocol.lastRequest)
        XCTAssertNil(request.value(forHTTPHeaderField: "Authorization"))
        XCTAssertNil(request.value(forHTTPHeaderField: "X-Demo-User"))
        XCTAssertNil(request.value(forHTTPHeaderField: "X-Demo-Key"))
    }

    func testDemoHeadersAreSentWhenThereIsNoToken() async throws {
        await client.setDemoProvider { (persona: "sunita", key: "test-demo-key") }
        StubURLProtocol.respond(json: #"{"ok": true}"#)

        _ = try? await client.get("/api/me", as: Empty.self)

        let request = try XCTUnwrap(StubURLProtocol.lastRequest)
        XCTAssertEqual(request.value(forHTTPHeaderField: "X-Demo-User"), "sunita")
        XCTAssertEqual(request.value(forHTTPHeaderField: "X-Demo-Key"), "test-demo-key")
    }

    func testRealTokenWinsOverDemoHeaders() async throws {
        /// Mirrors the backend's precedence in `app/deps.py`. Sending both would
        /// let the UI show a demo badge while acting as the real user.
        await client.setAuthTokenProvider { "real-token" }
        await client.setDemoProvider { (persona: "sunita", key: "test-demo-key") }
        StubURLProtocol.respond(json: #"{"ok": true}"#)

        _ = try? await client.get("/api/me", as: Empty.self)

        let request = try XCTUnwrap(StubURLProtocol.lastRequest)
        XCTAssertEqual(request.value(forHTTPHeaderField: "Authorization"), "Bearer real-token")
        XCTAssertNil(request.value(forHTTPHeaderField: "X-Demo-User"))
        XCTAssertNil(request.value(forHTTPHeaderField: "X-Demo-Key"))
    }

    // MARK: - Decoding

    func testDecodesASuccessfulResponse() async throws {
        StubURLProtocol.respond(
            json: #"""
                {"status":"ok","db":"ok","sarvam":"demo","version":"0.2.0","env":"dev","demoMode":false}
                """#
        )

        let health = try await client.get(Endpoints.health, as: Health.self)

        XCTAssertEqual(health.status, .ok)
        XCTAssertEqual(health.version, "0.2.0")
    }

    // MARK: - Errors

    func testMapsTheErrorEnvelope() async {
        StubURLProtocol.respond(
            json: #"""
                {"error":{"code":"unauthorized","message":"Not authenticated","requestId":"abc123"}}
                """#,
            status: 401
        )

        do {
            _ = try await client.get(Endpoints.me, as: Empty.self)
            XCTFail("expected an APIError")
        } catch let error as APIError {
            XCTAssertTrue(error.isUnauthorized)
            XCTAssertEqual(error.code, "unauthorized")
            XCTAssertEqual(error.requestId, "abc123")
            XCTAssertEqual(error.userMessage, "Not authenticated")
        } catch {
            XCTFail("expected an APIError, got \(error)")
        }
    }

    func testMapsANonEnvelopeErrorBody() async {
        /// What ngrok's interstitial or a proxy timeout page looks like.
        StubURLProtocol.respond(body: Data("<html>tunnel error</html>".utf8), status: 502)

        do {
            _ = try await client.get(Endpoints.health, as: Health.self)
            XCTFail("expected an APIError")
        } catch let error as APIError {
            guard case .unexpectedStatus(let status, _) = error else {
                return XCTFail("expected .unexpectedStatus, got \(error)")
            }
            XCTAssertEqual(status, 502)
            XCTAssertTrue(error.isRetryable)
        } catch {
            XCTFail("expected an APIError, got \(error)")
        }
    }

    func testReportsDecodingFailures() async {
        /// Contract drift: 200, but not the shape the app expects.
        StubURLProtocol.respond(json: #"{"unexpected": true}"#)

        do {
            _ = try await client.get(Endpoints.health, as: Health.self)
            XCTFail("expected an APIError")
        } catch let error as APIError {
            guard case .decoding = error else {
                return XCTFail("expected .decoding, got \(error)")
            }
            XCTAssertFalse(error.isRetryable, "retrying cannot fix a shape mismatch")
        } catch {
            XCTFail("expected an APIError, got \(error)")
        }
    }

    func testReportsTransportFailures() async {
        StubURLProtocol.fail(with: URLError(.cannotConnectToHost))

        do {
            _ = try await client.get(Endpoints.health, as: Health.self)
            XCTFail("expected an APIError")
        } catch let error as APIError {
            guard case .transport = error else {
                return XCTFail("expected .transport, got \(error)")
            }
            XCTAssertTrue(error.isRetryable)
            XCTAssertEqual(error.userMessage, "Could not reach the server. Is the backend running?")
        } catch {
            XCTFail("expected an APIError, got \(error)")
        }
    }

    // MARK: - Helpers

    /// A model that decodes any JSON object, for tests that only inspect the request.
    private struct Empty: Decodable {}
}

// MARK: - URLProtocol stub

/// Intercepts requests so tests never touch the network.
final class StubURLProtocol: URLProtocol, @unchecked Sendable {

    private struct Stub {
        var status: Int
        var body: Data
        var headers: [String: String]
        var error: URLError?
    }

    private static let lock = NSLock()
    nonisolated(unsafe) private static var stub = Stub(
        status: 200, body: Data("{}".utf8), headers: [:], error: nil
    )
    nonisolated(unsafe) private static var captured: URLRequest?

    /// The request the client actually sent.
    static var lastRequest: URLRequest? {
        lock.lock()
        defer { lock.unlock() }
        return captured
    }

    static func reset() {
        lock.lock()
        defer { lock.unlock() }
        stub = Stub(status: 200, body: Data("{}".utf8), headers: [:], error: nil)
        captured = nil
    }

    static func respond(json: String, status: Int = 200) {
        respond(
            body: Data(json.utf8),
            status: status,
            headers: ["Content-Type": "application/json", "X-Request-ID": "stub-request-id"]
        )
    }

    static func respond(
        body: Data,
        status: Int = 200,
        headers: [String: String] = ["X-Request-ID": "stub-request-id"]
    ) {
        lock.lock()
        defer { lock.unlock() }
        stub = Stub(status: status, body: body, headers: headers, error: nil)
    }

    static func fail(with error: URLError) {
        lock.lock()
        defer { lock.unlock() }
        stub = Stub(status: 0, body: Data(), headers: [:], error: error)
    }

    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

    override func startLoading() {
        Self.lock.lock()
        Self.captured = request
        let current = Self.stub
        Self.lock.unlock()

        if let error = current.error {
            client?.urlProtocol(self, didFailWithError: error)
            return
        }

        let response = HTTPURLResponse(
            url: request.url!,
            statusCode: current.status,
            httpVersion: "HTTP/1.1",
            headerFields: current.headers
        )!

        client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: current.body)
        client?.urlProtocolDidFinishLoading(self)
    }

    override func stopLoading() {}
}
