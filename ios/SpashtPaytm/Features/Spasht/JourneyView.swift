import SwiftUI

/// The conversation (build plan §5.6).
///
/// Header with the 6-step progress bar, the transcript, the server-driven card,
/// and the bottom bar with the mic, the keyboard toggle and the quick replies.
///
/// It renders what `JourneyViewModel` holds and sends back what the customer
/// did. Every decision - which card, whether the agree button is enabled, what
/// the chips say - was made by the backend (plan rule 10).
struct JourneyView: View {
    let auth: AuthService
    let language: Language

    /// A screen the caller already has, shown instead of starting a journey.
    /// Set by the rescue resume (phase 10); nil on the normal path.
    let resumed: TurnResponse?

    @Environment(\.dismiss) private var dismiss
    @State private var model: JourneyViewModel
    @State private var typing = false
    @State private var draft = ""
    @State private var showsOtp = false
    @State private var pdfUrl: String?
    @State private var muted = false
    @FocusState private var draftFocused: Bool

    // --- voice (phase 7) ---
    @State private var recorder = AudioRecorder()
    @State private var speech = SpeechPlayer()

    /// The last turn whose lines were spoken, so re-rendering the view does not
    /// play the same explanation twice.
    @State private var spokenTurn: String?

    init(auth: AuthService, language: Language, resumed: TurnResponse? = nil) {
        self.auth = auth
        self.language = language
        self.resumed = resumed
        _model = State(initialValue: JourneyViewModel(auth: auth))
    }

    var body: some View {
        ZStack {
            Theme.bg.ignoresSafeArea()

            VStack(spacing: 0) {
                JourneyHeader(
                    language: model.response?.language ?? language,
                    progress: model.progress,
                    muted: muted,
                    isDemoMode: model.isDemoMode,
                    onBack: { dismiss() },
                    onLanguage: { newLanguage in
                        Task { await model.send(action: .setLanguage(newLanguage)) }
                    },
                    onMute: {
                        muted.toggle()
                        speech.muted = muted
                    }
                )

                transcript

                // The microphone's own failures are shown here rather than as
                // an alert: §5.9 requires a typing alternative for every voice
                // action, and a modal would cover the keyboard button.
                if let failure = recorder.failure {
                    ErrorBar(message: failure.message) {
                        recorder.clearFailure()
                        typing = true
                        draftFocused = true
                    }
                } else if case .failed(let message) = model.phase {
                    ErrorBar(message: message) {
                        Task { await model.retry() }
                    }
                }

                bottomBar
            }
        }
        .navigationBarHidden(true)
        .task {
            // A rescue accept already carries the step the customer stopped on,
            // so adopt it rather than asking again (phase 10).
            if model.response == nil, let resumed {
                model.adopt(resumed)
                return
            }
            // Safe to call on every appearance: `POST /journeys` returns the
            // active journey rather than starting a second one (§8.2), which is
            // what makes relaunch-and-resume work with no extra code.
            await model.start(language: language)
        }
        // Speak whatever the backend just said, once per turn (§5.9).
        .onChange(of: model.response?.version) { _, _ in speakLatestTurn() }
        .onChange(of: model.transcript.count) { _, _ in speakLatestTurn() }
        // The 25 s ceiling stopped the recording; upload what was captured
        // rather than wait for a finger that never lifts (§10.1).
        .onChange(of: recorder.reachedLimit) { _, limited in
            guard limited else { return }
            recorder.clearLimit()
            sendRecording()
        }
        .onDisappear {
            recorder.cancel()
            speech.stop()
            speech.releaseSession()
        }
        .onChange(of: model.step) { _, step in
            // The OTP needs the keyboard and a focused field, so it is a sheet
            // rather than a card in the scroll view.
            showsOtp = step == "OTP"
        }
        .sheet(isPresented: $showsOtp) {
            if case .otp(let card) = model.card {
                OtpSheet(
                    language: model.language,
                    card: card,
                    demoCode: model.demoOtpCode,
                    isVerifying: model.phase == .working,
                    onVerify: { code in
                        Task {
                            await model.verifyOtp(code: code)
                            if model.isFinished { showsOtp = false }
                        }
                    },
                    onResend: { Task { _ = await model.sendOtp() } }
                )
                .interactiveDismissDisabled(model.phase == .working)
            }
        }
        .sheet(item: $pdfUrl) { url in
            KfsViewer(path: url)
        }
        .task(id: showsOtp) {
            // The code is requested when the sheet opens rather than when the
            // step is entered, so a customer who takes a while to tap "agree"
            // does not get an expired code.
            if showsOtp, model.demoOtpCode == nil {
                _ = await model.sendOtp()
            }
        }
    }

