//
//  ContentView.swift
//  tekst-tv
//
//  Created by Sveinung Axelsen on 21/05/2026.
//

import SwiftUI

struct ContentView: View {
    @Environment(\.scenePhase) private var scenePhase
    @State private var store = TeletextStore()
    @State private var currentSectionIndex = 0
    @State private var currentPageIndex = 0

    private var sections: [TeletextSection] {
        store.feed.sections
    }

    private var currentSection: TeletextSection {
        sections[safe: currentSectionIndex] ?? store.feed.sections[0]
    }

    private var currentPage: TeletextPage {
        currentSection.pages[safe: currentPageIndex] ?? currentSection.pages[0]
    }

    var body: some View {
        ZStack {
            TeletextTheme.background
                .ignoresSafeArea()

            VStack(spacing: 0) {
                header
                Divider().overlay(TeletextTheme.blue)
                pageBody
            }
            .padding(.horizontal, 48)
            .padding(.vertical, 20)
        }
        .foregroundStyle(.white)
        .fontDesign(.monospaced)
        .focusable(true)
        .task {
            await store.startAutoRefresh()
        }
        .onChange(of: store.feed.sections.count) { _, _ in
            clampSelection()
        }
        .onChange(of: scenePhase) { _, newPhase in
            guard newPhase == .active else {
                return
            }

            Task {
                await store.load()
            }
        }
        .onMoveCommand(perform: handleMoveCommand)
    }

    private var header: some View {
        HStack(alignment: .firstTextBaseline) {
            Text("TEKST-TV")
                .font(.system(size: 46, weight: .black))
                .foregroundStyle(.yellow)

            Text(currentPage.number)
                .font(.system(size: 46, weight: .black))
                .foregroundStyle(TeletextTheme.cyan)

            Text(currentPage.title.uppercased())
                .font(.system(size: 32, weight: .bold))
                .lineLimit(1)
                .minimumScaleFactor(0.7)

            Spacer(minLength: 24)

            VStack(alignment: .trailing, spacing: 6) {
                TimelineView(.periodic(from: .now, by: 1)) { context in
                    Text(Self.clockFormatter.string(from: context.date))
                        .font(.system(size: 24, weight: .black))
                        .foregroundStyle(.yellow)
                }

                Text(store.isLoading ? "Henter innhold" : store.statusMessage)
                    .font(.system(size: 20, weight: .bold))
                    .foregroundStyle(.white.opacity(0.7))

                Text("Side \(currentPageIndex + 1) av \(currentSection.pages.count)")
                    .font(.system(size: 19, weight: .semibold))
                    .foregroundStyle(TeletextTheme.cyan)
            }
        }
        .padding(.bottom, 10)
    }

