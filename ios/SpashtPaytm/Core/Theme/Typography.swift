import SwiftUI

/// Type scale from build plan §5.2.
///
/// SF Pro (the system font) throughout. Devanagari falls back to the system
/// Devanagari face automatically, which is why nothing here names a font file:
/// a bundled Latin font would break मराठी and हिंदी, the two languages the
/// product exists for.
extension Font {

    /// Section titles ("Recharge & Bills"). 20 bold.
    static let spashtSection = Font.system(size: 20, weight: .bold)

    /// Tile labels under an icon. 13 medium, two lines, centred.
    static let spashtTile = Font.system(size: 13, weight: .medium)

    /// Chips and quick replies. 13.
    static let spashtChip = Font.system(size: 13, weight: .regular)

    /// Body text and conversation bubbles. 16.
    static let spashtBody = Font.system(size: 16, weight: .regular)

    /// Emphasised body, e.g. an EMI figure inside a sentence.
    static let spashtBodyBold = Font.system(size: 16, weight: .semibold)

    /// Captions and source tags. 12.
    static let spashtCaption = Font.system(size: 12, weight: .regular)

    /// The concept ribbon and other fine print. 11.
    static let spashtFinePrint = Font.system(size: 11, weight: .medium)
}

extension View {
    /// Opt a view into Dynamic Type while capping how far it can grow.
    ///
    /// The journey must stay readable for someone who has enlarged their text —
    /// that is most of the audience this product is for — but the Paytm-style
    /// home screen is a dense 4-column grid that breaks past `.accessibility1`.
    /// §5.6 asks for Dynamic Type in the journey specifically.
    func spashtDynamicType(upTo limit: DynamicTypeSize = .accessibility1) -> some View {
        dynamicTypeSize(...limit)
    }
}