    // MARK: - Transcript

    private var transcript: some View {
        ScrollViewReader { proxy in
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 10) {
                    ForEach(model.transcript) { message in
                        MessageBubble(
                            message: message,
                            muted: muted,
                            onReplay: { speech.replay(path: message.audioUrl) }
                        )
                        .id(message.id)
                        .transition(.move(edge: .bottom).combined(with: .opacity))
                    }

                    if model.showsThinking {
                        ThinkingBubble().id("thinking")
                    }

                    if let card = model.card {
                        CardView(
                            card: card,
                            language: model.language,
                            acceptEnabled: model.acceptEnabled,
                            isSending: model.phase == .working,
                            onAction: { action in
                                Task { await model.send(action: action) }
                            },
                            onOpenPdf: { pdfUrl = $0 }
                        )
                        .id("card-\(model.step)-\(model.response?.version ?? 0)")
                        .transition(.scale(scale: 0.97).combined(with: .opacity))
                    }

                    if model.isFinished {
                        PrimaryButton(title: Strings.backToPaytm(model.language)) {
                            dismiss()
                        }
                        .padding(.top, 6)
                    }

                    Spacer(minLength: 10).id("bottom")
                }
                .padding(.horizontal, Metrics.screenPadding)
                .padding(.top, 12)
            }
            // §5.6: auto-scroll to the newest item.
            .onChange(of: model.transcript.count) {
                withAnimation(.easeOut(duration: 0.25)) {
                    proxy.scrollTo("bottom", anchor: .bottom)
                }
            }
            .onChange(of: model.step) {
                withAnimation(.easeOut(duration: 0.3)) {
                    proxy.scrollTo("bottom", anchor: .bottom)
                }
            }
            .animation(.easeOut(duration: 0.15), value: model.transcript.count)
        }
    }

    // MARK: - Bottom bar

    private var bottomBar: some View {
        VStack(spacing: 10) {
            if !model.quickReplies.isEmpty && model.acceptsInput {
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(spacing: 7) {
                        ForEach(model.quickReplies) { reply in
                            Button {
                                Task { await model.send(quickReply: reply) }
                            } label: {
                                Text(reply.label)
                                    .font(.system(size: 13, weight: .medium))
                                    .foregroundStyle(Theme.navy)
                                    .padding(.horizontal, 13)
                                    .padding(.vertical, 9)
                                    .background(.white, in: Capsule())
                                    .overlay(
                                        Capsule().strokeBorder(Theme.navy.opacity(0.25), lineWidth: 1)
                                    )
                            }
                            .buttonStyle(.plain)
                        }
                    }
                    .padding(.horizontal, Metrics.screenPadding)
                }
                .frame(height: 40)
            }

            HStack(spacing: 12) {
                if typing {
                    TextField(typeHint, text: $draft, axis: .vertical)
                        .font(.system(size: 15))
                        .lineLimit(1...4)
                        .focused($draftFocused)
                        .padding(.horizontal, 15)
                        .padding(.vertical, 11)
                        .background(.white, in: Capsule())
                        .overlay(Capsule().strokeBorder(Theme.hairline, lineWidth: 1))
                        .onSubmit(sendDraft)

                    Button(action: sendDraft) {
                        Image(systemName: "arrow.up")
                            .font(.system(size: 17, weight: .bold))
                            .foregroundStyle(.white)
                            .frame(width: 46, height: 46)
                            .background(Theme.navy, in: Circle())
                    }
                    .buttonStyle(.plain)
                    .disabled(draft.trimmingCharacters(in: .whitespaces).isEmpty)
                } else {
                    Spacer()
                    MicButton(
                        enabled: model.acceptsInput && !recorder.isDenied,
                        isRecording: recorder.isRecording,
                        level: recorder.level,
                        deniedHint: recorder.isDenied,
                        onStart: { Task { await recorder.start() } },
                        onStop: sendRecording
                    )
                    Spacer()
                }

                Button {
                    typing.toggle()
                    draftFocused = typing
                } label: {
                    Image(systemName: typing ? "mic" : "keyboard")
                        .font(.system(size: 18, weight: .medium))
                        .foregroundStyle(Theme.navy)
                        .frame(width: Metrics.minimumTapTarget, height: Metrics.minimumTapTarget)
                }
                .buttonStyle(.plain)
                // §5.6 and plan rule 9: every voice action has a typing
                // alternative, so this toggle is never hidden or disabled.
                .accessibilityLabel(typing ? "Use the microphone" : "Type instead")
            }
            .padding(.horizontal, Metrics.screenPadding)
            .padding(.bottom, 8)
        }
        .background(Theme.bg)
        .animation(.easeInOut(duration: 0.2), value: typing)
    }

    /// Stop recording and send the clip, or show why there is nothing to send.
    private func sendRecording() {
        Task {
            guard let data = await recorder.stop() else { return }
            // The phone's own detection, so a customer who switched language
            // mid-journey is still transcribed in the language they spoke.
            await model.send(voice: data, languageHint: model.language)
        }
    }

    /// Play the assistant's lines for the current turn, in order, once.
    ///
    /// Keyed on the turn rather than on the message list, because the list is
    /// the running total: re-speaking on every append would replay the whole
    /// conversation after each turn.
    private func speakLatestTurn() {
        guard !muted, let response = model.response else { return }

        let key = "\(response.journeyId):\(response.version)"
        guard key != spokenTurn else { return }
        spokenTurn = key

        speech.play(paths: response.messages.filter { $0.role == .assistant }.map(\.audioUrl))
    }

    private func sendDraft() {
        let text = draft
        draft = ""
        Task { await model.send(text: text) }
    }

    private var typeHint: String {
        switch model.language {
        case .marathi: return "टाइप करा…"
        case .hindi: return "टाइप कीजिए…"
        case .english: return "Type here…"
        }
    }
}

