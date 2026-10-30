import Foundation

/// Everything the app needs to know about its environment (build plan §14.3).
///
/// Values come from the Info.plist, which is filled from `ios/Config/*.xcconfig`
/// at build time. Nothing here is hard-coded, so pointing the app at the ngrok
/// tunnel is an xcconfig edit and a rebuild, not a code change.
///
/// In Debug the API base URL can be overridden at runtime from Dev settings,
/// which matters because an ngrok URL can change between a rehearsal and the
/// real demo. Release always uses the compiled-in value.
enum AppConfig {

    // MARK: - Info.plist keys

    private enum Key {
        static let apiBaseURL = "APIBaseURL"
        static let publicBaseURL = "PublicBaseURL"
        static let demoAuthKey = "DemoAuthKey"
    }

    /// `UserDefaults` key for the Debug-only API override.
    static let apiBaseURLOverrideKey = "spasht.devSettings.apiBaseURL"

    // MARK: - Values

    /// Where the backend lives. Dev settings win in Debug; Info.plist otherwise.
    static var apiBaseURL: URL {
        #if DEBUG
            if let override = overriddenAPIBaseURL {
                return override
            }
        #endif
        return plistURL(for: Key.apiBaseURL) ?? fallbackURL
    }

    /// The origin receipt QR codes point at. Only used for display in the app;
    /// the backend builds the real links so they cannot be spoofed by a client.
    static var publicBaseURL: URL {
        plistURL(for: Key.publicBaseURL) ?? fallbackURL
    }

    /// The shared secret for the dev demo login (§13.2).
    ///
    /// Release builds have this blank because `Release.xcconfig` wipes
    /// `DEMO_AUTH_KEY`, so `isDemoLoginAvailable` is false there even if the
    /// `#if DEBUG` guards were somehow removed. Two independent reasons the
    /// demo login cannot ship.
    static var demoAuthKey: String? {
        guard let raw = Bundle.main.object(forInfoDictionaryKey: Key.demoAuthKey) as? String else {
            return nil
        }
        let trimmed = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        return trimmed.isEmpty ? nil : trimmed
    }

    /// Whether to offer "Continue as demo user" on the login screen (§5.5).
    static var isDemoLoginAvailable: Bool {
        #if DEBUG
            return demoAuthKey != nil
        #else
            return false
        #endif
    }

    /// The Google sign-in URL scheme, present only once `make ios-config` has run.
    static var isGoogleSignInConfigured: Bool {
        googleServiceInfoPath != nil
    }

    /// Path to `GoogleService-Info.plist`, or nil when the human has not added it.
    ///
    /// `FirebaseApp.configure()` traps on a missing file, so the app must ask
    /// before configuring rather than crash on launch in a fresh clone.
    static var googleServiceInfoPath: String? {
        Bundle.main.path(forResource: "GoogleService-Info", ofType: "plist")
    }

    /// Marketing version, shown in Dev settings and sent as the app version on
    /// receipts (§11.1).
    static var appVersion: String {
        let version =
            Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String
        return "spasht-ios-\(version ?? "0.0.0")"
    }

    // MARK: - Debug override

    #if DEBUG
        /// The Dev-settings API override, if one is set and parses.
        static var overriddenAPIBaseURL: URL? {
            guard
                let raw = UserDefaults.standard.string(forKey: apiBaseURLOverrideKey),
                !raw.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
            else {
                return nil
            }
            return URL(string: raw)
        }

        /// Set or clear the Dev-settings override. Pass nil to fall back to the plist.
        static func setAPIBaseURLOverride(_ value: String?) {
            let defaults = UserDefaults.standard
            guard let value, !value.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
                defaults.removeObject(forKey: apiBaseURLOverrideKey)
                return
            }
            defaults.set(value, forKey: apiBaseURLOverrideKey)
        }
    #endif

    // MARK: - Helpers

    /// Last resort if the plist is missing or malformed. The Simulator default,
    /// so a misconfigured build fails visibly on a phone rather than silently
    /// talking to the wrong place.
    private static let fallbackURL = URL(string: "http://localhost:8000")!

    private static func plistURL(for key: String) -> URL? {
        guard
            let raw = Bundle.main.object(forInfoDictionaryKey: key) as? String
        else { return nil }

        let trimmed = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty, let url = URL(string: trimmed), url.scheme != nil else {
            return nil
        }
        return url
    }
}
