import AVFoundation
import Foundation

/// Plays one cached line of backend-synthesised speech (build plan §10.2).
///
/// Built for the rescue call: Accept has to *say* "your application is
/// incomplete, shall we continue?" before the journey screen appears.
///
/// Two decisions worth naming.
///
/// **The bytes come through `APIClient`, not through `AVPlayer`'s own
/// fetching.** The audio route is public (the HMAC key is the capability), but
/// the tunnel is not: without the `ngrok-skip-browser-warning` header ngrok
/// serves its HTML interstitial, and `AVPlayer` would fail on it silently.
///
/// **A failure is not reported to the customer.** The caption is on screen
/// either way, so a dead speaker or an empty cache means a quiet call rather
/// than an error anyone could act on.
@MainActor
final class CallAudioPlayer {

    private let client: APIClient
    private var player: AVAudioPlayer?

    init(client: APIClient = .shared) {
        self.client = client
    }

    /// Fetch and play `path` (e.g. `/api/audio/<key>.mp3`). Returns when the
    /// playback has *started*, not when it has finished.
    func play(path: String?) async {
        guard let path, !path.isEmpty else { return }

        do {
            let data = try await client.data(path)
            try activateSession()

            let player = try AVAudioPlayer(data: data)
            player.prepareToPlay()
            player.play()
            // Held so it is not deallocated mid-sentence, which is what
            // happens when the player is a local in the calling scope.
            self.player = player
        } catch {
            // Deliberately quiet: see the type comment.
            return
        }
    }

    func stop() {
        player?.stop()
        player = nil
    }

    /// `.playback` so the line is audible with the ringer switch on silent.
    ///
    /// A simulated phone call that says nothing because somebody's phone was on
    /// silent is a demo that looks broken rather than one that looks polite.
    private func activateSession() throws {
        let session = AVAudioSession.sharedInstance()
        try session.setCategory(.playback, mode: .spokenAudio, options: [.duckOthers])
        try session.setActive(true)
    }
}
