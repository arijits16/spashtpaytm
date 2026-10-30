import SwiftUI

/// A brief confirmation, e.g. after copying the UPI ID (build plan §5.4).
struct Toast: View {
    let message: String

    var body: some View {
        Text(message)
            .font(.system(size: 13, weight: .semibold))
            .foregroundStyle(.white)
            .padding(.horizontal, 18)
            .padding(.vertical, 11)
            .background(Theme.text1.opacity(0.92), in: Capsule())
            .shadow(color: .black.opacity(0.15), radius: 8, y: 3)
            // Announced rather than focusable: a toast that steals VoiceOver
            // focus interrupts whatever the user was reading.
            .accessibilityHidden(true)
    }
}

extension View {
    /// Show `message` for a couple of seconds, then clear it.
    ///
    /// The binding is cleared by this modifier rather than by the caller, so a
    /// toast cannot be left on screen by a view that forgot to dismiss it.
    func toast(_ message: Binding<String?>) -> some View {
        overlay(alignment: .bottom) {
            if let text = message.wrappedValue {
                Toast(message: text)
                    .padding(.bottom, 44)
                    .transition(.move(edge: .bottom).combined(with: .opacity))
                    .task {
                        try? await Task.sleep(for: .seconds(2))
                        message.wrappedValue = nil
                    }
            }
        }
        .animation(.easeInOut(duration: 0.2), value: message.wrappedValue)
    }
}
