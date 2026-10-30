import PDFKit
import SwiftUI

/// The in-app KFS viewer (build plan §13.11).
///
/// `PDFKit`, not a web view. The app deliberately has **no web views** (§13.11):
/// one would be a general-purpose renderer for remote content inside a
/// financial app, and the only remote document this product needs is a PDF
/// that `PDFView` can display on its own.
///
/// The bytes are fetched through `APIClient` so the bearer and ngrok headers are
/// sent - handing the URL straight to `PDFView` would get the ngrok warning
/// page, or a 401, and render a blank sheet.
struct KfsViewer: View {
    /// The relative API path, e.g. `/api/kfs/<id>/file`.
    let path: String

    @Environment(\.dismiss) private var dismiss
    @State private var document: PDFDocument?
    @State private var failed = false

    var body: some View {
        NavigationStack {
            ZStack {
                Theme.bg.ignoresSafeArea()

                if let document {
                    PdfView(document: document)
                        .ignoresSafeArea(edges: .bottom)
                } else if failed {
                    VStack(spacing: 10) {
                        Image(systemName: "doc.questionmark")
                            .font(.system(size: 30))
                            .foregroundStyle(Theme.text3)
                        Text("Could not open the Key Fact Statement.")
                            .font(.system(size: 14))
                            .foregroundStyle(Theme.text2)
                        Button("Try again") { Task { await load() } }
                            .font(.system(size: 14, weight: .semibold))
                    }
                } else {
                    ProgressView().tint(Theme.navy)
                }
            }
            .navigationTitle("Key Fact Statement")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button("Done") { dismiss() }
                }
            }
        }
        .task { await load() }
    }

    private func load() async {
        failed = false
        do {
            let data = try await APIClient.shared.data(path)
            guard let parsed = PDFDocument(data: data) else {
                failed = true
                return
            }
            document = parsed
        } catch {
            failed = true
        }
    }
}

private struct PdfView: UIViewRepresentable {
    let document: PDFDocument

    func makeUIView(context: Context) -> PDFView {
        let view = PDFView()
        view.document = document
        view.autoScales = true
        view.displayMode = .singlePageContinuous
        view.displayDirection = .vertical
        view.backgroundColor = UIColor(Theme.bg)
        return view
    }

    func updateUIView(_ view: PDFView, context: Context) {
        if view.document !== document {
            view.document = document
        }
    }
}
