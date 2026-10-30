import XCTest

@testable import SpashtPaytm

/// Decode every committed contract fixture (build plan §8.5).
///
/// This is the mechanism that keeps the backend, the app and the website
/// agreeing about the API. The backend regenerates `contracts/fixtures/*.json`
/// with `make contracts`; if a field was renamed, added or retyped without the
/// Swift model following, the decode here fails and the build goes red before
/// anyone points a phone at a judge.
final class ContractTests: XCTestCase {

    /// The copy build phase must actually have run.
    func testFixturesArePresent() throws {
        let names = FixtureLoader.allFixtureNames()
        XCTAssertFalse(
            names.isEmpty,
            "No contract fixtures in the test bundle. Run `make contracts` then `make ios-gen`."
        )
    }

    // MARK: - GET /api/health

    func testHealthFixtureDecodes() throws {
        let health = try FixtureLoader.decode(Health.self, from: "health")

        XCTAssertEqual(health.status, .ok)
        XCTAssertEqual(health.db, "ok")
        XCTAssertTrue(health.isDatabaseHealthy)
        XCTAssertFalse(health.version.isEmpty)
        XCTAssertFalse(health.env.isEmpty)
    }

    func testDegradedHealthDecodes() throws {
        /// Postgres stopped: the backend still answers 200 (decision D-009) so
        /// the app can say *what* broke. The app must not treat this as a
        /// failure to decode.
        let json = """
            {
              "status": "degraded",
              "db": "error: OperationalError",
              "sarvam": "demo",
              "version": "0.2.0",
              "env": "dev",
              "demoMode": true
            }
            """.data(using: .utf8)!

        let health = try JSONDecoder().decode(Health.self, from: json)

        XCTAssertEqual(health.status, .degraded)
        XCTAssertFalse(health.isDatabaseHealthy)
        XCTAssertEqual(health.sarvam, .demo)
        XCTAssertTrue(health.demoMode)
    }

    // MARK: - The error envelope

    func testErrorFixtureDecodes() throws {
        let error = try FixtureLoader.decode(APIErrorBody.self, from: "error_not_found")

        XCTAssertEqual(error.code, "not_found")
        XCTAssertFalse(error.message.isEmpty)
        XCTAssertFalse(error.requestId.isEmpty)
    }

    func testErrorEnvelopeIsRequiredInFull() {
        /// A partial envelope must fail rather than decode with empty strings:
        /// a silently blank `code` would break the `consent_locked` handling in
        /// phase 5.
        let json = """
            {"error": {"code": "unauthorized"}}
            """.data(using: .utf8)!

        XCTAssertThrowsError(try JSONDecoder().decode(APIErrorBody.self, from: json))
    }
}
