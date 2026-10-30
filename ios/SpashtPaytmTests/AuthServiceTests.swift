import XCTest

@testable import SpashtPaytm

/// `AuthService` behaviour without Firebase configured (build plan phase 1).
///
/// The test bundle has no `GoogleService-Info.plist`, which is the same state a
/// teammate is in before they have done Appendix D.2 — and the state the demo
/// login exists to work around. So these tests run in exactly the configuration
/// that broke.
@MainActor
final class AuthServiceTests: XCTestCase {

    /// Regression: the app crashed on launch whenever a demo session was
    /// restored on a machine with no plist.
    ///
    /// `AuthService.start()` installed a token provider that called
    /// `Auth.auth().currentUser`, and the first demo request invoked it.
    /// `Auth.auth()` **traps** when `FirebaseApp.configure()` was never called,
    /// so this was a hard crash with no recovery at the call site — and it hit
    /// precisely the path that is supposed to work without Firebase.
    func testCurrentFirebaseUserIsNilWhenFirebaseIsNotConfigured() {
        XCTAssertNil(
            AuthService.currentFirebaseUser(),
            "Must return nil rather than trap when Firebase was never configured."
        )
    }

    /// Google sign-in is offered **exactly when** the config is present.
    ///
    /// Asserted as a relationship rather than as a fixed expectation, because
    /// both sides are legitimate: a fresh clone has no
    /// `GoogleService-Info.plist` and must hide the button, while a configured
    /// machine has one and must show it. An earlier version of this test
    /// hard-coded "unavailable" and started failing the moment the plist was
    /// added — it was testing the checkout, not the behaviour.
    func testGoogleAvailabilityTracksTheBundledConfig() {
        let auth = AuthService()

        XCTAssertEqual(
            auth.isGoogleAvailable,
            AppConfig.isGoogleSignInConfigured,
            "The Google button must appear if and only if the Firebase config is bundled."
        )
    }

    /// Whichever side of that we are on, the demo path must stand alone.
    ///
    /// This is the promise phase 1 makes: if the plist is missing, everything
    /// else still works and the phase report says what is absent.
    func testDemoLoginDoesNotDependOnGoogle() {
        #if DEBUG
            XCTAssertEqual(
                AppConfig.isDemoLoginAvailable,
                AppConfig.demoAuthKey != nil,
                "Demo login depends only on the demo key, never on Firebase."
            )
        #else
            XCTAssertFalse(
                AppConfig.isDemoLoginAvailable,
                "Release builds must never offer the demo login."
            )
        #endif
    }

    func testStartingUpWithoutCredentialsSettlesOnSignedOut() async {
        let auth = AuthService()
        XCTAssertEqual(auth.state, .starting)

        await auth.start()

        // Must reach a terminal state: a view stuck on `.starting` is the blank
        // screen this test exists to prevent.
        XCTAssertNotEqual(auth.state, .starting)
        XCTAssertNotEqual(auth.state, .signingIn)
    }

    func testSignOutIsSafeWithoutFirebase() async {
        let auth = AuthService()

        await auth.signOut()

        XCTAssertEqual(auth.state, .signedOut)
    }

    #if DEBUG
        func testDemoHeadersNeedAKey() {
            // `AppConfig.demoAuthKey` comes from the xcconfig. Whatever it is in
            // this build, availability and header-building must agree — offering
            // the button without a key would only ever produce a 401.
            if AppConfig.demoAuthKey == nil {
                XCTAssertFalse(DemoAuth.isAvailable)
                XCTAssertNil(DemoAuth.headers(for: .sunita))
            } else {
                XCTAssertTrue(DemoAuth.isAvailable)
                let headers = DemoAuth.headers(for: .sunita)
                XCTAssertEqual(headers?.persona, "sunita")
                XCTAssertFalse(headers?.key.isEmpty ?? true)
            }
        }

        func testDemoSessionRoundTrips() {
            let original = DemoAuth.restore()
            defer { DemoAuth.persist(original) }

            DemoAuth.persist(.sunita)
            if DemoAuth.isAvailable {
                XCTAssertEqual(DemoAuth.restore(), .sunita)
            }

            DemoAuth.persist(nil)
            XCTAssertNil(DemoAuth.restore())
        }

        func testTheDashboardIdentityIsSeparateFromTheCustomer() {
            // The website signs in as `demo-admin`; the app as `sunita`.
            XCTAssertEqual(DemoAuth.Identity.demoAdmin.rawValue, "demo-admin")
            XCTAssertEqual(DemoAuth.Identity.sunita.rawValue, "sunita")
        }
    #endif
}
