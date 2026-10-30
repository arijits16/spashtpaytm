import SwiftUI

/// Temporary first screen (build plan phase 0, step 5).
///
/// Its whole job is to prove the chain works end to end —
/// app → URLSession → (tunnel) → FastAPI → Postgres — and to say precisely
/// which link is broken when it does not. Phase 1 replaces it with the login
/// screen and phase 4 with the real home screen.
///
/// Stopping Postgres must turn the DB row red **without crashing**: the backend
/// answers 200 with `status: "degraded"` (decision D-009) exactly so this view
/// can be specific instead of showing a generic network failure.
struct HealthView: View {
    @State private var model = HealthViewModel()

    var body: some View {
        VStack(spacing: 0) {
            ConceptRibbon()

            ScrollView {
                VStack(alignment: .leading, spacing: Metrics.cardGap) {
                    header
                    statusCard
                    configCard
                }
                .padding(.horizontal, Metrics.screenPadding)
                .padding(.vertical, 20)
            }
            .background(Theme.bg)
        }
        .task { await model.load() }
        .refreshable { await model.load() }
    }

    // MARK: - Pieces

    private var header: some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack(alignment: .firstTextBaseline, spacing: 8) {
                Text("Paytm")
                    .font(.system(size: 30, weight: .bold))
                    .foregroundStyle(Theme.navy)

                Text("Concept")
                    .font(.system(size: 10, weight: .bold))
                    .foregroundStyle(Theme.text1)
                    .padding(.horizontal, 8)
                    .padding(.vertical, 2)
                    .background(Theme.badgeNew, in: Capsule())
            }

            Text("Spasht · loans you understand")
                .font(.spashtCaption)
                .foregroundStyle(Theme.text3)
        }
        .padding(.top, 8)
    }

    @ViewBuilder
    private var statusCard: some View {
        VStack(alignment: .leading, spacing: 14) {
            Text("Phase 0 scaffold")
                .font(.spashtSection)
                .foregroundStyle(Theme.text1)

            switch model.state {
            case .loading:
                StatusRow(state: .pending, label: "Backend", detail: "contacting /api/health…")

            case .failed(let error):
                StatusRow(state: .bad, label: "Backend", detail: error.userMessage)
                if let requestId = error.requestId {
                    Text("request \(requestId)")
                        .font(.spashtCaption)
                        .foregroundStyle(Theme.text3)
                }

            case .loaded(let health):
                StatusRow(state: .good, label: "Backend", detail: "OK")
                StatusRow(
                    state: health.isDatabaseHealthy ? .good : .bad,
                    label: "DB",
                    detail: health.db
                )
                StatusRow(
                    state: health.sarvam == .configured ? .good : .pending,
                    label: "Sarvam",
                    detail: health.sarvam == .configured ? "configured" : "demo mode"
                )

                Divider()

                // The exact string the phase-0 acceptance check looks for.
                Text(model.summaryLine)
                    .font(.spashtBodyBold)
                    .foregroundStyle(Theme.text1)
                    .accessibilityIdentifier("health-summary")

                Text("v\(health.version) · \(health.env)")
                    .font(.spashtCaption)
                    .foregroundStyle(Theme.text3)
            }

            Button {
                Task { await model.load() }
            } label: {
                Label("Retry", systemImage: "arrow.clockwise")
                    .font(.spashtChip.weight(.semibold))
                    .foregroundStyle(Theme.navy)
                    .padding(.horizontal, 14)
                    .frame(height: Metrics.minimumTapTarget)
                    .overlay(Capsule().stroke(Theme.hairline, lineWidth: 1))
            }
            .disabled(model.state.isLoading)
        }
        .spashtCard()
    }

    private var configCard: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("Configuration")
                .font(.spashtBodyBold)
                .foregroundStyle(Theme.text1)

            ConfigRow(label: "API", value: AppConfig.apiBaseURL.absoluteString)
            ConfigRow(label: "App", value: AppConfig.appVersion)
            ConfigRow(
                label: "Google sign-in",
                value: AppConfig.isGoogleSignInConfigured
                    ? "configured" : "needs GoogleService-Info.plist"
            )
            ConfigRow(
                label: "Demo login",
                value: AppConfig.isDemoLoginAvailable ? "available" : "off"
            )

            Text("Login arrives in phase 1, the Paytm-style home in phase 4.")
                .font(.spashtCaption)
                .foregroundStyle(Theme.text3)
                .padding(.top, 6)
        }
        .spashtCard()
    }
}

// MARK: - Small components

private struct ConfigRow: View {
    let label: String
    let value: String

    var body: some View {
        HStack(alignment: .top, spacing: 8) {
            Text(label)
                .font(.spashtCaption)
                .foregroundStyle(Theme.text3)
                .frame(width: 104, alignment: .leading)

            Text(value)
                .font(.spashtCaption)
                .foregroundStyle(Theme.text2)
                .textSelection(.enabled)
        }
    }
}

private struct StatusRow: View {
    enum RowState { case good, bad, pending }

    let state: RowState
    let label: String
    let detail: String

    var body: some View {
        HStack(spacing: 10) {
            icon
            Text(label)
                .font(.spashtBodyBold)
                .foregroundStyle(Theme.text2)
            Text(detail)
                .font(.spashtBody)
                .foregroundStyle(Theme.text3)
                .lineLimit(2)
            Spacer(minLength: 0)
        }
        .accessibilityElement(children: .combine)
    }

    @ViewBuilder
    private var icon: some View {
        switch state {
        case .good:
            Image(systemName: "checkmark.circle.fill").foregroundStyle(Theme.success)
        case .bad:
            Image(systemName: "xmark.circle.fill").foregroundStyle(Theme.danger)
        case .pending:
            ProgressView().controlSize(.small)
        }
    }
}

#Preview {
    HealthView()
}
