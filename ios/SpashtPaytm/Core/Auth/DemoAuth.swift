import Foundation

/// The dev-only demo session (build plan §13.2, §13.11).
///
/// Whole file is inside `#if DEBUG`, so a Release build contains no demo
/// identity, no key handling and no sign-in path — the binary simply has no
/// code for it. `Release.xcconfig` also blanks `DEMO_AUTH_KEY`, so there are two
/// independent reasons it cannot ship (decision D-032).
#if DEBUG

    enum DemoAuth {

        /// The identities the backend knows (`app/security/demo_auth.py`).
        enum Identity: String, CaseIterable {
            /// The golden-path customer.
            case sunita
            /// Dashboard operator. Used by the website, not the app.
            case demoAdmin = "demo-admin"

            var label: String {
                switch self {
                case .sunita: return "Sunita J. (customer)"
                case .demoAdmin: return "Demo admin"
                }
            }
        }

        /// `UserDefaults` key holding an active demo session across relaunches.
        static let sessionKey = "spasht.demoSession"

        /// Whether the demo button may be shown: Debug **and** a key is present.
        static var isAvailable: Bool { AppConfig.demoAuthKey != nil }

        /// The headers a demo request carries, or nil when unavailable.
        ///
        /// Both are required by the backend. Sending the user without the key
        /// gets a 401, which is the point.
        static func headers(for identity: Identity) -> (persona: String, key: String)? {
            guard let key = AppConfig.demoAuthKey else { return nil }
            return (persona: identity.rawValue, key: key)
        }

        /// Remember the demo session so a relaunch stays signed in.
        static func persist(_ identity: Identity?) {
            let defaults = UserDefaults.standard
            if let identity {
                defaults.set(identity.rawValue, forKey: sessionKey)
            } else {
                defaults.removeObject(forKey: sessionKey)
            }
        }

        /// The demo session left open by a previous launch, if any.
        static func restore() -> Identity? {
            guard
                isAvailable,
                let raw = UserDefaults.standard.string(forKey: sessionKey)
            else { return nil }
            return Identity(rawValue: raw)
        }
    }

#endif
