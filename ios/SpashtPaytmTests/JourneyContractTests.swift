import XCTest

@testable import SpashtPaytm

/// Decode every journey fixture (build plan §8.5, phase 5 acceptance).
///
/// One test per card so a failure names the step that broke, rather than
/// reporting "a fixture did not decode" and leaving someone to find out which.
///
/// These also assert the *product's* claims where the fixture can prove them:
/// that consents arrive ungranted, that insurance is optional and off, and that
/// Bank B is badged as the trap. A payload that decoded but had the badges the
/// wrong way round would pass a decode-only test and lose the demo.
final class JourneyContractTests: XCTestCase {

    private func turn(_ name: String) throws -> TurnResponse {
        try FixtureLoader.decode(TurnResponse.self, from: name)
    }

    // MARK: - Every step decodes

    func testEveryJourneyFixtureDecodes() throws {
        let names = [
            "turn_intro", "turn_consent", "turn_prefill", "turn_confirm",
            "turn_offers", "turn_kfs", "turn_quiz", "turn_quiz_wrong",
            "turn_terms_consent", "turn_otp", "turn_receipt",
            "turn_handoff", "turn_manual_form",
        ]
        for name in names {
            let response = try turn(name)
            XCTAssertFalse(response.step.isEmpty, name)
            XCTAssertEqual(response.progress.total, 6, name)
            XCTAssertNotNil(response.card, "\(name) has no card")
        }
    }

    // MARK: - Amount

    func testIntroOffersAmountChips() throws {
        let response = try turn("turn_intro")
        XCTAssertEqual(response.step, "ASK_NEED")

        guard case .amount(let card) = response.card else {
            return XCTFail("expected an amount card, got \(String(describing: response.card))")
        }
        XCTAssertEqual(card.min, 10_000)
        XCTAssertEqual(card.max, 200_000)
        XCTAssertTrue(card.chips.contains(50_000))
    }

    // MARK: - Consent

    func testConsentPurposesArriveUngranted() throws {
        let response = try turn("turn_consent")
        guard case .consent(let card) = response.card else {
            return XCTFail("expected a consent card")
        }

        XCTAssertEqual(card.purposes.count, 2)
        // The product's central claim about consent (§5.6, §9).
        XCTAssertTrue(card.purposes.allSatisfy { !$0.granted })
        XCTAssertFalse(card.why.isEmpty, "a consent with no stated reason is not consent")
    }

    // MARK: - Prefill

    func testPrefillNamesItsSources() throws {
        let response = try turn("turn_prefill")
        guard case .prefill(let card) = response.card else {
            return XCTFail("expected a prefill card")
        }

        let sources = Set(card.rows.map(\.source))
        XCTAssertEqual(
            sources,
            ["DigiLocker", "CKYC", "Account Aggregator", "UPI AutoPay"],
            "every fetched value must say where it came from"
        )
    }

    // MARK: - Offers

    func testOffersAreSortedByAprAndBadged() throws {
        let response = try turn("turn_offers")
        guard case .offers(let card) = response.card else {
            return XCTFail("expected an offers card")
        }

        XCTAssertEqual(card.offers.count, 3)
        XCTAssertEqual(card.offers.map(\.apr), card.offers.map(\.apr).sorted())

        let cheapest = card.offers.first { $0.isCheapest }
        let trap = card.offers.first { $0.isLowRateHighFee }
        XCTAssertNotNil(cheapest)
        XCTAssertNotNil(trap)

        // The demo's insight, asserted on the wire: the lowest-rate offer is
        // the expensive one.
        if let cheapest, let trap {
            XCTAssertLessThan(trap.ratePa, cheapest.ratePa)
            XCTAssertGreaterThan(trap.totalCost, cheapest.totalCost)
            XCTAssertGreaterThan(trap.apr, cheapest.apr)
        }

        XCTAssertEqual(card.suitability.decision, "suitable")
        XCTAssertFalse(card.suitability.reasons.isEmpty)
    }

    // MARK: - KFS

    func testKfsCardIsFlaggedAsASample() throws {
        let response = try turn("turn_kfs")
        guard case .kfs(let card) = response.card else {
            return XCTFail("expected a KFS card")
        }

        XCTAssertTrue(card.sample, "the KFS must always be labelled a sample")
        XCTAssertFalse(card.lines.isEmpty)
        XCTAssertTrue(
            card.lines.contains(where: \.redFlag),
            "at least the late fee and foreclosure lines should be flagged"
        )
        XCTAssertTrue(card.pdfUrl.hasPrefix("/api/kfs/"))
    }

