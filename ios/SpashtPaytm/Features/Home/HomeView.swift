import SwiftUI

/// The Paytm-style home screen (build plan §5.3).
///
/// Sixteen sections in order, driven entirely by `HomeConfig`. This view's job
/// is composition and routing: which tile opens the journey, which opens the
/// concept sheet, and where the drawer comes from.
///
/// **One live feature.** `Loan` pushes `SpashtIntroView`; every other tap opens
/// the concept sheet (§5.1). That is enforced by `HomeConfig.Action` having no
/// third case, so a new tile cannot accidentally do something real.
struct HomeView: View {
    let auth: AuthService
    let me: Me

    @Environment(\.scenePhase) private var scenePhase

    @State private var showsDrawer = false
    @State private var conceptSubject: String?
    @State private var path: [Route] = []

    // --- the rescue agent (phase 10) ---
    //
    // It lives here rather than in `RootView` because answering a call has to
    // open the journey, and the home screen is what owns navigation. Polling
    // only while this screen exists also means it only runs when somebody is
    // signed in.
    @State private var rescue = RescueService()
    @State private var callAudio = CallAudioPlayer()
    @State private var rescueScreen: RescueScreen?

    /// What the rescue agent is currently showing full-screen. One piece of
    /// state rather than two `fullScreenCover` modifiers, which SwiftUI does
    /// not reliably present side by side.
    private enum RescueScreen: Identifiable {
        case incoming(RescueCall)
        case resumed(TurnResponse)

        var id: String {
            switch self {
            case .incoming(let call): return "call:\(call.taskId)"
            case .resumed(let response): return "journey:\(response.journeyId)"
            }
        }
    }

    /// Shown once per install (§5.3 item 16).
    @AppStorage(HomeConfig.tooltipSeenKey) private var tooltipSeen = false

    /// Where the home screen can navigate to. An enum rather than a bare view
    /// so the stack is `Codable`-shaped and resume is possible later.
    private enum Route: Hashable {
        case spasht
        case profileCompletion
    }