    private static let clockFormatter: DateFormatter = {
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "nb_NO")
        formatter.dateFormat = "HH:mm:ss"
        return formatter
    }()

    private var pageBody: some View {
        HStack(alignment: .top, spacing: 28) {
            sectionMenu

            VStack(alignment: .leading, spacing: 17) {
                if let errorMessage = store.errorMessage {
                    Text(errorMessage)
                        .font(.system(size: 26, weight: .black))
                        .foregroundStyle(.red)
                }

                ForEach(currentPage.lines) { line in
                    TeletextLineView(line: line)
                }

                Spacer(minLength: 0)
            }
            .frame(maxWidth: .infinity, alignment: .topLeading)
            .padding(.top, 16)
        }
    }

    private var sectionMenu: some View {
        VStack(alignment: .leading, spacing: 9) {
            ForEach(Array(sections.enumerated()), id: \.element.id) { index, section in
                Button {
                    currentSectionIndex = index
                    currentPageIndex = 0
                } label: {
                    HStack(spacing: 10) {
                        Text(section.startPage)
                            .font(.system(size: 25, weight: .black))
                            .foregroundStyle(section.color)

                        Text(section.title.uppercased())
                            .font(.system(size: 25, weight: .bold))
                            .foregroundStyle(index == currentSectionIndex ? .black : .white)
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(.horizontal, 12)
                    .padding(.vertical, 8)
                    .background(index == currentSectionIndex ? section.color : Color.white.opacity(0.08))
                    .clipShape(RoundedRectangle(cornerRadius: 6))
                }
                .buttonStyle(.plain)
                .focusEffectDisabled()
                .accessibilityLabel("\(section.title), side \(section.startPage)")
            }

            Spacer(minLength: 20)

            VStack(alignment: .leading, spacing: 8) {
                Text("FJERNKONTROLL")
                    .foregroundStyle(.yellow)
                Text("Piler  flytt")
                Text("OK     trykk knapp")
                Text("Menu   avslutt")
            }
            .font(.system(size: 19, weight: .bold))
            .foregroundStyle(.white.opacity(0.75))
        }
        .frame(width: 292)
        .padding(.top, 16)
    }

    private var remoteControlButtons: some View {
        HStack(spacing: 12) {
            RemoteActionButton(title: "Forrige seksjon", systemImage: "arrow.up", color: currentSection.color, action: previousSection)
            RemoteActionButton(title: "Neste seksjon", systemImage: "arrow.down", color: currentSection.color, action: nextSection)
            RemoteActionButton(title: "Forrige side", systemImage: "arrow.left", color: .yellow, action: previousPage)
            RemoteActionButton(title: "Neste side", systemImage: "arrow.right", color: .yellow, action: nextPage)
            RemoteActionButton(title: "Side 100", systemImage: "house.fill", color: TeletextTheme.blue, action: goToFrontPage)
        }
        .padding(.top, 10)
        .focusSection()
    }

    private var footer: some View {
        VStack(spacing: 10) {
            Divider().overlay(TeletextTheme.blue)

            HStack(spacing: 12) {
                ForEach(sections) { section in
                    FooterShortcut(label: section.startPage, title: section.title, color: section.color)
                }

                Spacer()

                Text("TV-fjernkontroll: piler + OK")
                    .foregroundStyle(.white.opacity(0.65))
            }
            .font(.system(size: 16, weight: .bold))
        }
        .padding(.top, 10)
    }

    private func handleMoveCommand(_ direction: MoveCommandDirection) {
        switch direction {
        case .left:
            previousPage()
        case .right:
            nextPage()
        case .up:
            previousSection()
        case .down:
            nextSection()
        default:
            break
        }
    }

    private func nextPage() {
        currentPageIndex = (currentPageIndex + 1) % currentSection.pages.count
    }

    private func previousPage() {
        currentPageIndex = (currentPageIndex - 1 + currentSection.pages.count) % currentSection.pages.count
    }

    private func nextSection() {
        currentSectionIndex = (currentSectionIndex + 1) % sections.count
        currentPageIndex = 0
    }

    private func previousSection() {
        currentSectionIndex = (currentSectionIndex - 1 + sections.count) % sections.count
        currentPageIndex = 0
    }

    private func goToFrontPage() {
        currentSectionIndex = 0
        currentPageIndex = 0
    }

    private func clampSelection() {
        currentSectionIndex = min(currentSectionIndex, max(sections.count - 1, 0))
        currentPageIndex = min(currentPageIndex, max(currentSection.pages.count - 1, 0))
    }
}

private struct TeletextLineView: View {
    let line: TeletextLine

