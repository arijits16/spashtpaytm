import FirebaseAuth
import FirebaseCore
import GoogleSignIn
import UIKit

/// Google sign-in, exchanged for a Firebase session (build plan phase 1).
///
/// The flow is: Google returns an ID token and an access token → those become a
/// Firebase credential → Firebase signs in and from then on owns the session
/// and the token refresh. The app never stores a token itself; Firebase keeps
/// them in the Keychain (§13.11).
@MainActor
enum GoogleSignInService {

    enum Failure: LocalizedError {
        case notConfigured
        case noPresenter
        case missingIDToken
        case cancelled

        var errorDescription: String? {
            switch self {
            case .notConfigured:
                return
                    "Google sign-in is not set up yet. Add GoogleService-Info.plist and run `make ios-config`."
            case .noPresenter:
                return "Could not open the Google sign-in screen."
            case .missingIDToken:
                return "Google did not return an ID token."
            case .cancelled:
                return "Sign-in was cancelled."
            }
        }
    }

    /// Configure Firebase, but only when the human has added the plist.
    ///
    /// `FirebaseApp.configure()` traps on a missing file, so a fresh clone would
    /// crash at launch rather than simply showing no Google button.
    static func configureFirebaseIfPossible() {
        guard AppConfig.googleServiceInfoPath != nil else { return }
        guard FirebaseApp.app() == nil else { return }
        FirebaseApp.configure()
    }

    /// True once Firebase is configured and a client ID is available.
    static var isAvailable: Bool {
        FirebaseApp.app()?.options.clientID != nil
    }

    /// Run the full Google → Firebase sign-in. Returns the Firebase user.
    @discardableResult
    static func signIn() async throws -> User {
        guard let clientID = FirebaseApp.app()?.options.clientID else {
            throw Failure.notConfigured
        }
        guard let presenter = topViewController() else {
            throw Failure.noPresenter
        }

        GIDSignIn.sharedInstance.configuration = GIDConfiguration(clientID: clientID)

        let result: GIDSignInResult
        do {
            result = try await GIDSignIn.sharedInstance.signIn(withPresenting: presenter)
        } catch let error as NSError where error.code == GIDSignInError.canceled.rawValue {
            throw Failure.cancelled
        }

        guard let idToken = result.user.idToken?.tokenString else {
            throw Failure.missingIDToken
        }

        let credential = GoogleAuthProvider.credential(
            withIDToken: idToken,
            accessToken: result.user.accessToken.tokenString
        )
        return try await Auth.auth().signIn(with: credential).user
    }

    /// Sign out of both Google and Firebase.
    ///
    /// `Auth.auth()` traps when Firebase was never configured, so it is only
    /// touched once `FirebaseApp.app()` exists. Signing out of Google alone is
    /// always safe.
    static func signOut() {
        GIDSignIn.sharedInstance.signOut()
        guard FirebaseApp.app() != nil else { return }
        try? Auth.auth().signOut()
    }

    /// Handle the callback URL from the Google app or browser.
    @discardableResult
    static func handle(_ url: URL) -> Bool {
        GIDSignIn.sharedInstance.handle(url)
    }

    // MARK: - Helpers

    /// The view controller to present the Google sheet from.
    private static func topViewController() -> UIViewController? {
        let scene =
            UIApplication.shared.connectedScenes
            .compactMap { $0 as? UIWindowScene }
            .first { $0.activationState == .foregroundActive }
            ?? UIApplication.shared.connectedScenes.compactMap { $0 as? UIWindowScene }.first

        var controller = scene?.keyWindow?.rootViewController
        while let presented = controller?.presentedViewController {
            controller = presented
        }
        return controller
    }
}