    // MARK: - Quiz

    func testQuizCardCarriesAttemptCounts() throws {
        let response = try turn("turn_quiz")
        guard case .quiz(let card) = response.card else {
            return XCTFail("expected a quiz card")
        }

        XCTAssertEqual(card.index, 1)
        XCTAssertEqual(card.total, 3)
        XCTAssertEqual(card.attempt, 1)
        XCTAssertEqual(card.maxAttempts, 3)
        XCTAssertGreaterThanOrEqual(card.options.count, 2)
        XCTAssertNil(card.result, "an unanswered question has no result")
    }

    func testWrongAnswerCarriesAReExplanation() throws {
        let response = try turn("turn_quiz_wrong")
        guard case .quiz(let card) = response.card else {
            return XCTFail("expected a quiz card")
        }

        XCTAssertEqual(card.result?.correct, false)
        XCTAssertNotNil(card.result?.explanation)
        XCTAssertEqual(card.attempt, 2, "a wrong answer uses one of the three attempts")
        // Still locked: this is the whole point.
        XCTAssertFalse(response.locks.acceptEnabled)
    }

    // MARK: - Consent lock

    func testTermsConsentUnlocksWithInsuranceOff() throws {
        let response = try turn("turn_terms_consent")
        guard case .consentLock(let card) = response.card else {
            return XCTFail("expected a consent lock card")
        }

        XCTAssertTrue(card.acceptEnabled, "teach-back passed, so the lock should be open")
        XCTAssertTrue(response.locks.acceptEnabled)
        XCTAssertFalse(card.terms.isEmpty, "the customer must be told what they are agreeing to")

        // Never bundled, never pre-selected (§7.2).
        XCTAssertTrue(card.insurance.optional)
        XCTAssertFalse(card.insurance.granted)
    }

    // MARK: - OTP

    func testOtpCardIsSixDigits() throws {
        let response = try turn("turn_otp")
        guard case .otp(let card) = response.card else {
            return XCTFail("expected an OTP card")
        }
        XCTAssertEqual(card.length, 6)
        XCTAssertGreaterThan(card.expiresInSec, 0)
    }

    func testOtpSendResponseDecodes() throws {
        let sent = try FixtureLoader.decode(OtpSendResponse.self, from: "otp_send")
        XCTAssertTrue(sent.sent)
        XCTAssertEqual(sent.expiresInSec, 300)
    }

    // MARK: - Receipt

    func testReceiptCardCarriesTheSignedFigures() throws {
        let response = try turn("turn_receipt")
        guard case .receipt(let card) = response.card else {
            return XCTFail("expected a receipt card")
        }

        XCTAssertTrue(card.receiptNo.hasPrefix("SP-"))
        XCTAssertEqual(card.teachback.passed, card.teachback.total)
        XCTAssertFalse(card.insuranceTaken, "the golden path declines insurance")
        XCTAssertTrue(
            card.publicUrl.contains("/r/"),
            "the QR must point at the public check page"
        )
        XCTAssertFalse(card.summaryText.isEmpty)
        XCTAssertEqual(response.status, .completed)
    }

    // MARK: - Handoff and the manual form

    func testHandoffCardDecodes() throws {
        let response = try turn("turn_handoff")
        guard case .handoff(let card) = response.card else {
            return XCTFail("expected a handoff card")
        }
        XCTAssertFalse(card.message.isEmpty)
        XCTAssertFalse(card.window.isEmpty)
        XCTAssertEqual(response.status, .needsHuman)
        XCTAssertFalse(response.locks.acceptEnabled, "a handoff must leave consent locked")
    }

    func testManualFormHasEveryRequiredField() throws {
        let response = try turn("turn_manual_form")
        guard case .manualForm(let card) = response.card else {
            return XCTFail("expected a manual form card")
        }
        XCTAssertEqual(
            Set(card.fields.map(\.id)),
            ["fullName", "dob", "monthlyIncome", "shopAddress", "mobile"]
        )
        XCTAssertTrue(card.fields.allSatisfy(\.required))
    }

    // MARK: - Unknown cards

    func testAnUnknownCardTypeDecodesAsUnsupported() throws {
        // The forward-compatibility guarantee of §8.4: a newer backend must not
        // be able to break this build, only to show "please update the app".
        let json = """
            {"type": "something_from_2027", "data": {"whatever": true}}
            """.data(using: .utf8)!

        let card = try JSONDecoder().decode(Card.self, from: json)
        guard case .unsupported(let type) = card else {
            return XCTFail("expected .unsupported, got \(card)")
        }
        XCTAssertEqual(type, "something_from_2027")
    }