    var body: some View {
        VStack(alignment: .leading, spacing: 7) {
            Text(line.headline)
                .font(.system(size: line.isImportant ? 50 : 33, weight: .black))
                .foregroundStyle(line.color)
                .lineLimit(2)
                .minimumScaleFactor(0.75)

            if let ingress = line.ingress {
                Text(ingress)
                    .font(.system(size: 28, weight: .black))
                    .foregroundStyle(.white)
                    .lineSpacing(5)
                    .fixedSize(horizontal: false, vertical: true)
            }

            if let body = line.body {
                if shouldAlternateBodyRows(body) {
                    AlternatingBodyRows(text: body)
                } else {
                    Text(body)
                        .font(.system(size: 29, weight: .semibold))
                        .foregroundStyle(.white.opacity(0.9))
                        .lineSpacing(7)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }

            if !line.bodyRows.isEmpty {
                VStack(alignment: .leading, spacing: 2) {
                    ForEach(line.bodyRows) { row in
                        BodyRowView(row: row)
                    }
                }
            }

            if let source = line.source {
                Text("Kilde: \(source)")
                    .font(.system(size: 19, weight: .bold))
                    .foregroundStyle(TeletextTheme.cyan.opacity(0.85))
            }
        }
    }

    private func shouldAlternateBodyRows(_ body: String) -> Bool {
        let rows = body.split(separator: "\n")
        guard rows.count >= 4 else {
            return false
        }

        let listLikeRows = rows.filter { row in
            let text = row.trimmingCharacters(in: .whitespaces)
            return text.range(of: #"^\d{1,2}\.\d{2}|\d+\.\s|^[A-ZÆØÅ][\p{L}\s.'/-]{1,28}\s{2,}"#, options: .regularExpression) != nil
        }
        return listLikeRows.count >= max(3, rows.count / 2)
    }
}

private struct BodyRowView: View {
    let row: TeletextBodyRow

    var body: some View {
        if let label = row.label, let detail = row.detail {
            HStack(alignment: .firstTextBaseline, spacing: 8) {
                Text(label)
                    .font(.system(size: 29, weight: .black))
                    .foregroundStyle(row.color)
                    .lineLimit(1)
                    .minimumScaleFactor(0.75)

                Text(detail)
                    .font(.system(size: 29, weight: .semibold))
                    .foregroundStyle(.white.opacity(0.92))
                    .lineLimit(1)
                    .minimumScaleFactor(0.75)
            }
        } else {
            Text(row.text)
                .font(.system(size: 29, weight: .semibold))
                .foregroundStyle(row.color)
                .lineLimit(1)
                .minimumScaleFactor(0.75)
        }
    }
}

private struct AlternatingBodyRows: View {
    let text: String

    private var rows: [String] {
        text.split(separator: "\n").map(String.init)
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            ForEach(Array(rows.enumerated()), id: \.offset) { index, row in
                Text(row)
                    .font(.system(size: 29, weight: .semibold))
                    .foregroundStyle(index.isMultiple(of: 2) ? .white.opacity(0.95) : TeletextTheme.cyan.opacity(0.82))
                    .lineLimit(1)
                    .minimumScaleFactor(0.74)
            }
        }
    }
}

private struct RemoteActionButton: View {
    let title: String
    let systemImage: String
    let color: Color
    let action: () -> Void

    private var foregroundColor: Color {
        color == .yellow ? .black : .white
    }

    var body: some View {
        Button(action: action) {
            HStack(spacing: 12) {
                Image(systemName: systemImage)
                    .font(.system(size: 18, weight: .black))
                Text(title)
                    .font(.system(size: 18, weight: .black))
                    .lineLimit(1)
                    .minimumScaleFactor(0.8)
            }
            .foregroundStyle(foregroundColor)
            .frame(maxWidth: .infinity, minHeight: 44)
            .padding(.horizontal, 10)
            .background(color)
            .clipShape(RoundedRectangle(cornerRadius: 6))
        }
        .buttonStyle(.plain)
        .focusEffectDisabled()
    }
}

private struct FooterShortcut: View {
    let label: String
    let title: String
    let color: Color

    var body: some View {
        HStack(spacing: 8) {
            Text(label)
                .foregroundStyle(.black)
                .padding(.horizontal, 8)
                .padding(.vertical, 4)
                .background(color)
            Text(title)
                .foregroundStyle(color)
                .lineLimit(1)
                .minimumScaleFactor(0.75)
        }
    }
}

private extension Array {
    subscript(safe index: Int) -> Element? {
        indices.contains(index) ? self[index] : nil
    }
}

#Preview {
    ContentView()
}
