import CoreImage.CIFilterBuiltins
import SwiftUI

/// QR generation with CoreImage (build plan §5.4, §5.7).
///
/// **The encoded string is never a `upi://` URL** (plan rule 9). A QR code that
/// looked like a payment request would be a real payment request to any UPI app
/// that scanned it, which is not something a concept demo gets to produce. The
/// profile QR carries a demo string; the receipt QR carries the public check
/// URL, which is a page, not a payment.
enum QrCode {

    /// The profile drawer's QR payload: synthetic and obviously so.
    static func demoPayload() -> String {
        // Six base32-ish characters is enough to make two screenshots differ,
        // which is all this needs to do.
        let suffix = String((0..<6).map { _ in "0123456789ABCDEFGHJKMNPQRSTVWXYZ".randomElement()! })
        return "SPASHT-CONCEPT-DEMO-\(suffix)"
    }

    /// Render a string as a QR image.
    ///
    /// @param scale  CoreImage emits roughly a 25pt image; scaling up with
    ///               nearest-neighbour keeps the modules crisp instead of the
    ///               blurry result `resizable()` alone would give.
    @MainActor
    static func image(from text: String, scale: CGFloat = 12) -> Image? {
        let filter = CIFilter.qrCodeGenerator()
        filter.message = Data(text.utf8)
        // "M" tolerates ~15% damage, which is the right trade for a code shown
        // on a screen and photographed from a few feet away.
        filter.correctionLevel = "M"

        guard let output = filter.outputImage else { return nil }
        let scaled = output.transformed(by: CGAffineTransform(scaleX: scale, y: scale))

        let context = CIContext()
        guard let cgImage = context.createCGImage(scaled, from: scaled.extent) else {
            return nil
        }
        return Image(decorative: cgImage, scale: 1, orientation: .up)
    }
}
