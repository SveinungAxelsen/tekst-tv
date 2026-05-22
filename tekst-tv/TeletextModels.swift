import SwiftUI

struct TeletextFeed: Decodable {
    let updated: String
    let sections: [TeletextSection]
}

struct TeletextSection: Decodable, Identifiable {
    let id: String
    let title: String
    let startPage: String
    let colorName: TeletextColor
    let pages: [TeletextPage]

    var color: Color {
        colorName.color
    }
}

struct TeletextPage: Decodable, Identifiable {
    let id: String
    let number: String
    let title: String
    let lines: [TeletextLine]
}

struct TeletextLine: Decodable, Identifiable {
    let id: String
    let headline: String
    let ingress: String?
    let body: String?
    let bodyRows: [TeletextBodyRow]
    let source: String?
    let colorName: TeletextColor
    let isImportant: Bool

    var color: Color {
        colorName.color
    }

    enum CodingKeys: String, CodingKey {
        case id
        case headline
        case ingress
        case body
        case bodyRows
        case source
        case colorName
        case isImportant
    }

    init(
        id: String,
        headline: String,
        ingress: String? = nil,
        body: String? = nil,
        bodyRows: [TeletextBodyRow] = [],
        source: String? = nil,
        colorName: TeletextColor = .yellow,
        isImportant: Bool = false
    ) {
        self.id = id
        self.headline = headline
        self.ingress = ingress
        self.body = body
        self.bodyRows = bodyRows
        self.source = source
        self.colorName = colorName
        self.isImportant = isImportant
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        id = try container.decode(String.self, forKey: .id)
        headline = try container.decode(String.self, forKey: .headline)
        ingress = try container.decodeIfPresent(String.self, forKey: .ingress)
        body = try container.decodeIfPresent(String.self, forKey: .body)
        bodyRows = try container.decodeIfPresent([TeletextBodyRow].self, forKey: .bodyRows) ?? []
        source = try container.decodeIfPresent(String.self, forKey: .source)
        colorName = try container.decodeIfPresent(TeletextColor.self, forKey: .colorName) ?? .yellow
        isImportant = try container.decodeIfPresent(Bool.self, forKey: .isImportant) ?? false
    }
}

struct TeletextBodyRow: Decodable, Identifiable {
    let id: String
    let text: String
    let colorName: TeletextColor

    var color: Color {
        colorName.color
    }
}

enum TeletextColor: String, Decodable {
    case blue
    case cyan
    case green
    case magenta
    case orange
    case purple
    case red
    case teal
    case white
    case yellow

    var color: Color {
        switch self {
        case .blue:
            TeletextTheme.blue
        case .cyan:
            TeletextTheme.cyan
        case .green:
            .green
        case .magenta:
            TeletextTheme.magenta
        case .orange:
            TeletextTheme.orange
        case .purple:
            TeletextTheme.purple
        case .red:
            .red
        case .teal:
            TeletextTheme.teal
        case .white:
            .white
        case .yellow:
            .yellow
        }
    }
}

enum TeletextTheme {
    static let background = Color(red: 0.01, green: 0.01, blue: 0.08)
    static let blue = Color(red: 0.05, green: 0.2, blue: 0.95)
    static let cyan = Color(red: 0.0, green: 0.95, blue: 1.0)
    static let magenta = Color(red: 1.0, green: 0.25, blue: 0.85)
    static let orange = Color(red: 1.0, green: 0.58, blue: 0.0)
    static let purple = Color(red: 0.72, green: 0.45, blue: 1.0)
    static let teal = Color(red: 0.0, green: 0.85, blue: 0.65)
}
