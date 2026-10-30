import AVFoundation
import Foundation
import Observation

/// Recording a voice turn (build plan §5.9, §10.1, §13.11).
///
/// Records AAC in an m4a container, which is what `detect_format` on the
/// backend accepts (`ftyp` magic bytes) and what the phone encodes in hardware.
/// 16 kHz mono: speech-to-text does not benefit from more, and a clip four
/// times the size is four times the upload over venue Wi-Fi.
///
/// **Every failure has a typed reason and a typed fallback.** The product rule
/// is that voice is never the only way to do anything (§5.9), so a denied
/// microphone is not an error state - it is a sentence telling the customer to
/// use the keyboard, which is already on screen.
///
/// **Nothing is kept.** The clip is handed to the caller as `Data`, the
/// temporary file is deleted immediately, and no recording is ever written
/// where a backup could pick it up (§13.11).
@Observable
@MainActor
final class AudioRecorder: NSObject {

    enum Failure: Equatable {
        /// The customer said no, or Settings says no. Not retryable here.
        case permissionDenied
        /// The session or the encoder failed. Retryable.
        case unavailable
        /// Nothing audible was captured - a tap rather than a hold.
        case tooShort

        var message: String {
            switch self {
            case .permissionDenied:
                return "Microphone access is off, so voice is unavailable. Type instead — the keyboard button is beside the mic."
            case .unavailable:
                return "The microphone could not start. Please type, or try again."
            case .tooShort:
                return "That was too short to hear. Hold the mic while you speak, or type instead."
            }
        }
    }

    /// True while recording. Drives the mic button's pulse.
    private(set) var isRecording = false

    /// 0-1, smoothed. The button grows with it, so the customer can see that
    /// the phone is hearing them - which is the only feedback a voice-first
    /// screen can give before the transcript arrives.
    private(set) var level: CGFloat = 0

    /// The last failure, for the UI to show and clear.
    private(set) var failure: Failure?

    /// Set when the 25 s ceiling stopped the recording, so the view can upload
    /// what it has instead of waiting for a finger that never lifts.
    private(set) var reachedLimit = false

    /// True once the customer has denied the microphone, so the UI can stop
    /// offering it and show the keyboard instead.
    private(set) var isDenied = false

    /// §10.1: clips are 25 s or shorter. Enforced here as well as on the
    /// backend, because the customer who is still talking at 25 s should get
    /// their first 25 s transcribed rather than a 413.
    static let maxDuration: TimeInterval = 25

    /// Below this there is nothing to transcribe and a paid call would be
    /// wasted on silence.
    private static let minDuration: TimeInterval = 0.4

    private var recorder: AVAudioRecorder?
    private var url: URL?
    private var startedAt: Date?
    private var meter: Task<Void, Never>?
    private var autoStop: Task<Void, Never>?

    // MARK: - Permission

    /// Whether the microphone may be used, asking once if it has not been asked.
    func requestPermission() async -> Bool {
        switch AVAudioApplication.shared.recordPermission {
        case .granted:
            return true
        case .denied:
            isDenied = true
            failure = .permissionDenied
            return false
        case .undetermined:
            // The SDK exposes only the completion-handler form, so it is
            // bridged here rather than at every call site.
            let granted = await withCheckedContinuation { continuation in
                AVAudioApplication.requestRecordPermission { granted in
                    continuation.resume(returning: granted)
                }
            }
            if !granted {
                isDenied = true
                failure = .permissionDenied
            }
            return granted
        @unknown default:
            return false
        }
    }

    // MARK: - Recording

    func clearFailure() {
        failure = nil
    }

    /// Start recording. Safe to call twice; the second call is ignored.
    func start() async {
        guard !isRecording else { return }
        failure = nil

        guard await requestPermission() else { return }

        let target = FileManager.default.temporaryDirectory
            .appendingPathComponent("spasht-turn-\(UUID().uuidString).m4a")

        let settings: [String: Any] = [
            AVFormatIDKey: Int(kAudioFormatMPEG4AAC),
            AVSampleRateKey: 16_000,
            AVNumberOfChannelsKey: 1,
            AVEncoderAudioQualityKey: AVAudioQuality.medium.rawValue,
        ]

        do {
            let session = AVAudioSession.sharedInstance()
            // `.playAndRecord` rather than `.record`: the assistant speaks
            // immediately after the turn, and switching categories between the
            // two inserts a gap long enough to look like a hang.
            try session.setCategory(.playAndRecord, mode: .spokenAudio, options: [.duckOthers])
            try session.setActive(true)

            let recorder = try AVAudioRecorder(url: target, settings: settings)
            recorder.delegate = self
            recorder.isMeteringEnabled = true
            guard recorder.record() else {
                failure = .unavailable
                return
            }

            self.recorder = recorder
            self.url = target
            startedAt = Date()
            isRecording = true
            level = 0

            startMetering()
            startAutoStop()
        } catch {
            failure = .unavailable
            isRecording = false
        }
    }

    /// Stop recording and return the clip, or nil with `failure` set.
    func stop() async -> Data? {
        guard let recorder, let url else { return nil }

        meter?.cancel()
        autoStop?.cancel()
        meter = nil
        autoStop = nil

        let duration = Date().timeIntervalSince(startedAt ?? Date())
        recorder.stop()

        self.recorder = nil
        self.url = nil
        startedAt = nil
        isRecording = false
        level = 0

        defer { try? FileManager.default.removeItem(at: url) }

        guard duration >= Self.minDuration else {
            failure = .tooShort
            return nil
        }

        guard let data = try? Data(contentsOf: url), data.count > 1024 else {
            failure = .tooShort
            return nil
        }

        return data
    }

    /// Abandon the recording without uploading it.
    func cancel() {
        meter?.cancel()
        autoStop?.cancel()
        recorder?.stop()
        if let url { try? FileManager.default.removeItem(at: url) }
        recorder = nil
        url = nil
        startedAt = nil
        isRecording = false
        level = 0
    }

    private func startMetering() {
        meter = Task { [weak self] in
            while !Task.isCancelled {
                try? await Task.sleep(for: .milliseconds(80))
                guard let self, let recorder = self.recorder else { return }
                recorder.updateMeters()
                // dBFS, roughly -60 (silence) to 0 (clipping), mapped to 0-1
                // and smoothed so the button breathes rather than flickers.
                let power = Double(recorder.averagePower(forChannel: 0))
                let normalised = max(0, min(1, (power + 50) / 50))
                self.level = self.level * 0.6 + CGFloat(normalised) * 0.4
            }
        }
    }

    private func startAutoStop() {
        autoStop = Task { [weak self] in
            try? await Task.sleep(for: .seconds(Self.maxDuration))
            guard !Task.isCancelled, let self, self.isRecording else { return }
            // The caller's `onStop` is not invoked: the view observes
            // `isRecording` and sends what was captured.
            self.reachedLimit = true
        }
    }

    func clearLimit() {
        reachedLimit = false
    }
}

extension AudioRecorder: AVAudioRecorderDelegate {
    nonisolated func audioRecorderEncodeErrorDidOccur(_ recorder: AVAudioRecorder, error: Error?) {
        Task { @MainActor [weak self] in
            self?.cancel()
            self?.failure = .unavailable
        }
    }
}
