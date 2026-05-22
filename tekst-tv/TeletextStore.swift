import Foundation
import Observation

@Observable
@MainActor
final class TeletextStore {
    private(set) var feed: TeletextFeed = .fallback
    private(set) var statusMessage = "Starter"
    private(set) var errorMessage: String?
    private(set) var isLoading = false

    private let remoteFeedURL: URL?
    private let cacheFileName = "cached-pages.json"
    private let refreshInterval: Duration = .seconds(300)

    init(remoteFeedURL: URL? = nil) {
        self.remoteFeedURL = remoteFeedURL ?? TeletextConfiguration.remoteFeedURL
    }

    func load() async {
        isLoading = true
        defer { isLoading = false }

        if let remoteFeedURL {
            do {
                let data = try await fetchRemoteFeed(from: remoteFeedURL)
                feed = try decodeFeed(from: data)
                try saveCache(data)
                statusMessage = "Oppdatert fra nett \(Self.statusTimeFormatter.string(from: Date()))"
                errorMessage = nil
                return
            } catch {
                errorMessage = "Nettoppdatering feilet. Viser lagret innhold."
            }
        }

        if loadCachedFeed() {
            return
        }

        loadBundledFeed()
    }

    func startAutoRefresh() async {
        await load()

        guard remoteFeedURL != nil else {
            statusMessage = "Lokal prototype - ingen nettfeed"
            return
        }

        while !Task.isCancelled {
            do {
                try await Task.sleep(for: refreshInterval)
                await load()
            } catch {
                return
            }
        }
    }

    private func fetchRemoteFeed(from url: URL) async throws -> Data {
        var request = URLRequest(url: url)
        request.cachePolicy = .reloadIgnoringLocalCacheData
        request.timeoutInterval = 12

        let (data, response) = try await URLSession.shared.data(for: request)
        guard let httpResponse = response as? HTTPURLResponse else {
            throw URLError(.badServerResponse)
        }
        guard (200...299).contains(httpResponse.statusCode) else {
            throw URLError(.badServerResponse)
        }
        return data
    }

    private func loadCachedFeed() -> Bool {
        guard let cacheURL else {
            return false
        }

        do {
            let data = try Data(contentsOf: cacheURL)
            feed = try decodeFeed(from: data)
            statusMessage = "Viser lagret kopi"
            return true
        } catch {
            return false
        }
    }

    private func loadBundledFeed() {
        guard let url = Bundle.main.url(forResource: "pages", withExtension: "json") else {
            errorMessage = "Fant ikke pages.json"
            statusMessage = "Reserveinnhold"
            feed = .fallback
            return
        }

        do {
            let data = try Data(contentsOf: url)
            feed = try decodeFeed(from: data)
            statusMessage = "Viser lokal prototype"
            if remoteFeedURL == nil {
                errorMessage = nil
            }
        } catch {
            errorMessage = "Kunne ikke lese pages.json"
            statusMessage = "Reserveinnhold"
            feed = .fallback
        }
    }

    private func decodeFeed(from data: Data) throws -> TeletextFeed {
        let decoder = JSONDecoder()
        return try decoder.decode(TeletextFeed.self, from: data)
    }

    private func saveCache(_ data: Data) throws {
        guard let cacheURL else {
            return
        }
        try data.write(to: cacheURL, options: [.atomic])
    }

    private var cacheURL: URL? {
        FileManager.default.urls(for: .cachesDirectory, in: .userDomainMask).first?.appendingPathComponent(cacheFileName)
    }

    private static let statusTimeFormatter: DateFormatter = {
        let formatter = DateFormatter()
        formatter.dateFormat = "HH:mm"
        return formatter
    }()
}

enum TeletextConfiguration {
    static var remoteFeedURL: URL? {
        if let value = Bundle.main.object(forInfoDictionaryKey: "TeletextFeedURL") as? String,
           let url = URL(string: value),
           !value.isEmpty {
            return url
        }

        if let value = UserDefaults.standard.string(forKey: "TeletextFeedURL"),
           let url = URL(string: value),
           !value.isEmpty {
            return url
        }

        return URL(string: "https://sveinungaxelsen.github.io/tekst-tv/pages.json")
    }
}

extension TeletextFeed {
    static let fallback = TeletextFeed(
        updated: "Lokal reserve",
        sections: [
            TeletextSection(
                id: "fallback",
                title: "Forside",
                startPage: "100",
                colorName: .yellow,
                pages: [
                    TeletextPage(
                        id: "100",
                        number: "100",
                        title: "Forside",
                        lines: [
                            TeletextLine(
                                id: "fallback-1",
                                headline: "Tekst-TV er klar",
                                ingress: "Appen viser reserveinnhold fordi pages.json ikke kunne lastes.",
                                body: "Sjekk at pages.json ligger i appens bundle og at JSON-formatet er gyldig.",
                                colorName: .yellow,
                                isImportant: true
                            )
                        ]
                    )
                ]
            )
        ]
    )
}