    func testAnUnknownStepStillDecodes() throws {
        // `step` is a String, not an enum, for the same reason.
        var payload = try JSONSerialization.jsonObject(
            with: try FixtureLoader.data("turn_intro")
        ) as! [String: Any]
        payload["step"] = "SOME_NEW_STEP"

        let data = try JSONSerialization.data(withJSONObject: payload)
        let response = try JSONDecoder().decode(TurnResponse.self, from: data)
        XCTAssertEqual(response.step, "SOME_NEW_STEP")
    }

    // MARK: - Quick replies

    func testQuickRepliesRelayOpaqueActions() throws {
        let response = try turn("turn_consent")
        XCTAssertFalse(response.quickReplies.isEmpty)

        // A chip is either text or an action the app relays without
        // understanding it, so a new backend chip needs no app release.
        for reply in response.quickReplies {
            XCTAssertFalse(reply.label.isEmpty)
            let hasPayload = reply.send.text != nil || reply.send.action != nil
            XCTAssertTrue(hasPayload, "chip \"\(reply.label)\" sends nothing")
        }
    }
}

/// Encoding, which the fixtures cannot check: these go *to* the backend.
final class JourneyActionEncodingTests: XCTestCase {

    private func encode(_ action: JourneyAction) throws -> [String: Any] {
        let data = try JSONEncoder().encode(action)
        return try JSONSerialization.jsonObject(with: data) as! [String: Any]
    }

    func testConsentsEncodeAsTheBackendsSnakeCaseGrants() throws {
        let json = try encode(.consents(digilocker: true, accountAggregator: false))

        XCTAssertEqual(json["name"] as? String, "consents")
        let grants = json["grants"] as? [String: Any]
        XCTAssertEqual(grants?["fetch_digilocker"] as? Bool, true)
        XCTAssertEqual(grants?["fetch_account_aggregator"] as? Bool, false)
    }

    func testConfirmWithNoEditsOmitsTheKeyEntirely() throws {
        // The backend's models are `extra="forbid"`, and an explicit null is
        // noise that a stricter validator could reject.
        let json = try encode(.confirmDetails(shopAddress: nil, mobile: nil))
        XCTAssertEqual(json["name"] as? String, "confirm_details")
        XCTAssertNil(json["edits"])
    }

    func testConfirmSendsOnlyTheEditedField() throws {
        let json = try encode(.confirmDetails(shopAddress: nil, mobile: "9800000210"))
        let edits = json["edits"] as? [String: Any]
        XCTAssertEqual(edits?["mobile"] as? String, "9800000210")
        XCTAssertNil(edits?["shopAddress"])
    }

    func testPayloadlessActionsEncodeAsJustAName() throws {
        for (action, name) in [
            (JourneyAction.acceptTerms, "accept_terms"),
            (.repeatLast, "repeat"),
            (.didntUnderstand, "didnt_understand"),
            (.requestHuman, "request_human"),
        ] as [(JourneyAction, String)] {
            let json = try encode(action)
            XCTAssertEqual(json["name"] as? String, name)
            XCTAssertEqual(json.count, 1, "\(name) should carry no payload")
        }
    }

    func testTurnRequestCarriesTheIdempotencyKey() throws {
        let id = UUID()
        let request = TurnRequest(
            clientTurnId: id, expectedVersion: 4, input: .tap(.amount(50_000))
        )
        let json = try JSONSerialization.jsonObject(
            with: try JSONEncoder().encode(request)
        ) as! [String: Any]

        XCTAssertEqual(json["clientTurnId"] as? String, id.uuidString)
        XCTAssertEqual(json["expectedVersion"] as? Int, 4)
        let input = json["input"] as? [String: Any]
        XCTAssertEqual(input?["type"] as? String, "tap")
    }

    func testTextTurnEncodesTheUtterance() throws {
        let request = TurnRequest(
            clientTurnId: UUID(), expectedVersion: nil, input: .text("मला ५० हजार हवे")
        )
        let json = try JSONSerialization.jsonObject(
            with: try JSONEncoder().encode(request)
        ) as! [String: Any]

        let input = json["input"] as? [String: Any]
        XCTAssertEqual(input?["type"] as? String, "text")
        XCTAssertEqual(input?["text"] as? String, "मला ५० हजार हवे")
    }
}
