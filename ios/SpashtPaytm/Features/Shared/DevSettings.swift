import SwiftUI

/// Dev settings, Debug builds only (build plan §5.10).
///
/// Wrapped in `#if DEBUG` so none of it - not the view, not the canned
/// transcripts, not the API override - is compiled into a Release build. That
/// is checked in phase 1's acceptance criteria by inspecting the built binary.
///
/// The API override earns its place: an ngrok URL can change between a
/// rehearsal and the real demo, and re-editing an xcconfig and rebuilding on
/// stage is not a plan.

/// Long-press target in the drawer footer that opens Dev settings.
struct DevSettingsTrigger: View {
    #if DEBUG
        @State private var showsDevSettings = false
    #endif

    var body: some View {
        #if DEBUG
            Wordmark(size: 17, showsPill: false, colour: Theme.text3)
                .onLongPressGesture(minimumDuration: 0.8) {
                    showsDevSettings = true
                }
                .sheet(isPresented: $showsDevSettings) {
                    DevSettingsView()
                }
        #else
            // Release: the same wordmark, with nothing behind it.
            Wordmark(size: 17, showsPill: false, colour: Theme.text3)
        #endif
    }
}

#if DEBUG

    struct DevSettingsView: View {
        @Environment(\.dismiss) private var dismiss

        @State private var apiBaseURL = AppConfig.overriddenAPIBaseURL?.absoluteString ?? ""
        @State private var saved = false

        var body: some View {
            NavigationStack {
                Form {
                    Section("API base URL") {
                        TextField("https://your-domain.ngrok-free.app", text: $apiBaseURL)
                            .textInputAutocapitalization(.never)
                            .autocorrectionDisabled()
                            .keyboardType(.URL)
                            .font(.system(size: 13, design: .monospaced))

                        Text("Overrides the compiled-in value. Leave empty to use \(AppConfig.compiledAPIBaseURL.absoluteString).")
                            .font(.caption2)
                            .foregroundStyle(Theme.text3)

                        Button("Save and use") {
                            AppConfig.setAPIBaseURLOverride(apiBaseURL)
                            saved = true
                        }
                        Button("Clear override", role: .destructive) {
                            AppConfig.setAPIBaseURLOverride(nil)
                            apiBaseURL = ""
                            saved = true
                        }
                    }

                    Section("Status") {
                        LabeledContent("Effective API", value: AppConfig.apiBaseURL.absoluteString)
                        LabeledContent("Public base", value: AppConfig.publicBaseURL.absoluteString)
                        LabeledContent("App version", value: AppConfig.appVersion)
                        LabeledContent(
                            "Google sign-in",
                            value: AppConfig.isGoogleSignInConfigured ? "configured" : "not configured"
                        )
                        LabeledContent(
                            "Demo login",
                            value: AppConfig.isDemoLoginAvailable ? "available" : "no key"
                        )
                    }

                    Section("Canned transcripts") {
                        Text("Picked from the mic button in the journey, when demo mode is on (§10.6).")
                            .font(.caption2)
                            .foregroundStyle(Theme.text3)
                        ForEach(CannedTranscripts.all) { canned in
                            VStack(alignment: .leading, spacing: 2) {
                                Text(canned.step)
                                    .font(.caption2.weight(.semibold))
                                    .foregroundStyle(Theme.text3)
                                Text(canned.text)
                                    .font(.system(size: 12))
                            }
                        }
                    }

                    Section {
                        Text("These settings exist only in Debug builds.")
                            .font(.caption2)
                            .foregroundStyle(Theme.text3)
                    }
                }
                .navigationTitle("Dev settings")
                .toolbar {
                    ToolbarItem(placement: .confirmationAction) {
                        Button("Done") { dismiss() }
                    }
                }
                .alert("Saved", isPresented: $saved) {
                    Button("OK") {}
                } message: {
                    Text("The next request uses the new URL.")
                }
            }
        }
    }

    /// Golden-path utterances for the canned-transcript picker (§10.6).
    ///
    /// Used when the Sarvam key is absent or the venue network is down: the
    /// picker sends the utterance as a text turn so the demo still completes by
    /// "voice" with no speech recognition at all.
    enum CannedTranscripts {
        struct Canned: Identifiable {
            let id = UUID()
            let step: String
            let text: String
            let language: Language
        }

        static let all: [Canned] = [
            Canned(step: "ASK_NEED", text: "मला ५० हजारांचं कर्ज शिलाई मशीनसाठी हवं आहे", language: .marathi),
            Canned(step: "CONSENT_DATA", text: "हो, चालेल", language: .marathi),
            Canned(step: "CONFIRM_DETAILS", text: "हो, बरोबर आहे", language: .marathi),
            Canned(step: "OFFERS", text: "सगळ्यात स्वस्त", language: .marathi),
            Canned(step: "TEACHBACK q1", text: "लेट फी लागेल आणि सिबिल स्कोर कमी होईल", language: .marathi),
            Canned(step: "TEACHBACK q2", text: "एकूण ५५,२०० परत करावे लागतील", language: .marathi),
            Canned(step: "TEACHBACK q3", text: "नाही, विमा ऐच्छिक आहे", language: .marathi),
            Canned(step: "any", text: "समजलं नाही", language: .marathi),
            Canned(step: "any", text: "माणसाशी बोलायचं", language: .marathi),
        ]

        /// The canned lines for one language, for the journey's picker.
        static func forLanguage(_ language: Language) -> [Canned] {
            all.filter { $0.language == language }
        }
    }

#endif