// MARK: - Header

private struct JourneyHeader: View {
    let language: Language
    let progress: TurnResponse.Progress?
    let muted: Bool
    let isDemoMode: Bool
    let onBack: () -> Void
    let onLanguage: (Language) -> Void
    let onMute: () -> Void

    var body: some View {
        VStack(spacing: 9) {
            HStack(spacing: 6) {
                Button(action: onBack) {
                    Image(systemName: "chevron.left")
                        .font(.system(size: 17, weight: .semibold))
                        .foregroundStyle(Theme.text1)
                        .frame(width: Metrics.minimumTapTarget, height: Metrics.minimumTapTarget)
                }
                .buttonStyle(.plain)
                .accessibilityLabel("Back")

                VStack(alignment: .leading, spacing: 0) {
                    Text("Spasht")
                        .font(.system(size: 17, weight: .bold))
                        .foregroundStyle(Theme.text1)
                    Text("in Paytm (concept)")
                        .font(.system(size: 9.5))
                        .foregroundStyle(Theme.text3)
                }

                Spacer()

                if isDemoMode {
                    Text("Demo mode")
                        .font(.system(size: 9, weight: .heavy))
                        .foregroundStyle(Theme.text1)
                        .padding(.horizontal, 7)
                        .padding(.vertical, 3)
                        .background(Theme.badgeNew, in: Capsule())
                }

                // Muting silences the voice; the captions stay (§5.9), so
                // nothing is ever only available as audio.
                Button(action: onMute) {
                    Image(systemName: muted ? "speaker.slash.fill" : "speaker.wave.2.fill")
                        .font(.system(size: 14))
                        .foregroundStyle(muted ? Theme.danger : Theme.navy)
                        .frame(width: Metrics.minimumTapTarget, height: Metrics.minimumTapTarget)
                }
                .buttonStyle(.plain)
                .accessibilityLabel(muted ? "Unmute Spasht" : "Mute Spasht")

                Menu {
                    ForEach(Language.allCases, id: \.self) { option in
                        Button(option.nativeName) { onLanguage(option) }
                    }
                } label: {
                    HStack(spacing: 3) {
                        Text(language.nativeName)
                            .font(.system(size: 13, weight: .semibold))
                        Image(systemName: "chevron.down")
                            .font(.system(size: 9, weight: .bold))
                    }
                    .foregroundStyle(Theme.navy)
                    .padding(.horizontal, 10)
                    .padding(.vertical, 7)
                    .background(.white, in: Capsule())
                }
            }
            .padding(.horizontal, 6)

            StepProgress(progress: progress)
                .padding(.horizontal, Metrics.screenPadding)
        }
        .padding(.vertical, 6)
        .background(Theme.bg)
    }
}