    var body: some View {
        NavigationStack(path: $path) {
            ZStack(alignment: .top) {
                Theme.bg.ignoresSafeArea()

                ScrollView {
                    LazyVStack(spacing: Metrics.cardGap) {
                        HomeTopBar(
                            initials: me.initials,
                            photoURL: me.photoUrl.flatMap(URL.init(string:)),
                            onAvatar: { showsDrawer = true },
                            onConcept: { showConcept("Search and notifications") }
                        )
                        .padding(.horizontal, Metrics.screenPadding)
                        .padding(.top, 6)

                        if !tooltipSeen {
                            FirstVisitTooltip(
                                onTap: {
                                    tooltipSeen = true
                                    path.append(.spasht)
                                },
                                onDismiss: { tooltipSeen = true }
                            )
                            .padding(.horizontal, Metrics.screenPadding)
                            .transition(.move(edge: .top).combined(with: .opacity))
                        }

                        // The carousel pads itself, so it sits outside the
                        // common horizontal inset and can bleed if needed.
                        PromoCarousel(onAction: handle)

                        Group {
                            UpiSection(onTile: handle)

                            RechargeSection(
                                onTile: handle,
                                onConcept: { showConcept("Recharge & Bills") }
                            )

                            OfferStrip(onTap: { showConcept("Exclusive offers") })

                            PostpaidGrid(onTap: { showConcept("Paytm Postpaid") })

                            ChipRow(chips: HomeConfig.topChips) {
                                showConcept("Offers and UPI Lite")
                            }
                            .padding(.vertical, 2)

                            TileSection(
                                title: "Travel & Tickets",
                                tiles: HomeConfig.travelTiles,
                                chips: HomeConfig.travelChips,
                                onTile: handle,
                                onConcept: { showConcept("Travel & Tickets") }
                            )

                            TileSection(
                                title: "Grow Your Money",
                                tiles: HomeConfig.growTiles,
                                onTile: handle,
                                onConcept: { showConcept("Grow Your Money") }
                            )

                            // ★ The one section with a working feature in it.
                            TileSection(
                                title: "Loans & Insurance",
                                tiles: HomeConfig.loanTiles,
                                chips: HomeConfig.loanChips,
                                onTile: handle,
                                onConcept: { showConcept("Loans & Insurance") }
                            )

                            FreeToolsSection(onTap: { showConcept("Free Tools") })

                            TileSection(
                                title: "Do More with Paytm",
                                tiles: HomeConfig.doMoreTiles,
                                chips: HomeConfig.doMoreChips,
                                onTile: handle,
                                onConcept: { showConcept("Services") }
                            )

                            PromotedSection(onTap: { showConcept("Promoted partners") })

                            ReferralCard(onTap: { showConcept("Refer & Win") })
                        }
                        .padding(.horizontal, Metrics.screenPadding)

                        // Clears the floating pill, so the last card is not
                        // permanently half-hidden behind it.
                        Spacer(minLength: 76)
                    }
                }
                .safeAreaInset(edge: .bottom) {
                    ScanQrPill(onTap: { showConcept("Scan QR") })
                }
            }
            .navigationBarHidden(true)
            .navigationDestination(for: Route.self) { route in
                switch route {
                case .spasht:
                    SpashtIntroView(auth: auth, me: me)
                case .profileCompletion:
                    ProfileCompletionView(me: me)
                }
            }
        }
        // The drawer is a full-screen overlay rather than a sheet: it slides in
        // from the left over a dimmed backdrop (§5.4), which a sheet cannot do.
        .overlay {
            if showsDrawer {
                ProfileDrawer(
                    auth: auth,
                    me: me,
                    onClose: { showsDrawer = false },
                    onProfileCompletion: {
                        showsDrawer = false
                        path.append(.profileCompletion)
                    },
                    onConcept: showConcept
                )
                .transition(.opacity)
            }
        }
        .animation(.easeInOut(duration: 0.22), value: showsDrawer)
        .animation(.easeInOut(duration: 0.25), value: tooltipSeen)
        .sheet(item: $conceptSubject) { subject in
            ConceptSheet(subject: subject) {
                conceptSubject = nil
                path.append(.spasht)
            }
        }
        // --- the rescue agent (phase 10) ---
        .task { rescue.start() }
        .onChange(of: scenePhase) { _, phase in
            // Foreground only (§12). A loop polling from the background would
            // be battery rudeness in exchange for a screen that cannot be
            // shown from there anyway.
            if phase == .active {
                rescue.start()
            } else {
                rescue.stop()
                callAudio.stop()
            }
        }
        .onChange(of: rescue.call) { _, call in
            guard let call else { return }
            rescueScreen = .incoming(call)
        }
        .fullScreenCover(item: $rescueScreen) { screen in
            switch screen {
            case .incoming(let call):
                IncomingCallView(
                    call: call,
                    isWorking: rescue.isWorking,
                    onAccept: { accept(call) },
                    onDecline: { decline(call) }
                )
            case .resumed(let response):
                // Wrapped in its own stack: the journey pushes the KFS viewer,
                // and a cover has no navigation of its own.
                NavigationStack {
                    JourneyView(auth: auth, language: response.language, resumed: response)
                }
            }
        }
    }

    // MARK: - Rescue

    /// Answer: speak the line, then show the step the customer stopped on.
    ///
    /// The audio starts before the resume call so the call *sounds* answered
    /// immediately; `play` returns once playback has begun, not when the line
    /// has finished, so the journey screen is not held back by it.
    private func accept(_ call: RescueCall) {
        Task {
            await callAudio.play(path: call.audioUrl)

            if let response = await rescue.accept(call) {
                rescueScreen = .resumed(response)
            } else {
                // The resume failed. The journey is untouched and still
                // reachable from the Loan tile, so the call simply closes.
                rescueScreen = nil
            }
        }
    }

    private func decline(_ call: RescueCall) {
        Task {
            callAudio.stop()
            await rescue.decline(call)
            rescueScreen = nil
        }
    }

    // MARK: - Routing

    private func handle(_ tile: HomeConfig.Tile) {
        handle(tile.action, subject: tile.label.replacingOccurrences(of: "\n", with: " "))
    }

    private func handle(_ action: HomeConfig.Action) {
        handle(action, subject: "This feature")
    }

    private func handle(_ action: HomeConfig.Action, subject: String) {
        switch action {
        case .spasht:
            path.append(.spasht)
        case .concept:
            showConcept(subject)
        }
    }

    private func showConcept(_ subject: String) {
        conceptSubject = subject
    }
}

/// `sheet(item:)` for a plain `String?`.
///
/// SwiftUI's own `sheet(item:)` needs `Identifiable`, and conforming `String`
/// app-wide would be rude to every other type that holds one. This keeps it
/// local.
extension View {
    func sheet<Content: View>(
        item: Binding<String?>,
        @ViewBuilder content: @escaping (String) -> Content
    ) -> some View {
        sheet(isPresented: Binding(
            get: { item.wrappedValue != nil },
            set: { if !$0 { item.wrappedValue = nil } }
        )) {
            if let value = item.wrappedValue {
                content(value)
            }
        }
    }
}
