import FirebaseAuth
import FirebaseCore
import Foundation
import Observation

/// The app's session (build plan phase 1).
///
/// Owns four things and nothing else: which state we are in, wiring a fresh
/// token into `APIClient` before every request, fetching `/api/me`, and signing
/// out. It holds **no business logic** (plan rule 10) — `isAdmin`, the persona
/// and the language all come from the backend.
///
/// A fresh ID token is fetched per request rather than cached: Firebase renews
/// automatically as one nears expiry, and a stale token mid-demo would log the
/// user out for no reason.
@MainActor
@Observable
final class AuthService {

    enum State: Equatable {
        case starting
        case signedOut
        case signingIn
        case signedIn(Me)

        var me: Me? {
            if case .signedIn(let me) = self { return me }
            return nil
        }

        var isBusy: Bool {
            self == .starting || self == .signingIn
        }
    }

    private(set) var state: State = .starting

    /// Last failure, in words a person can act on. Cleared when a new attempt starts.
    private(set) var errorMessage: String?

    /// Whether to offer "Continue with Google": Firebase must be configured.
    var isGoogleAvailable: Bool { GoogleSignInService.isAvailable }

    /// The signed-in Firebase user, or nil — including when Firebase was never
    /// configured.
    ///
    /// Every access to `Auth.auth()` goes through here. Calling it on an
    /// unconfigured app is a trap, not a thrown error, so there is no recovering
    /// from it at the call site.
    static func currentFirebaseUser() -> User? {
        guard FirebaseApp.app() != nil else { return nil }
        return Auth.auth().currentUser
    }

    /// Whether to offer "Continue as demo user" (Debug + a demo key).
    var isDemoAvailable: Bool {
        #if DEBUG
            return DemoAuth.isAvailable
        #else
            return false
        #endif
    }

    private let client: APIClient
    private var authStateHandle: AuthStateDidChangeListenerHandle?

    init(client: APIClient = .shared) {
        self.client = client
    }

    // MARK: - Startup

    /// Wire the token providers and restore any existing session.
    ///
    /// Called once from the root view's `.task`.
    func start() async {
        GoogleSignInService.configureFirebaseIfPossible()

        // A fresh token per request. Returns nil when signed out, which is what
        // makes the demo headers the fallback rather than a competitor.
        //
        // The `FirebaseApp.app() != nil` check is load-bearing: `Auth.auth()`
        // traps when Firebase was never configured, and it is never configured
        // on a machine without GoogleService-Info.plist. Without this guard the
        // app crashes on the first demo request — which is precisely the path a
        // teammate uses before they have set Firebase up.
        await client.setAuthTokenProvider {
            guard let user = await MainActor.run(body: { Self.currentFirebaseUser() }) else {
                return nil
            }
            return try? await user.getIDToken()
        }

        #if DEBUG
            await client.setDemoProvider {
                guard let identity = await MainActor.run(body: { DemoAuth.restore() }) else {
                    return nil
                }
                return DemoAuth.headers(for: identity)
            }
        #endif

        await restoreSession()
    }

    /// Resume whatever session the last launch left behind.
    private func restoreSession() async {
        #if DEBUG
            if DemoAuth.restore() != nil {
                await loadProfile()
                return
            }
        #endif

        guard Self.currentFirebaseUser() != nil else {
            state = .signedOut
            return
        }
        await loadProfile()
    }

    // MARK: - Sign in

    func signInWithGoogle() async {
        errorMessage = nil
        state = .signingIn
        do {
            #if DEBUG
                // A real token outranks the demo headers on both sides, but
                // clearing it keeps the stored state honest too.
                DemoAuth.persist(nil)
            #endif
            try await GoogleSignInService.signIn()
            await loadProfile()
        } catch {
            errorMessage = (error as? LocalizedError)?.errorDescription ?? error.localizedDescription
            state = .signedOut
        }
    }

    #if DEBUG
        func signInAsDemoUser(_ identity: DemoAuth.Identity = .sunita) async {
            errorMessage = nil
            state = .signingIn

            // End any real Firebase session first. `APIClient` prefers a bearer
            // token over the demo headers, so leaving one in place would keep
            // the real identity active behind a demo badge (decision D-016).
            if isGoogleAvailable {
                GoogleSignInService.signOut()
            }
            DemoAuth.persist(identity)
            await loadProfile()
        }
    #endif

    // MARK: - Sign out

    func signOut() async {
        #if DEBUG
            DemoAuth.persist(nil)
        #endif
        if isGoogleAvailable {
            GoogleSignInService.signOut()
        }
        errorMessage = nil
        state = .signedOut
    }

    // MARK: - Profile

    /// Fetch `/api/me` and settle the state.
    ///
    /// A 401 here means the credentials were refused, so the session is ended
    /// rather than left half-authenticated showing a spinner.
    func loadProfile() async {
        do {
            state = .signedIn(try await client.get(Endpoints.me, as: Me.self))
        } catch let error as APIError {
            if error.isUnauthorized {
                await signOut()
                errorMessage = "Your session has expired. Please sign in again."
            } else {
                errorMessage = error.userMessage
                state = .signedOut
            }
        } catch {
            errorMessage = "Could not load your profile."
            state = .signedOut
        }
    }

    /// Change the language and persist it (`PATCH /api/me`).
    ///
    /// Non-throwing: callers that have nowhere to show an error get the message
    /// in `errorMessage` instead.
    func setLanguage(_ language: Language) async {
        do {
            try await updateLanguage(language)
        } catch let error as APIError {
            errorMessage = error.userMessage
        } catch {
            errorMessage = "Could not save your language."
        }
    }

    /// Change the language, propagating the failure.
    ///
    /// The language sheet needs this: it has a visible error row and a Save
    /// button to keep enabled, and silently dismissing after a failed save
    /// would leave the customer believing a product about speaking their
    /// language had agreed to speak it.
    func updateLanguage(_ language: Language) async throws {
        let updated: Me = try await client.patch(
            Endpoints.me, body: MePatch(preferredLanguage: language), as: Me.self
        )
        state = .signedIn(updated)
    }
}
