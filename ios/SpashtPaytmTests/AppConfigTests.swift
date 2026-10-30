import XCTest

@testable import SpashtPaytm

/// `AppConfig` and the Info.plist wiring (build plan §13.11, §14.3).
///
/// These assert the security properties that are easy to break silently: that
/// a Release build carries no demo key, and that the plist keys the app reads
/// actually exist with the values the xcconfigs were meant to supply.
final class AppConfigTests: XCTestCase {

    // MARK: - The demo login must never ship

    func testDemoLoginIsUnavailableInRelease() throws {
        #if DEBUG
            throw XCTSkip("Release-only check; run `make ios-test CONFIG=Release`.")
        #else
            XCTAssertNil(
                AppConfig.demoAuthKey,
                "Release.xcconfig must blank DEMO_AUTH_KEY (build plan 13.11)."
            )
            XCTAssertFalse(AppConfig.isDemoLoginAvailable)
        #endif
    }

    func testDemoLoginNeedsAKeyEvenInDebug() {
        /// `DEMO_AUTH=true` alone is not enough on either side: the backend
        /// requires a matching `X-Demo-Key`, so offering the button without a
        /// key would only ever produce a confusing 401.
        if AppConfig.demoAuthKey == nil {
            XCTAssertFalse(AppConfig.isDemoLoginAvailable)
        }
    }

    // MARK: - Configuration is readable

    func testAPIBaseURLIsAnAbsoluteURL() {
        let url = AppConfig.apiBaseURL

        XCTAssertNotNil(url.scheme, "API_BASE_URL must include a scheme.")
        XCTAssertNotNil(url.host, "API_BASE_URL must include a host.")
        XCTAssertTrue(
            ["http", "https"].contains(url.scheme ?? ""),
            "Unexpected scheme \(url.scheme ?? "nil"). In xcconfig, write URLs as https:/$()/host."
        )
    }

    func testPublicBaseURLIsAnAbsoluteURL() {
        XCTAssertNotNil(AppConfig.publicBaseURL.host)
    }

    func testAppVersionIsReported() {
        /// Goes onto every receipt as `app_version` (§11.1).
        XCTAssertTrue(AppConfig.appVersion.hasPrefix("spasht-ios-"))
        XCTAssertFalse(AppConfig.appVersion.hasSuffix("0.0.0"), "CFBundleShortVersionString is unset")
    }

    // MARK: - Info.plist keys the app depends on

    func testInfoPlistCarriesTheKeysTheAppReads() {
        for key in ["APIBaseURL", "PublicBaseURL", "DemoAuthKey"] {
            XCTAssertNotNil(
                Bundle.main.object(forInfoDictionaryKey: key),
                "\(key) is missing from the Info.plist for this configuration."
            )
        }
    }

    func testBundleDisplayNameIsTheConceptName() {
        /// §5.1: the Home-screen name must say this is a concept.
        XCTAssertEqual(
            Bundle.main.object(forInfoDictionaryKey: "CFBundleDisplayName") as? String,
            "Spasht (Concept)"
        )
    }

    func testMicrophoneUsageDescriptionIsPresent() {
        /// Without it iOS kills the app the moment the mic is requested (phase 7).
        let description =
            Bundle.main.object(forInfoDictionaryKey: "NSMicrophoneUsageDescription") as? String
        XCTAssertNotNil(description)
        XCTAssertFalse(description?.isEmpty ?? true)
    }

    // MARK: - Debug override

    #if DEBUG
        func testAPIBaseURLOverrideRoundTrips() {
            let original = UserDefaults.standard.string(forKey: AppConfig.apiBaseURLOverrideKey)
            defer { AppConfig.setAPIBaseURLOverride(original) }

            AppConfig.setAPIBaseURLOverride("https://example.ngrok-free.app")
            XCTAssertEqual(AppConfig.apiBaseURL.absoluteString, "https://example.ngrok-free.app")

            AppConfig.setAPIBaseURLOverride(nil)
            XCTAssertNotEqual(AppConfig.apiBaseURL.absoluteString, "https://example.ngrok-free.app")
        }

        func testBlankOverrideIsIgnored() {
            let original = UserDefaults.standard.string(forKey: AppConfig.apiBaseURLOverrideKey)
            defer { AppConfig.setAPIBaseURLOverride(original) }

            AppConfig.setAPIBaseURLOverride("   ")
            XCTAssertNil(AppConfig.overriddenAPIBaseURL)
        }
    #endif
}
