import AVFoundation
import Foundation
import Observation

/// Plays the backend's synthesised speech (build plan §5.9, §10.2).
///
/// One player for the whole app: the journey's assistant lines and the rescue
/// call's one line. Two decisions worth naming.
///
/// **The bytes come through `APIClient`, not through `AVPlayer`'s own
/// fetching.** The audio route is public — the HMAC key in the URL *is* the
/// capability (§8.2) — but the tunnel is not: without the
/// `ngrok-skip-browser-warning` header ngrok serves its HTML interstitial, and
/// `AVPlayer` fails on it silently.
///
/// **Lines queue rather than interrupt.** A turn can carry three explanation
/// lines (§9 EXPLAIN_KFS); playing them concurrently is noise, and playing only
/// the last one would drop two thirds of the explanation.
///
/// A failure is never shown to the customer. The caption is on screen either
/// way, so an empty cache or a silenced phone means a quiet turn rather than an
/// error nobody can act on (§10.6).
@Observable
@MainActor
final class SpeechPlayer: NSObject {

    /// True while something is playing, so the UI can show a speaker animating.
    private(set) var isSpeaking = false

    /// Set when the customer mutes. Muting stops the current line immediately:
    /// a mute button that lets the current sentence finish is a mute button
    /// people press twice.
    var muted = false {
        didSet { if muted { stop() } }
    }

    private let client: APIClient
    private var player: AVAudioPlayer?

    /// Paths still to play, oldest first.
    private var queue: [String] = []

    /// Bytes already fetched, keyed by path. The cache URLs are immutable (the
    /// key is a hash of the text), so a replayed line costs nothing and the
    /// three explanation lines replay instantly.
    private var cache: [String: Data] = [:]

    private var isSessionActive = false

    init(client: APIClient = .shared) {
        self.client = client
        super.init()
    }

    // MARK: - Playing

    /// Queue one line. Starts playback if nothing is playing.
    func play(path: String?) {
        guard let path, !path.isEmpty, !muted else { return }
        queue.append(path)
        if !isSpeaking { advance() }
    }

    /// Queue several lines, in order.
    func play(paths: [String?]) {
        for path in paths { play(path: path) }
    }

    /// Replay one line now, discarding whatever was queued behind it.
    func replay(path: String?) {
        guard let path, !path.isEmpty else { return }
        stop()
        muted = false
        queue = [path]
        advance()
    }

    func stop() {
        player?.stop()
        player = nil
        queue.removeAll()
        isSpeaking = false
    }

    private func advance() {
        guard !muted, !queue.isEmpty else {
            isSpeaking = false
            return
        }

        let path = queue.removeFirst()
        isSpeaking = true

        Task { [weak self] in
            guard let self else { return }
            await self.start(path: path)
        }
    }

    private func start(path: String) async {
        do {
            let data: Data
            if let cached = cache[path] {
                data = cached
            } else {
                data = try await client.data(path)
                cache[path] = data
            }

            guard !muted else {
                isSpeaking = false
                return
            }

            try activateSession()
            let player = try AVAudioPlayer(data: data)
            player.delegate = self
            player.prepareToPlay()
            player.play()
            // Held so it is not deallocated mid-sentence, which is what happens
            // when the player is a local in the calling scope.
            self.player = player
        } catch {
            // Deliberately quiet: see the type comment. Move on to the next
            // line rather than stalling the queue on one missing file.
            advance()
        }
    }

    /// `.playback` so the assistant is audible with the ringer switch on silent.
    ///
    /// A voice-first product that says nothing because somebody's phone was on
    /// silent looks broken rather than polite. Activated once and left active:
    /// re-activating between the three explanation lines inserts an audible gap.
    private func activateSession() throws {
        guard !isSessionActive else { return }
        let session = AVAudioSession.sharedInstance()
        try session.setCategory(.playback, mode: .spokenAudio, options: [.duckOthers])
        try session.setActive(true)
        isSessionActive = true
    }

    /// Give the microphone the session back (§10.1: record, then speak).
    func releaseSession() {
        guard isSessionActive else { return }
        try? AVAudioSession.sharedInstance().setActive(false, options: [.notifyOthersOnDeactivation])
        isSessionActive = false
    }
}

extension SpeechPlayer: AVAudioPlayerDelegate {
    nonisolated func audioPlayerDidFinishPlaying(_ player: AVAudioPlayer, successfully flag: Bool) {
        Task { @MainActor [weak self] in
            self?.player = nil
            self?.advance()
        }
    }

    nonisolated func audioPlayerDecodeErrorDidOccur(_ player: AVAudioPlayer, error: Error?) {
        Task { @MainActor [weak self] in
            self?.player = nil
            self?.advance()
        }
    }
}