/// The 6-step progress bar with the remaining-time estimate (§5.6).
private struct StepProgress: View {
    let progress: TurnResponse.Progress?

    private let stageCount = 6

    var body: some View {
        VStack(spacing: 5) {
            HStack(spacing: 4) {
                ForEach(0..<stageCount, id: \.self) { index in
                    Capsule()
                        .fill(index <= (progress?.index ?? 0) ? Theme.sky : Theme.hairline)
                        .frame(height: 4)
                }
            }

            HStack {
                Text(progress?.label ?? "")
                    .font(.system(size: 10.5, weight: .semibold))
                    .foregroundStyle(Theme.text2)
                Spacer()
                if let eta = progress?.etaSeconds, eta > 0 {
                    Text("≈ \(max(1, eta / 60)) min left")
                        .font(.system(size: 10))
                        .foregroundStyle(Theme.text3)
                }
            }
        }
        .animation(.easeInOut(duration: 0.3), value: progress?.index)
    }
}

// MARK: - Bubbles

private struct MessageBubble: View {
    let message: TurnMessage
    let muted: Bool
    let onReplay: () -> Void

    var body: some View {
        HStack {
            if message.role == .user { Spacer(minLength: 44) }

            HStack(alignment: .bottom, spacing: 6) {
                Text(message.text)
                    .font(.system(size: 15))
                    .foregroundStyle(message.role == .user ? .white : Theme.text1)
                    .fixedSize(horizontal: false, vertical: true)

                if message.role == .assistant, message.audioUrl != nil, !muted {
                    Button(action: onReplay) {
                        Image(systemName: "speaker.wave.2")
                            .font(.system(size: 11))
                            .foregroundStyle(Theme.text3)
                    }
                    .buttonStyle(.plain)
                    .accessibilityLabel("Play again")
                }
            }
            .padding(.horizontal, 14)
            .padding(.vertical, 11)
            .background(
                message.role == .user ? Theme.navy : Theme.card,
                in: RoundedRectangle(cornerRadius: 18, style: .continuous)
            )
            .overlay(
                RoundedRectangle(cornerRadius: 18, style: .continuous)
                    .strokeBorder(
                        message.role == .user ? .clear : Theme.hairline,
                        lineWidth: 1
                    )
            )

            if message.role == .assistant { Spacer(minLength: 44) }
        }
    }
}

/// The three-dot `Thinking…` indicator (§5.6).
private struct ThinkingBubble: View {
    @State private var phase = 0

    var body: some View {
        HStack(spacing: 5) {
            ForEach(0..<3, id: \.self) { index in
                Circle()
                    .fill(Theme.text3)
                    .frame(width: 7, height: 7)
                    .opacity(phase == index ? 1 : 0.3)
            }
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 13)
        .background(Theme.card, in: Capsule())
        .overlay(Capsule().strokeBorder(Theme.hairline, lineWidth: 1))
        .task {
            while !Task.isCancelled {
                try? await Task.sleep(for: .milliseconds(320))
                phase = (phase + 1) % 3
            }
        }
        .accessibilityLabel("Thinking")
    }
}

/// A failed turn, with the retry that reuses the same `clientTurnId`.
private struct ErrorBar: View {
    let message: String
    let onRetry: () -> Void

    var body: some View {
        HStack(spacing: 10) {
            Image(systemName: "exclamationmark.triangle.fill")
                .font(.system(size: 14))
                .foregroundStyle(Theme.danger)
            Text(message)
                .font(.system(size: 12))
                .foregroundStyle(Theme.text2)
                .fixedSize(horizontal: false, vertical: true)
            Spacer(minLength: 4)
            Button("Retry", action: onRetry)
                .font(.system(size: 13, weight: .bold))
                .foregroundStyle(Theme.navy)
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 11)
        .background(Theme.alertPink)
        .padding(.horizontal, Metrics.screenPadding)
        .padding(.bottom, 6)
    }
}
