import SwiftUI

/// The mic button (build plan §5.6, §5.9).
///
/// Phase 7 wires it to the recorder. Until then it is visible but disabled with
/// an explanatory caption, because hiding it would make the journey look
/// typing-only and the voice loop is the point of the product.
///
/// It supports both press-and-hold and tap-to-toggle. Hold is what people do
/// instinctively; tap-to-toggle is what someone with a tremor or an unsteady
/// grip can actually use, and a voice product that only works if you can hold
/// a button steady for ten seconds has missed its own audience.
struct MicButton: View {
    let enabled: Bool
    var isRecording = false
    var level: CGFloat = 0
    var onStart: (() -> Void)?
    var onStop: (() -> Void)?

    @State private var pulsing = false

    var body: some View {
        VStack(spacing: 7) {
            ZStack {
                if isRecording {
                    ForEach([1.0, 1.3, 1.6], id: \.self) { scale in
                        Circle()
                            .strokeBorder(Theme.sky.opacity(pulsing ? 0.06 : 0.4), lineWidth: 2)
                            .frame(
                                width: Metrics.micButton * scale,
                                height: Metrics.micButton * scale
                            )
                    }
                }

                Circle()
                    .fill(enabled ? Theme.navy : Theme.text3.opacity(0.35))
                    .frame(width: Metrics.micButton, height: Metrics.micButton)
                    // Grows slightly with the input level, so the button itself
                    // confirms it is hearing something.
                    .scaleEffect(isRecording ? 1 + min(0.12, level * 0.12) : 1)

                Image(systemName: isRecording ? "waveform" : "mic.fill")
                    .font(.system(size: 25, weight: .medium))
                    .foregroundStyle(.white)
            }
            .animation(
                .easeInOut(duration: 1.1).repeatForever(autoreverses: false),
                value: pulsing
            )
            .animation(.easeOut(duration: 0.12), value: level)
            .contentShape(Circle())
            .onLongPressGesture(
                minimumDuration: .infinity,
                pressing: { pressing in
                    guard enabled else { return }
                    if pressing {
                        onStart?()
                    } else if isRecording {
                        onStop?()
                    }
                },
                perform: {}
            )
            .onTapGesture {
                guard enabled else { return }
                if isRecording { onStop?() } else { onStart?() }
            }
            .onChange(of: isRecording) { _, recording in
                pulsing = recording
            }
            .accessibilityLabel(isRecording ? "Stop recording" : "Hold to speak")
            .accessibilityHint(enabled ? "" : "Voice arrives in a later phase. Use the keyboard instead.")

            if !enabled {
                Text("Voice comes in Phase 7")
                    .font(.system(size: 10))
                    .foregroundStyle(Theme.text3)
            }
        }
    }
}
