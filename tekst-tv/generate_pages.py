#!/usr/bin/env python3
"""Generate the text-TV pages feed consumed by the Apple TV app."""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import time
import textwrap
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Iterable
from zoneinfo import ZoneInfo


NRK_LATEST_RSS_URL = "https://www.nrk.no/nyheter/siste.rss"
NRK_NORGE_RSS_URL = "https://www.nrk.no/norge/toppsaker.rss"
NRK_SPORT_TOP_RSS_URL = "https://www.nrk.no/sport/toppsaker.rss"
NRK_SPORT_LATEST_RSS_URL = "https://www.nrk.no/sport/siste.rss"
NRK_TROMS_RSS_URL = "https://www.nrk.no/troms/toppsaker.rss"
NRK_FINNMARK_RSS_URL = "https://www.nrk.no/finnmark/toppsaker.rss"
NRK_TROMS_FINNMARK_RSS_URL = "https://www.nrk.no/tromsogfinnmark/toppsaker.rss"
NRK_URIX_RSS_URL = "https://www.nrk.no/urix/toppsaker.rss"
BBC_WORLD_RSS_URL = "https://feeds.bbci.co.uk/news/world/rss.xml"
SPORTSDB_BASE_URL = "https://www.thesportsdb.com/api/v1/json/123"
ESPN_STANDINGS_BASE_URL = "https://site.web.api.espn.com/apis/v2/sports/soccer"
ESPN_SCOREBOARD_BASE_URL = "https://site.api.espn.com/apis/site/v2/sports/soccer"
LIVERPOOL_NEWS_URL = "https://www.liverpool.no/lfc/"
MET_LOCATIONFORECAST_URL = "https://api.met.no/weatherapi/locationforecast/2.0/compact"
USER_AGENT = "privat-tekst-tv/0.1 (+private household prototype)"
NEWS_BODY_MAX_CHARS = 560


@dataclass
class SourceItem:
    title: str
    summary: str
    source: str
    url: str | None = None
    published_at: datetime | None = None
    body: str | None = None


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate pages.json for tekst-tv.")
    parser.add_argument(
        "--output",
        default="tekst-tv/pages.json",
        help="Path to write generated JSON feed.",
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Skip network fetches and use local sample data.",
    )
    parser.add_argument(
        "--watch",
        action="store_true",
        help="Keep regenerating the feed until stopped.",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=300,
        help="Seconds between regenerations when --watch is used.",
    )
    args = parser.parse_args()

    while True:
        generate_feed(args)
        if not args.watch:
            break
        print(f"Sleeping {args.interval} seconds before next update")
        time.sleep(args.interval)


def generate_feed(args: argparse.Namespace) -> None:
    domestic_items = [] if args.offline else fetch_domestic_news_items()
    local_items = [] if args.offline else fetch_local_news_items()
    world_items = [] if args.offline else fetch_rss_items(NRK_URIX_RSS_URL, source="NRK Urix")
    sports_data = SportsData.empty() if args.offline else fetch_sports_data()
    weather_forecasts = [] if args.offline else fetch_weather_forecasts()
    if not domestic_items:
        domestic_items = fallback_news_items()
    if not local_items:
        local_items = fallback_local_items()
    if world_items:
        pass
    elif os.environ.get("OPENAI_API_KEY") and not args.offline:
        world_items = rewrite_world_items_in_norwegian(fetch_rss_items(BBC_WORLD_RSS_URL, source="BBC")[:7])
    else:
        world_items = fallback_world_items()

    if world_items and world_items[0].source == "BBC":
        world_items = rewrite_world_items_in_norwegian(world_items[:7])

    if not args.offline:
        domestic_items = enrich_items_with_article_text(domestic_items[:9])
        local_items = enrich_items_with_article_text(local_items[:8])
        world_items = enrich_items_with_article_text(world_items[:7])

    feed = build_feed(domestic_items, local_items, world_items, sports_data, weather_forecasts)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(feed, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {output_path} with {count_pages(feed)} pages")


@dataclass
class LeagueTable:
    title: str
    source: str
    rows: list[dict]


@dataclass
class LeagueEvents:
    title: str
    source: str
    rows: list[dict]
    round_name: str | None = None


@dataclass
class PlayerStat:
    player: str
    team: str
    value: int
    competition: str = ""


@dataclass
class LeagueLeaders:
    title: str
    source: str
    goals: list[PlayerStat]
    assists: list[PlayerStat]


@dataclass
class SportsData:
    sports_news: list[SourceItem]
    premier_league_table: LeagueTable | None
    eliteserien_table: LeagueTable | None
    champions_league_table: LeagueTable | None
    premier_league_leaders: LeagueLeaders | None
    eliteserien_leaders: LeagueLeaders | None
    champions_league_leaders: LeagueLeaders | None
    liverpool_premier_league_leaders: LeagueLeaders | None
    liverpool_all_leaders: LeagueLeaders | None
    premier_league_events: LeagueEvents | None
    eliteserien_events: LeagueEvents | None
    champions_league_events: LeagueEvents | None
    europa_league_events: LeagueEvents | None
    fa_cup_events: LeagueEvents | None
    league_cup_events: LeagueEvents | None
    premier_league_results: LeagueEvents | None
    eliteserien_results: LeagueEvents | None
    champions_league_results: LeagueEvents | None
    europa_league_results: LeagueEvents | None
    fa_cup_results: LeagueEvents | None
    league_cup_results: LeagueEvents | None
    liverpool_news: list[SourceItem]

    @staticmethod
    def empty() -> "SportsData":
        return SportsData(
            sports_news=[],
            premier_league_table=None,
            eliteserien_table=None,
            champions_league_table=None,
            premier_league_leaders=None,
            eliteserien_leaders=None,
            champions_league_leaders=None,
            liverpool_premier_league_leaders=None,
            liverpool_all_leaders=None,
            premier_league_events=None,
            eliteserien_events=None,
            champions_league_events=None,
            europa_league_events=None,
            fa_cup_events=None,
            league_cup_events=None,
            premier_league_results=None,
            eliteserien_results=None,
            champions_league_results=None,
            europa_league_results=None,
            fa_cup_results=None,
            league_cup_results=None,
            liverpool_news=[],
        )


@dataclass
class WeatherPlace:
    name: str
    latitude: float
    longitude: float
    region: str


@dataclass
class WeatherForecast:
    place: WeatherPlace
    source: str
    summary: str
    details: str
    days: list[str]


def fetch_rss_items(url: str, source: str, limit: int = 12) -> list[SourceItem]:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT},
    )

    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            data = response.read()
    except (urllib.error.URLError, TimeoutError) as error:
        print(f"{source} RSS fetch failed: {error}")
        return []

    try:
        root = ET.fromstring(data)
    except ET.ParseError as error:
        print(f"{source} RSS parse failed: {error}")
        return []

    items: list[SourceItem] = []
    for item in root.findall("./channel/item")[:limit]:
        title = clean_text(item.findtext("title"))
        summary = clean_text(item.findtext("description"))
        link = clean_text(item.findtext("link")) or None
        published_at = parse_rss_date(item.findtext("pubDate"))

        if not title or not summary:
            continue

        items.append(
            SourceItem(
                title=title,
                summary=summary,
                source=source,
                url=link,
                published_at=published_at,
            )
        )

    return items


def fetch_local_news_items(limit: int = 8) -> list[SourceItem]:
    items = []
    for url, source in [
        (NRK_TROMS_FINNMARK_RSS_URL, "NRK Troms og Finnmark"),
        (NRK_TROMS_RSS_URL, "NRK Troms"),
        (NRK_FINNMARK_RSS_URL, "NRK Finnmark"),
    ]:
        items.extend(fetch_rss_items(url, source=source, limit=limit))

    seen: set[str] = set()
    unique_items: list[SourceItem] = []
    for item in sorted(items, key=lambda value: value.published_at or datetime.min, reverse=True):
        key = item.url or item.title
        if key in seen:
            continue
        seen.add(key)
        unique_items.append(item)
        if len(unique_items) == limit:
            break

    return unique_items


def fetch_domestic_news_items(limit: int = 12) -> list[SourceItem]:
    items = fetch_rss_items(NRK_NORGE_RSS_URL, source="NRK Norge", limit=limit)
    if not items:
        items = fetch_rss_items(NRK_LATEST_RSS_URL, source="NRK", limit=limit * 2)

    domestic_items = [item for item in items if not looks_like_world_news(item)]
    return domestic_items[:limit]


def looks_like_world_news(item: SourceItem) -> bool:
    text = f"{item.title} {item.summary}".casefold()
    markers = [
        "usa",
        "trump",
        "rubio",
        "nato",
        "iran",
        "israel",
        "gaza",
        "russland",
        "ukraina",
        "zelenskyj",
        "taiwan",
        "kina",
    ]
    return any(marker in text for marker in markers)


def fetch_sports_data() -> SportsData:
    premier_league_leaders = fetch_espn_leaders("eng.1", "Premier League")
    eliteserien_leaders = fetch_espn_leaders("nor.1", "Eliteserien")
    champions_league_leaders = fetch_espn_leaders("uefa.champions", "Champions League")
    europa_league_leaders = fetch_espn_leaders("uefa.europa", "Europa League")
    fa_cup_leaders = fetch_espn_leaders("eng.fa", "FA-cupen")
    league_cup_leaders = fetch_espn_leaders("eng.league_cup", "Ligacupen")
    liverpool_premier_league_leaders = filter_team_leaders(
        premier_league_leaders,
        team_name="Liverpool",
        title="Liverpool PL",
    )
    liverpool_all_leaders = combine_team_leaders(
        [
            premier_league_leaders,
            champions_league_leaders,
            europa_league_leaders,
            fa_cup_leaders,
            league_cup_leaders,
        ],
        team_name="Liverpool",
        title="Liverpool alle turneringer",
    )

    return SportsData(
        sports_news=fetch_sports_news_items(),
        premier_league_table=fetch_espn_table(
            league_code="eng.1",
            title="Premier League",
        ),
        eliteserien_table=fetch_espn_table(
            league_code="nor.1",
            title="Eliteserien",
        ),
        champions_league_table=fetch_espn_table(
            league_code="uefa.champions",
            title="Champions League",
        ),
        premier_league_leaders=premier_league_leaders,
        eliteserien_leaders=eliteserien_leaders,
        champions_league_leaders=champions_league_leaders,
        liverpool_premier_league_leaders=liverpool_premier_league_leaders,
        liverpool_all_leaders=liverpool_all_leaders,
        premier_league_events=fetch_sportsdb_events(
            league_id="4328",
            season="2025-2026",
            title="Premier League",
        ),
        eliteserien_events=fetch_sportsdb_events(
            league_id="4358",
            season="2026",
            title="Eliteserien",
        ),
        champions_league_events=fetch_sportsdb_events(
            league_id="4480",
            season="2025-2026",
            title="Champions League",
        ),
        europa_league_events=fetch_sportsdb_events(
            league_id="4481",
            season="2025-2026",
            title="Europa League",
        ),
        fa_cup_events=fetch_sportsdb_events(
            league_id="4482",
            season="2025-2026",
            title="FA-cupen",
        ),
        league_cup_events=fetch_sportsdb_events(
            league_id="4570",
            season="2025-2026",
            title="Ligacupen",
        ),
        premier_league_results=fetch_espn_results(
            league_code="eng.1",
            title="Premier League",
            expected_matches=10,
        ) or fetch_sportsdb_results(
            league_id="4328",
            season="2025-2026",
            title="Premier League",
        ),
        eliteserien_results=fetch_espn_results(
            league_code="nor.1",
            title="Eliteserien",
            expected_matches=8,
        ) or fetch_sportsdb_results(
            league_id="4358",
            season="2026",
            title="Eliteserien",
        ),
        champions_league_results=fetch_espn_results(
            league_code="uefa.champions",
            title="Champions League",
            expected_matches=4,
        ) or fetch_sportsdb_results(
            league_id="4480",
            season="2025-2026",
            title="Champions League",
        ),
        europa_league_results=fetch_espn_results(
            league_code="uefa.europa",
            title="Europa League",
            cluster_days=7,
        ) or fetch_sportsdb_results(
            league_id="4481",
            season="2025-2026",
            title="Europa League",
        ),
        fa_cup_results=fetch_espn_results(
            league_code="eng.fa",
            title="FA-cupen",
            cluster_days=7,
        ) or fetch_sportsdb_results(
            league_id="4482",
            season="2025-2026",
            title="FA-cupen",
        ),
        league_cup_results=fetch_espn_results(
            league_code="eng.league_cup",
            title="Ligacupen",
            expected_matches=1,
            lookback_days=120,
            cluster_days=7,
        ) or fetch_sportsdb_results(
            league_id="4570",
            season="2025-2026",
            title="Ligacupen",
        ),
        liverpool_news=fetch_liverpool_news(),
    )


def fetch_sports_news_items(limit: int = 8) -> list[SourceItem]:
    items = []
    for url, source in [
        (NRK_SPORT_TOP_RSS_URL, "NRK Sport"),
        (NRK_SPORT_LATEST_RSS_URL, "NRK Sport"),
    ]:
        items.extend(fetch_rss_items(url, source=source, limit=limit))

    seen: set[str] = set()
    unique_items: list[SourceItem] = []
    for item in sorted(items, key=lambda value: value.published_at or datetime.min, reverse=True):
        key = item.url or item.title
        if key in seen:
            continue
        seen.add(key)
        unique_items.append(item)
        if len(unique_items) == limit:
            break

    return unique_items


def fetch_weather_forecasts() -> list[WeatherForecast]:
    forecasts: list[WeatherForecast] = []
    for place in weather_places():
        forecast = fetch_met_forecast(place)
        if forecast:
            forecasts.append(forecast)
        else:
            forecasts.append(
                WeatherForecast(
                    place=place,
                    source="Generator",
                    summary="Værvarsel kunne ikke hentes akkurat nå.",
                    details="Siden fylles automatisk når MET/Yr-kilden svarer igjen.",
                    days=[],
                )
            )
    return forecasts


def weather_places() -> list[WeatherPlace]:
    return [
        WeatherPlace("Alta", 69.9689, 23.2716, "Norge"),
        WeatherPlace("Børselv", 70.3151, 25.5417, "Norge"),
        WeatherPlace("Čáhppiljohka", 70.0937, 24.9608, "Norge"),
        WeatherPlace("Heimdal", 63.3507, 10.3505, "Norge"),
        WeatherPlace("Bø", 59.4130, 9.0693, "Norge"),
        WeatherPlace("Kristiansand", 58.1467, 7.9956, "Norge"),
        WeatherPlace("Oslo", 59.9139, 10.7522, "Norge"),
        WeatherPlace("Svalbard", 78.2232, 15.6469, "Norge"),
        WeatherPlace("Os", 60.1857, 5.4708, "Norge"),
        WeatherPlace("Finnsnes", 69.2296, 17.9811, "Norge"),
        WeatherPlace("Torrevieja", 37.9787, -0.6822, "Europa"),
        WeatherPlace("London", 51.5072, -0.1276, "Europa"),
        WeatherPlace("Paris", 48.8566, 2.3522, "Europa"),
        WeatherPlace("Berlin", 52.5200, 13.4050, "Europa"),
        WeatherPlace("Roma", 41.9028, 12.4964, "Europa"),
    ]


def fetch_met_forecast(place: WeatherPlace) -> WeatherForecast | None:
    url = f"{MET_LOCATIONFORECAST_URL}?lat={place.latitude:.4f}&lon={place.longitude:.4f}"
    data = fetch_json(url)
    timeseries = data.get("properties", {}).get("timeseries") if isinstance(data, dict) else None
    if not timeseries:
        return None

    current = timeseries[0]
    current_details = current.get("data", {}).get("instant", {}).get("details", {})
    temperature = current_details.get("air_temperature")
    wind = current_details.get("wind_speed")
    symbol = forecast_symbol(current)
    precipitation = forecast_precipitation(timeseries)
    tomorrow = forecast_next_day(timeseries)
    coming_days = forecast_days(timeseries)

    summary_parts = []
    if symbol:
        summary_parts.append(symbol)
    if temperature is not None:
        summary_parts.append(f"{round(float(temperature))} grader")
    if wind is not None:
        summary_parts.append(f"vind {round(float(wind))} m/s")

    summary = ", ".join(summary_parts).capitalize() if summary_parts else "Varsel fra MET/Yr."
    details = []
    if precipitation is not None:
        details.append(f"Nedbør neste 6 timer: {precipitation:.1f} mm.")
    if tomorrow:
        details.append(tomorrow)
    if coming_days:
        details.append("Kommende dager:")
        details.extend(coming_days[:5])
    details.append("Værdata fra MET Norway / Yr.")

    return WeatherForecast(
        place=place,
        source="MET/Yr",
        summary=summary,
        details="\n".join(details),
        days=coming_days,
    )


def forecast_symbol(entry: dict) -> str:
    for key in ["next_1_hours", "next_6_hours", "next_12_hours"]:
        symbol_code = entry.get("data", {}).get(key, {}).get("summary", {}).get("symbol_code")
        if symbol_code:
            return describe_symbol(symbol_code)
    return ""


def forecast_precipitation(timeseries: list[dict]) -> float | None:
    first = timeseries[0] if timeseries else {}
    for key in ["next_6_hours", "next_1_hours", "next_12_hours"]:
        amount = first.get("data", {}).get(key, {}).get("details", {}).get("precipitation_amount")
        if amount is not None:
            return float(amount)
    return None


def forecast_next_day(timeseries: list[dict]) -> str:
    if len(timeseries) < 8:
        return ""
    temperatures = []
    precipitation = 0.0
    for entry in timeseries[1:9]:
        details = entry.get("data", {}).get("instant", {}).get("details", {})
        temperature = details.get("air_temperature")
        if temperature is not None:
            temperatures.append(float(temperature))
        precipitation_amount = entry.get("data", {}).get("next_6_hours", {}).get("details", {}).get("precipitation_amount")
        if precipitation_amount is not None:
            precipitation += float(precipitation_amount)

    if not temperatures:
        return ""
    return (
        f"Neste døgn: {round(min(temperatures))} til {round(max(temperatures))} grader, "
        f"omtrent {precipitation:.1f} mm nedbør."
    )


def forecast_days(timeseries: list[dict], max_days: int = 5) -> list[str]:
    grouped: dict[str, list[dict]] = {}
    today = datetime.now().date().isoformat()

    for entry in timeseries:
        time_value = entry.get("time")
        if not time_value:
            continue
        try:
            parsed = datetime.fromisoformat(time_value.replace("Z", "+00:00"))
        except ValueError:
            continue

        day_key = parsed.date().isoformat()
        if day_key == today:
            continue
        grouped.setdefault(day_key, []).append(entry)

    lines: list[str] = []
    for day_key in sorted(grouped.keys())[:max_days]:
        entries = grouped[day_key]
        temperatures = []
        precipitation = 0.0
        symbols: list[str] = []

        for entry in entries:
            details = entry.get("data", {}).get("instant", {}).get("details", {})
            temperature = details.get("air_temperature")
            if temperature is not None:
                temperatures.append(float(temperature))

            amount = (
                entry.get("data", {})
                .get("next_6_hours", {})
                .get("details", {})
                .get("precipitation_amount")
            )
            if amount is not None:
                precipitation += float(amount)

            symbol = forecast_symbol(entry)
            if symbol and symbol not in symbols:
                symbols.append(symbol)

        if not temperatures:
            continue

        day_name = format_day_name(day_key)
        symbol_text = symbols[0] if symbols else "varierende vær"
        lines.append(
            f"{day_name}: {symbol_text}, {round(min(temperatures))}-{round(max(temperatures))} grader, "
            f"{precipitation:.1f} mm nedbør."
        )

    return lines


def format_day_name(day_key: str) -> str:
    try:
        parsed = datetime.fromisoformat(day_key)
    except ValueError:
        return day_key

    names = [
        "mandag",
        "tirsdag",
        "onsdag",
        "torsdag",
        "fredag",
        "lørdag",
        "søndag",
    ]
    return f"{names[parsed.weekday()].capitalize()} {parsed.strftime('%d.%m')}"


def describe_symbol(symbol_code: str) -> str:
    base = symbol_code.split("_")[0]
    descriptions = {
        "clearsky": "klart",
        "cloudy": "skyet",
        "fair": "pent vær",
        "fog": "tåke",
        "heavyrain": "kraftig regn",
        "heavyrainandthunder": "kraftig regn og torden",
        "heavysleet": "kraftig sludd",
        "heavysnow": "kraftig snø",
        "lightrain": "lett regn",
        "lightrainandthunder": "lett regn og torden",
        "lightsleet": "lett sludd",
        "lightsnow": "lett snø",
        "partlycloudy": "delvis skyet",
        "rain": "regn",
        "rainandthunder": "regn og torden",
        "sleet": "sludd",
        "snow": "snø",
    }
    return descriptions.get(base, base.replace("_", " "))


def fetch_espn_table(league_code: str, title: str) -> LeagueTable | None:
    url = f"{ESPN_STANDINGS_BASE_URL}/{league_code}/standings?region=us&lang=en"
    data = fetch_json(url)
    children = data.get("children") if isinstance(data, dict) else None
    if not children:
        return None

    entries = children[0].get("standings", {}).get("entries", [])
    rows = []
    for entry in entries:
        stats = {stat.get("name"): stat.get("displayValue") for stat in entry.get("stats", [])}
        rows.append(
            {
                "intRank": stats.get("rank", ""),
                "strTeam": entry.get("team", {}).get("displayName", ""),
                "intPlayed": stats.get("gamesPlayed", ""),
                "intWin": stats.get("wins", ""),
                "intDraw": stats.get("ties", ""),
                "intLoss": stats.get("losses", ""),
                "intGoalDifference": stats.get("pointDifferential", ""),
                "intPoints": stats.get("points", ""),
            }
        )

    if not rows:
        return None
    return LeagueTable(title=title, source="ESPN", rows=rows)


def fetch_espn_leaders(league_code: str, title: str) -> LeagueLeaders | None:
    url = f"{ESPN_SCOREBOARD_BASE_URL}/{league_code}/statistics"
    data = fetch_json(url)
    stats = data.get("stats") if isinstance(data, dict) else None
    if not stats:
        return None

    goals: list[PlayerStat] = []
    assists: list[PlayerStat] = []
    for stat in stats:
        name = clean_text(stat.get("name"))
        leaders = stat.get("leaders") or []
        if name == "goalsLeaders":
            goals = parse_espn_player_stats(leaders, "Goals", title)
        elif name == "assistsLeaders":
            assists = parse_espn_player_stats(leaders, "Assists", title)

    if not goals and not assists:
        return None
    return LeagueLeaders(title=title, source="ESPN", goals=goals, assists=assists)


def parse_espn_player_stats(leaders: list[dict], label: str, competition: str) -> list[PlayerStat]:
    rows: list[PlayerStat] = []
    for leader in leaders:
        athlete = leader.get("athlete") or {}
        team = leader.get("team") or athlete.get("team") or {}
        player_name = clean_text(athlete.get("displayName") or athlete.get("name"))
        team_name = clean_text(team.get("displayName") or team.get("name"))
        value = extract_stat_value(clean_text(leader.get("displayValue")), label)
        if value is None:
            raw_value = leader.get("value")
            value = int(raw_value) if isinstance(raw_value, (int, float)) else None
        if player_name and value is not None:
            rows.append(PlayerStat(player=player_name, team=team_name, value=value, competition=competition))
    return rows


def extract_stat_value(display_value: str, label: str) -> int | None:
    match = re.search(rf"{re.escape(label)}:\s*(\d+)", display_value)
    if match:
        return int(match.group(1))
    return None


def filter_team_leaders(leaders: LeagueLeaders | None, team_name: str, title: str) -> LeagueLeaders | None:
    if not leaders:
        return None
    needle = team_name.casefold()
    goals = [row for row in leaders.goals if needle in row.team.casefold()]
    assists = [row for row in leaders.assists if needle in row.team.casefold()]
    if not goals and not assists:
        return None
    return LeagueLeaders(title=title, source=leaders.source, goals=goals, assists=assists)


def combine_team_leaders(
    leader_sets: list[LeagueLeaders | None],
    team_name: str,
    title: str,
) -> LeagueLeaders | None:
    goal_totals: dict[str, PlayerStat] = {}
    assist_totals: dict[str, PlayerStat] = {}
    for leaders in leader_sets:
        if not leaders:
            continue
        add_team_stats(goal_totals, leaders.goals, team_name)
        add_team_stats(assist_totals, leaders.assists, team_name)

    goals = sorted(goal_totals.values(), key=lambda row: (-row.value, row.player))
    assists = sorted(assist_totals.values(), key=lambda row: (-row.value, row.player))
    if not goals and not assists:
        return None
    return LeagueLeaders(title=title, source="ESPN", goals=goals, assists=assists)


def add_team_stats(totals: dict[str, PlayerStat], rows: list[PlayerStat], team_name: str) -> None:
    needle = team_name.casefold()
    for row in rows:
        if needle not in row.team.casefold():
            continue
        current = totals.get(row.player)
        if current:
            current.value += row.value
        else:
            totals[row.player] = PlayerStat(player=row.player, team=row.team, value=row.value, competition="Flere")


def fetch_sportsdb_table(league_id: str, season: str, title: str) -> LeagueTable | None:
    url = f"{SPORTSDB_BASE_URL}/lookuptable.php?l={league_id}&s={season}"
    data = fetch_json(url)
    rows = data.get("table") if isinstance(data, dict) else None
    if not rows:
        return None
    return LeagueTable(title=title, source="TheSportsDB", rows=rows)


def fetch_sportsdb_events(league_id: str, season: str, title: str) -> LeagueEvents | None:
    next_url = f"{SPORTSDB_BASE_URL}/eventsnextleague.php?id={league_id}"
    next_data = fetch_json(next_url)
    next_rows = next_data.get("events") if isinstance(next_data, dict) else None
    next_round = next_rows[0].get("intRound") if next_rows else None
    if next_round:
        round_url = f"{SPORTSDB_BASE_URL}/eventsround.php?id={league_id}&r={next_round}&s={season}"
        round_data = fetch_json(round_url)
        round_rows = round_data.get("events") if isinstance(round_data, dict) else None
        if round_rows:
            return LeagueEvents(
                title=title,
                source="TheSportsDB",
                rows=sorted(round_rows, key=event_sort_key),
                round_name=f"Runde {next_round}",
            )

    url = f"{SPORTSDB_BASE_URL}/eventsseason.php?id={league_id}&s={season}"
    data = fetch_json(url)
    rows = data.get("events") if isinstance(data, dict) else None
    if not rows:
        return None
    first_round = rows[0].get("intRound")
    if first_round:
        rows = [row for row in rows if row.get("intRound") == first_round]
    return LeagueEvents(
        title=title,
        source="TheSportsDB",
        rows=sorted(rows, key=event_sort_key),
        round_name=f"Runde {first_round}" if first_round else None,
    )


def fetch_sportsdb_results(league_id: str, season: str, title: str) -> LeagueEvents | None:
    url = f"{SPORTSDB_BASE_URL}/eventsseason.php?id={league_id}&s={season}"
    data = fetch_json(url)
    rows = data.get("events") if isinstance(data, dict) else None
    if not rows:
        return None

    completed_rows = [
        row for row in rows
        if clean_text(row.get("intHomeScore")) and clean_text(row.get("intAwayScore"))
    ]
    if not completed_rows:
        return None

    latest_round = latest_completed_round(completed_rows)
    if latest_round:
        round_rows = [row for row in completed_rows if clean_text(row.get("intRound")) == latest_round]
    else:
        round_rows = completed_rows[:10]

    return LeagueEvents(
        title=title,
        source="TheSportsDB",
        rows=sorted(round_rows, key=event_sort_key),
        round_name=f"Runde {latest_round}" if latest_round else "Seneste resultater",
    )


def fetch_espn_results(
    league_code: str,
    title: str,
    expected_matches: int | None = None,
    cluster_days: int = 6,
    lookback_days: int = 45,
) -> LeagueEvents | None:
    end_date = datetime.now()
    start_date = end_date - timedelta(days=lookback_days)
    dates = f"{start_date.strftime('%Y%m%d')}-{end_date.strftime('%Y%m%d')}"
    url = f"{ESPN_SCOREBOARD_BASE_URL}/{league_code}/scoreboard?dates={dates}&limit=100"
    data = fetch_json(url)
    events = data.get("events") if isinstance(data, dict) else None
    if not events:
        return None

    rows = []
    for event in events:
        row = espn_result_row(event)
        if row:
            rows.append(row)
    if not rows:
        return None

    rows = sorted(rows, key=event_sort_key)
    if expected_matches:
        selected_rows = rows[-expected_matches:]
    else:
        latest_date = parse_event_date(rows[-1].get("dateEvent"))
        selected_rows = [
            row for row in rows
            if latest_date and parse_event_date(row.get("dateEvent"))
            and 0 <= (latest_date - parse_event_date(row.get("dateEvent"))).days <= cluster_days
        ]
        if not selected_rows:
            selected_rows = [rows[-1]]

    return LeagueEvents(
        title=title,
        source="ESPN",
        rows=annotate_aggregate_scores(sorted(selected_rows, key=event_sort_key)),
        round_name=result_period_name(selected_rows),
    )


def espn_result_row(event: dict) -> dict | None:
    competition = (event.get("competitions") or [{}])[0]
    status_type = competition.get("status", {}).get("type", {})
    if not status_type.get("completed"):
        return None

    competitors = competition.get("competitors") or []
    home = next((item for item in competitors if item.get("homeAway") == "home"), None)
    away = next((item for item in competitors if item.get("homeAway") == "away"), None)
    if not home or not away:
        return None

    home_score = clean_text(home.get("score"))
    away_score = clean_text(away.get("score"))
    if not home_score or not away_score:
        return None

    return {
        "strTimestamp": clean_text(event.get("date")),
        "dateEvent": clean_text(event.get("date", ""))[:10],
        "strTime": clean_text(event.get("date", ""))[11:16],
        "strEvent": clean_text(event.get("name")),
        "strHomeTeam": clean_text(home.get("team", {}).get("displayName")),
        "strAwayTeam": clean_text(away.get("team", {}).get("displayName")),
        "intHomeScore": home_score,
        "intAwayScore": away_score,
    }


def annotate_aggregate_scores(rows: list[dict]) -> list[dict]:
    grouped: dict[tuple[str, str], list[dict]] = {}
    for row in rows:
        home_team = clean_text(row.get("strHomeTeam"))
        away_team = clean_text(row.get("strAwayTeam"))
        if not home_team or not away_team:
            continue
        grouped.setdefault(tuple(sorted([home_team, away_team])), []).append(row)

    for teams, pair_rows in grouped.items():
        if len(pair_rows) != 2:
            continue
        totals = {team: 0 for team in teams}
        for row in pair_rows:
            home_team = clean_text(row.get("strHomeTeam"))
            away_team = clean_text(row.get("strAwayTeam"))
            try:
                totals[home_team] += int(clean_text(row.get("intHomeScore")))
                totals[away_team] += int(clean_text(row.get("intAwayScore")))
            except ValueError:
                continue
        first_team, second_team = teams
        aggregate = f"samlet {first_team} {totals[first_team]}-{totals[second_team]} {second_team}"
        pair_rows[-1]["strAggregate"] = aggregate
    return rows


def parse_event_date(value: str | None) -> datetime | None:
    text = clean_text(value)
    if not text:
        return None
    try:
        return datetime.fromisoformat(text[:10])
    except ValueError:
        return None


def result_period_name(rows: list[dict]) -> str:
    dates = [parse_event_date(row.get("dateEvent")) for row in rows]
    dates = [date for date in dates if date]
    if not dates:
        return "Seneste resultater"
    first_date = min(dates)
    last_date = max(dates)
    if first_date.date() == last_date.date():
        return f"Spilt {last_date.strftime('%d.%m')}"
    return f"Spilt {first_date.strftime('%d.%m')}-{last_date.strftime('%d.%m')}"


def latest_completed_round(rows: list[dict]) -> str | None:
    round_values = [clean_text(row.get("intRound")) for row in rows]
    round_values = [value for value in round_values if value]
    if not round_values:
        return None

    numeric_rounds = []
    for value in round_values:
        try:
            numeric_rounds.append((int(value), value))
        except ValueError:
            continue

    if numeric_rounds:
        return max(numeric_rounds, key=lambda item: item[0])[1]
    return round_values[0]


def event_sort_key(row: dict) -> tuple[str, str, str]:
    return (
        clean_text(row.get("dateEvent")),
        clean_text(row.get("strTime")),
        clean_text(row.get("strEvent")),
    )


def fetch_liverpool_news(limit: int = 5) -> list[SourceItem]:
    try:
        request = urllib.request.Request(LIVERPOOL_NEWS_URL, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(request, timeout=15) as response:
            html_text = response.read().decode("utf-8", "replace")
    except (urllib.error.URLError, TimeoutError) as error:
        print(f"Liverpool news fetch failed: {error}")
        return []

    links = []
    for href in re.findall(r'href="(/lfc/\d+/\d+/[^"]+/)"', html_text):
        if href not in links:
            links.append(href)
        if len(links) == limit:
            break

    items: list[SourceItem] = []
    for href in links:
        item = fetch_liverpool_article(f"https://www.liverpool.no{href}")
        if item:
            items.append(item)

    return items


def fetch_liverpool_article(url: str) -> SourceItem | None:
    try:
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(request, timeout=12) as response:
            html_text = response.read().decode("utf-8", "replace")
    except (urllib.error.URLError, TimeoutError) as error:
        print(f"Liverpool article fetch failed: {error}")
        return None

    title = clean_liverpool_title(extract_meta(html_text, "og:title"))
    description = extract_meta(html_text, "og:description")
    published_at = extract_article_datetime(html_text)
    if not title or not description:
        return None

    return SourceItem(
        title=title,
        summary=description,
        source="Liverpool.no",
        url=url,
        published_at=published_at,
    )


def clean_liverpool_title(title: str) -> str:
    title = re.sub(r"\s*\|\s*Liverpool FC Supporters Club Norway\s*$", "", title)
    title = title.strip()
    if title.startswith("«") and title.endswith("»"):
        title = title[1:-1].strip()
    return title


def extract_meta(html_text: str, property_name: str) -> str:
    pattern = rf'<meta[^>]+property="{re.escape(property_name)}"[^>]+content="([^"]*)"'
    match = re.search(pattern, html_text)
    if not match:
        pattern = rf'<meta[^>]+content="([^"]*)"[^>]+property="{re.escape(property_name)}"'
        match = re.search(pattern, html_text)
    return clean_text(match.group(1)) if match else ""


def extract_article_datetime(html_text: str) -> datetime | None:
    value = extract_meta(html_text, "article:published_time")
    if not value:
        return None
    for format_string in ["%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S%z"]:
        try:
            return datetime.strptime(value, format_string)
        except ValueError:
            continue
    return None


def fetch_json(url: str) -> dict:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            return json.loads(response.read())
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
        print(f"JSON fetch failed for {url}: {error}")
        return {}


def enrich_items_with_article_text(items: list[SourceItem], max_items: int | None = None) -> list[SourceItem]:
    enriched: list[SourceItem] = []
    for index, item in enumerate(items):
        if max_items is not None and index >= max_items:
            enriched.append(item)
            continue
        if item.body or is_roster_story(item) or not item.url or "nrk.no" not in item.url:
            enriched.append(item)
            continue

        body = fetch_nrk_article_body(item.url)
        if body:
            enriched.append(
                SourceItem(
                    title=item.title,
                    summary=item.summary,
                    source=item.source,
                    url=item.url,
                    published_at=item.published_at,
                    body=body,
                )
            )
        else:
            enriched.append(item)

    return enriched


def fetch_nrk_article_body(url: str) -> str:
    try:
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(request, timeout=12) as response:
            html_text = response.read().decode("utf-8", "replace")
    except (urllib.error.URLError, TimeoutError) as error:
        print(f"NRK article fetch failed: {error}")
        return ""

    paragraphs = extract_article_paragraphs(html_text)
    if not paragraphs:
        return ""

    body = " ".join(paragraphs[:6])
    return wrap_text(body, width=95)


def extract_article_paragraphs(html_text: str) -> list[str]:
    paragraphs: list[str] = []
    for match in re.finditer(r"<p[^>]*>(.*?)</p>", html_text, re.S):
        text = clean_text(match.group(1))
        if should_skip_article_paragraph(text):
            continue
        paragraphs.append(text)
        if len(paragraphs) >= 9:
            break
    return paragraphs


def should_skip_article_paragraph(text: str) -> bool:
    if len(text) < 45:
        return True
    lowercased = text.lower()
    blocked_fragments = [
        ":where(body)",
        "du trenger javascript",
        "sportsnyheter her får du",
        "her får du de siste sportsnyhetene",
        "siste sportsnyhetene fra nrk",
        "kommentar",
        "les også",
        "følg saken",
        "se video",
        "hør podkast",
        "er du der det skjer",
        "ta kontakt på",
    ]
    return any(fragment in lowercased for fragment in blocked_fragments)


def build_feed(
    domestic_items: list[SourceItem],
    local_items: list[SourceItem],
    world_items: list[SourceItem],
    sports_data: SportsData,
    weather_forecasts: list[WeatherForecast],
) -> dict:
    now = datetime.now().strftime("%d.%m kl. %H:%M")
    domestic_page_items = exclude_duplicate_news_items(
        domestic_items,
        local_items + world_items,
    )
    domestic_pages = make_news_pages(
        start_page=110,
        title="Innland",
        items=domestic_page_items[:9],
    )
    world_pages = make_news_pages(
        start_page=120,
        title="Utland",
        items=world_items[:7],
    )
    local_pages = make_news_pages(
        start_page=130,
        title="Lokal",
        items=local_items[:8],
    )

    return {
        "updated": f"Oppdatert {now}",
        "sections": [
            make_front_page(
                domestic_items=domestic_items,
                world_items=world_items,
                local_items=local_items,
                sports_data=sports_data,
                weather_forecasts=weather_forecasts,
            ),
            {
                "id": "domestic",
                "title": "Innland",
                "startPage": "110",
                "colorName": "cyan",
                "pages": domestic_pages,
            },
            {
                "id": "local",
                "title": "Lokal",
                "startPage": "130",
                "colorName": "magenta",
                "pages": local_pages,
            },
            {
                "id": "world",
                "title": "Utland",
                "startPage": "120",
                "colorName": "green",
                "pages": world_pages,
            },
            make_sport_section(sports_data),
            make_matches_section(sports_data),
            make_results_section(sports_data),
            make_tables_section(sports_data),
            make_stats_section(sports_data),
            make_weather_section(weather_forecasts),
        ],
    }


def make_front_page(
    domestic_items: list[SourceItem],
    world_items: list[SourceItem],
    local_items: list[SourceItem],
    sports_data: SportsData,
    weather_forecasts: list[WeatherForecast],
) -> dict:
    return {
        "id": "front",
        "title": "Forside",
        "startPage": "100",
        "colorName": "yellow",
        "pages": [
            {
                "id": "100",
                "number": "100",
                "title": "Forside",
                "lines": [
                    make_line(
                        "Mors tekst-TV",
                        color="yellow",
                        important=True,
                    ),
                    make_line(
                        "Siste nytt",
                        body=front_news_summary(domestic_items, world_items, local_items),
                        color="cyan",
                    ),
                    make_line(
                        "Neste kamp",
                        front_liverpool_match_summary(sports_data),
                        color="green",
                    ),
                    make_line(
                        "Været",
                        body=front_weather_summary(weather_forecasts),
                        color="yellow",
                    ),
                ],
            }
        ],
    }


def front_news_summary(
    domestic_items: list[SourceItem],
    world_items: list[SourceItem],
    local_items: list[SourceItem],
) -> str:
    local_title = first_unique_title(local_items, set())
    world_title = first_unique_title(world_items, {front_title_key(local_title)})
    domestic_title = first_unique_title(
        domestic_items,
        {front_title_key(local_title), front_title_key(world_title)},
    )

    return "\n".join(
        [
            f"110 {domestic_title}",
            f"130 {local_title}",
            f"120 {world_title}",
        ]
    )


def front_sport_summary(sports_data: SportsData) -> str:
    if sports_data.premier_league_events and sports_data.premier_league_events.rows:
        first_event = clean_text(sports_data.premier_league_events.rows[0].get("strEvent"))
        return f"Neste PL-runde: {first_event}"
    if sports_data.liverpool_news:
        return f"Liverpool: {sports_data.liverpool_news[0].title}"
    return "Sportssidene er oppdatert."


def front_liverpool_match_summary(sports_data: SportsData) -> str:
    event = find_next_liverpool_event(sports_data)
    if event:
        timestamp = format_timestamp(event.get("strTimestamp"))
        event_name = clean_text(event.get("strEvent"))
        league_name = clean_text(event.get("strLeague"))
        suffix = f" ({league_name})" if league_name else ""
        return f"{timestamp}  {event_name}{suffix}" if timestamp else f"{event_name}{suffix}"
    return "Liverpool-kamp ikke funnet i kommende kamper."


def find_next_liverpool_event(sports_data: SportsData) -> dict | None:
    candidates: list[dict] = []
    for events in [
        sports_data.premier_league_events,
        sports_data.champions_league_events,
        sports_data.europa_league_events,
        sports_data.fa_cup_events,
        sports_data.league_cup_events,
    ]:
        event = find_liverpool_event(events)
        if event:
            candidates.append(event)
    if not candidates:
        return None
    return sorted(candidates, key=event_sort_key)[0]


def find_liverpool_event(events: LeagueEvents | None) -> dict | None:
    if not events:
        return None
    for event in events.rows:
        event_name = clean_text(event.get("strEvent")).lower()
        if "liverpool" in event_name:
            return event
    return None


def front_weather_summary(weather_forecasts: list[WeatherForecast]) -> str:
    preferred = [
        ("Alta", "Alta"),
        ("Børselv", "Børselv"),
        ("Čáhppiljohka", "Cahppiljohka"),
    ]
    lines = []
    for place_name, display_name in preferred:
        forecast = next((item for item in weather_forecasts if item.place.name == place_name), None)
        if forecast:
            lines.append(f"{display_name}: {forecast.summary}")
    if lines:
        return "\n".join(lines)

    if weather_forecasts:
        return f"{weather_forecasts[0].place.name}: {weather_forecasts[0].summary}"
    return "Værsidene er klare."


def first_title(items: list[SourceItem]) -> str:
    return items[0].title if items else "Ingen nye saker akkurat nå"


def first_unique_title(items: list[SourceItem], used_keys: set[str]) -> str:
    for item in items:
        title = item.title
        key = front_title_key(title)
        if key and key not in used_keys:
            return title
    return first_title(items)


def front_title_key(title: str) -> str:
    return re.sub(r"\W+", "", title.casefold())


def exclude_duplicate_news_items(
    items: list[SourceItem],
    preferred_items: list[SourceItem],
) -> list[SourceItem]:
    preferred_keys = {news_item_key(item) for item in preferred_items}
    preferred_keys.discard("")
    return [item for item in items if news_item_key(item) not in preferred_keys]


def news_item_key(item: SourceItem) -> str:
    return front_title_key(item.title)


def make_news_pages(start_page: int, title: str, items: list[SourceItem]) -> list[dict]:
    pages: list[dict] = []
    for index, item in enumerate(items):
        page_number = str(start_page + index)
        pages.append(
            {
                "id": page_number,
                "number": page_number,
                "title": title,
                "lines": [
                    make_line_from_source_item(item, line_id=f"{page_number}-1")
                ],
            }
        )

    return pages or [
        {
            "id": str(start_page),
            "number": str(start_page),
            "title": title,
            "lines": [
                make_line(
                    "Ingen nyheter hentet",
                    "Generatoren fant ingen saker i feeden.",
                    "Appen kan fortsatt vise lokal reserve eller sist lagrede kopi.",
                    source="Generator",
                )
            ],
        }
    ]


def make_line_from_source_item(item: SourceItem, line_id: str) -> dict:
    ingress = make_ingress(item)
    body = make_body(item, ingress)
    return make_line(
        headline=item.title,
        ingress=ingress,
        body=body,
        source=format_source(item),
        line_id=line_id,
        color="yellow",
    )


def make_ingress(item: SourceItem) -> str:
    sentences = relevant_sentences(item.summary, item.title)
    if sentences and is_complete_ingress(sentences[0]):
        return sentences[0]

    body_sentences = relevant_sentences(item.body, item.title)
    if body_sentences:
        return body_sentences[0]

    if sentences:
        return sentences[0]
    return "Kort nyhetsmelding fra kilden."


def make_body(item: SourceItem, ingress: str | None = None) -> str:
    if item.body:
        body_text = remove_repeated_headline(item.body, item.title)
        body_text = remove_repeated_ingress(body_text, ingress)
        if body_text:
            return wrap_text(limit_news_text(body_text))

    if is_roster_story(item):
        roster_text = remove_repeated_headline(item.summary, item.title)
        roster_text = remove_repeated_ingress(roster_text, ingress)
        if roster_text:
            return wrap_text(limit_news_text(roster_text), width=95)

    details = relevant_sentences(item.summary, item.title)[:4]
    details = [
        sentence for sentence in details
        if not repeats_text(sentence, ingress)
    ]

    text = " ".join(details).strip()
    if not text:
        text = "Flere detaljer kommer når kilden oppdateres."
    return wrap_text(limit_news_text(text))


def is_roster_story(item: SourceItem) -> bool:
    text = f"{item.title} {item.summary}".lower()
    roster_terms = ["tropp", "angrepsspillere", "midtbanespillere", "backer", "keepere"]
    return any(term in text for term in roster_terms)


def is_complete_ingress(sentence: str) -> bool:
    text = sentence.strip()
    if len(text) < 45:
        return False
    if re.search(r"\b\d+\.$", text):
        return False
    return True


def relevant_sentences(value: str | None, headline: str, max_sentences: int = 5) -> list[str]:
    sentences = safe_sentences(value or "", max_sentences=max_sentences + 2)
    filtered = [sentence for sentence in sentences if not repeats_headline(sentence, headline)]
    return filtered[:max_sentences]


def remove_repeated_headline(value: str | None, headline: str) -> str:
    text = clean_text(value)
    if not text:
        return ""

    sentences = split_sentences(text)
    filtered = [sentence for sentence in sentences if not repeats_headline(sentence, headline)]
    return " ".join(filtered).strip()


def remove_repeated_ingress(value: str | None, ingress: str | None) -> str:
    text = clean_text(value)
    if not text or not ingress:
        return text

    sentences = split_sentences(text)
    filtered = [sentence for sentence in sentences if not repeats_text(sentence, ingress)]
    return " ".join(filtered).strip()


def repeats_headline(sentence: str, headline: str) -> bool:
    return repeats_text(sentence, headline)


def repeats_text(sentence: str, comparison: str | None) -> bool:
    normalized_sentence = normalize_for_comparison(sentence)
    normalized_comparison = normalize_for_comparison(comparison or "")
    if not normalized_sentence or not normalized_comparison:
        return False
    return (
        normalized_sentence == normalized_comparison
        or normalized_sentence.startswith(f"{normalized_comparison} ")
    )


def normalize_for_comparison(value: str) -> str:
    normalized = re.sub(r"[^\wæøåáč]+", " ", value.casefold())
    return re.sub(r"\s+", " ", normalized).strip()


def limit_news_text(value: str, max_chars: int = NEWS_BODY_MAX_CHARS) -> str:
    text = clean_text(value)
    if len(text) <= max_chars:
        return text

    sentences = split_sentences(text)
    selected: list[str] = []
    length = 0
    for sentence in sentences:
        next_length = length + len(sentence) + (1 if selected else 0)
        if selected and next_length > max_chars:
            break
        if not selected and len(sentence) > max_chars:
            return sentence[:max_chars].rsplit(" ", 1)[0].strip()
        selected.append(sentence)
        length = next_length

    return " ".join(selected).strip() or text[:max_chars].rsplit(" ", 1)[0].strip()


def format_source(item: SourceItem) -> str:
    if item.published_at:
        return f"{item.source}, publisert {item.published_at.strftime('%d.%m kl. %H:%M')}"
    return item.source


def rewrite_world_items_in_norwegian(items: list[SourceItem]) -> list[SourceItem]:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("OPENAI_API_KEY is not set; keeping foreign news in source language.")
        return items

    model = os.environ.get("OPENAI_MODEL", "gpt-5.2")
    payload = {
        "model": model,
        "instructions": (
            "Du skriver korte tekst-TV-saker på norsk bokmål. "
            "Bruk bare fakta fra kildeteksten. Ikke legg til nye detaljer. "
            "Skriv nøkternt, klart og egnet for eldre TV-lesere."
        ),
        "input": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": json.dumps(
                            [
                                {
                                    "id": str(index),
                                    "source": item.source,
                                    "title": item.title,
                                    "summary": item.summary,
                                }
                                for index, item in enumerate(items)
                            ],
                            ensure_ascii=False,
                        ),
                    }
                ],
            }
        ],
        "text": {
            "format": {
                "type": "json_schema",
                "name": "teletext_world_news",
                "strict": True,
                "schema": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["items"],
                    "properties": {
                        "items": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "additionalProperties": False,
                                "required": ["id", "headline", "ingress", "body"],
                                "properties": {
                                    "id": {"type": "string"},
                                    "headline": {"type": "string"},
                                    "ingress": {"type": "string"},
                                    "body": {"type": "string"},
                                },
                            },
                        }
                    },
                },
            }
        },
    }

    request = urllib.request.Request(
        "https://api.openai.com/v1/responses",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": USER_AGENT,
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            data = json.loads(response.read())
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
        print(f"OpenAI rewrite failed: {error}")
        return items

    try:
        rewritten = json.loads(extract_response_text(data))
        rewritten_by_id = {item["id"]: item for item in rewritten.get("items", [])}
    except (KeyError, TypeError, json.JSONDecodeError) as error:
        print(f"OpenAI rewrite parse failed: {error}")
        return items

    result: list[SourceItem] = []
    for index, item in enumerate(items):
        rewritten_item = rewritten_by_id.get(str(index))
        if not rewritten_item:
            result.append(item)
            continue

        result.append(
            SourceItem(
                title=clean_text(rewritten_item.get("headline")) or item.title,
                summary=clean_text(rewritten_item.get("ingress")) or item.summary,
                body=clean_text(rewritten_item.get("body")) or None,
                source=item.source,
                url=item.url,
                published_at=item.published_at,
            )
        )

    return result


def extract_response_text(data: dict) -> str:
    if isinstance(data.get("output_text"), str):
        return data["output_text"]

    for output in data.get("output", []):
        for content in output.get("content", []):
            if isinstance(content.get("text"), str):
                return content["text"]

    raise KeyError("No text output found")


def make_table_line(table: LeagueTable | None, fallback_title: str) -> dict:
    if not table:
        return make_line(
            fallback_title,
            "Tabell kunne ikke hentes akkurat nå.",
            "Når sportskilden svarer, fylles denne siden automatisk med plassering, lag, kamper og poeng.",
            source="Generator",
        )

    body_rows = []
    for row in table.rows:
        rank = row.get("intRank", "")
        team = row.get("strTeam", "")
        played = row.get("intPlayed", "")
        goal_difference = row.get("intGoalDifference", "")
        points = row.get("intPoints", "")
        row_text = f"{rank:>2}. {team:<24} K {played:>2}  +/- {goal_difference:>3}  P {points:>3}"
        body_rows.append(
            {
                "id": f"table-{rank}",
                "text": row_text,
                "colorName": table_row_color(table.title, rank),
            }
        )

    line = make_line(
        table.title,
        source=table.source,
    )
    line["bodyRows"] = body_rows
    return line


def table_row_color(title: str, rank: str) -> str:
    try:
        placement = int(rank)
    except (TypeError, ValueError):
        return "white"

    normalized_title = title.casefold()
    if placement == 1:
        return "yellow"
    if "es-tabell" in normalized_title:
        if placement in [14]:
            return "orange"
        if placement >= 15:
            return "red"
    if "pl-tabell" in normalized_title and placement >= 18:
        return "red"
    return "white"


def make_table_pages(start_page: int, title: str, table: LeagueTable | None, fallback_title: str, per_page: int = 10) -> list[dict]:
    if not table:
        return [
            {
                "id": str(start_page),
                "number": str(start_page),
                "title": title,
                "lines": [make_table_line(None, fallback_title)],
            }
        ]

    pages = []
    chunks = list(chunked_rows(table.rows, per_page))
    for index, rows in enumerate(chunks):
        page_number = str(start_page + index)
        page_title = title if len(chunks) == 1 else f"{title} {index + 1}/{len(chunks)}"
        pages.append(
            {
                "id": page_number,
                "number": page_number,
                "title": page_title,
                "lines": [
                    make_table_line(
                        LeagueTable(title=page_title, source=table.source, rows=rows),
                        fallback_title,
                    )
                ],
            }
        )
    return pages


def make_events_line(events: LeagueEvents | None, fallback_title: str) -> dict:
    if not events:
        return make_line(
            fallback_title,
            "Kampprogram kunne ikke hentes akkurat nå.",
            "Denne siden fylles automatisk når sportskilden svarer.",
            source="Generator",
        )

    body_lines = []
    for row in events.rows:
        timestamp = format_timestamp(row.get("strTimestamp"))
        event_name = clean_text(row.get("strEvent"))
        if timestamp and event_name:
            body_lines.append(f"{timestamp}  {event_name}")
        elif event_name:
            body_lines.append(event_name)

    return make_line(
        events.title,
        events.round_name or "Kommende runde.",
        "\n".join(body_lines) or "Ingen kommende kamper funnet.",
        source=events.source,
    )


def make_event_pages(start_page: int, title: str, events: LeagueEvents | None, fallback_title: str, per_page: int = 10) -> list[dict]:
    if not events:
        return [
            {
                "id": str(start_page),
                "number": str(start_page),
                "title": title,
                "lines": [make_events_line(None, fallback_title)],
            }
        ]

    pages = []
    chunks = list(chunked_rows(events.rows, per_page))
    for index, rows in enumerate(chunks):
        page_number = str(start_page + index)
        page_title = title if len(chunks) == 1 else f"{title} {index + 1}/{len(chunks)}"
        pages.append(
            {
                "id": page_number,
                "number": page_number,
                "title": page_title,
                "lines": [
                    make_events_line(
                        LeagueEvents(
                            title=page_title,
                            source=events.source,
                            rows=rows,
                            round_name=events.round_name,
                        ),
                        fallback_title,
                    )
                ],
            }
        )
    return pages


def make_results_line(events: LeagueEvents | None, fallback_title: str) -> dict:
    if not events:
        return make_line(
            fallback_title,
            "Resultater kunne ikke hentes akkurat nå.",
            "Denne siden fylles automatisk når sportskilden svarer.",
            source="Generator",
        )

    body_lines = []
    for row in events.rows:
        timestamp = format_timestamp(row.get("strTimestamp"))
        home_team = clean_text(row.get("strHomeTeam"))
        away_team = clean_text(row.get("strAwayTeam"))
        home_score = clean_text(row.get("intHomeScore"))
        away_score = clean_text(row.get("intAwayScore"))
        if home_team and away_team and home_score and away_score:
            prefix = f"{timestamp}  " if timestamp else ""
            aggregate = clean_text(row.get("strAggregate"))
            suffix = f" ({aggregate})" if aggregate else ""
            body_lines.append(f"{prefix}{home_team} {home_score}-{away_score} {away_team}{suffix}")
        else:
            event_name = clean_text(row.get("strEvent"))
            if event_name:
                body_lines.append(event_name)

    return make_line(
        events.title,
        events.round_name or "Seneste resultater.",
        "\n".join(body_lines) or "Ingen resultater funnet.",
        source=events.source,
    )


def make_result_pages(start_page: int, title: str, events: LeagueEvents | None, fallback_title: str, per_page: int = 10) -> list[dict]:
    if not events:
        return [
            {
                "id": str(start_page),
                "number": str(start_page),
                "title": title,
                "lines": [make_results_line(None, fallback_title)],
            }
        ]

    pages = []
    chunks = list(chunked_rows(events.rows, per_page))
    for index, rows in enumerate(chunks):
        page_number = str(start_page + index)
        page_title = title if len(chunks) == 1 else f"{title} {index + 1}/{len(chunks)}"
        pages.append(
            {
                "id": page_number,
                "number": page_number,
                "title": page_title,
                "lines": [
                    make_results_line(
                        LeagueEvents(
                            title=page_title,
                            source=events.source,
                            rows=rows,
                            round_name=events.round_name,
                        ),
                        fallback_title,
                    )
                ],
            }
        )
    return pages


def make_sport_section(sports_data: SportsData) -> dict:
    pages = make_news_pages(
        start_page=200,
        title="Sportsnyheter",
        items=sports_data.sports_news or fallback_sports_news_items(),
    )

    pages.extend(
        make_news_pages(
            start_page=230,
            title="Liverpool",
            items=sports_data.liverpool_news or fallback_liverpool_items(),
        )
    )

    return {
        "id": "sport",
        "title": "Sport",
        "startPage": "200",
        "colorName": "red",
        "pages": pages,
    }


def make_matches_section(sports_data: SportsData) -> dict:
    pages = []
    next_page = 210
    for title, events, fallback_title, per_page in [
        ("Engelsk: Premier League", sports_data.premier_league_events, "Premier League", 10),
        ("Engelsk: FA-cup", sports_data.fa_cup_events, "FA-cupen", 8),
        ("Engelsk: Ligacup", sports_data.league_cup_events, "Ligacupen", 8),
        ("Norsk: Eliteserien", sports_data.eliteserien_events, "Eliteserien", 10),
        ("Europa: Champions League", sports_data.champions_league_events, "Champions League", 8),
        ("Europa: Europa League", sports_data.europa_league_events, "Europa League", 8),
    ]:
        event_pages = make_event_pages(next_page, title, events, fallback_title, per_page=per_page)
        pages.extend(event_pages)
        next_page = int(event_pages[-1]["number"]) + 1

    return {
        "id": "matches",
        "title": "Kamper",
        "startPage": "210",
        "colorName": "orange",
        "pages": pages,
    }


def make_results_section(sports_data: SportsData) -> dict:
    pages = []
    next_page = 240
    for title, events, fallback_title, per_page in [
        ("Engelsk: Premier League", sports_data.premier_league_results, "Premier League", 10),
        ("Engelsk: FA-cup", sports_data.fa_cup_results, "FA-cupen", 8),
        ("Engelsk: Ligacup", sports_data.league_cup_results, "Ligacupen", 8),
        ("Norsk: Eliteserien", sports_data.eliteserien_results, "Eliteserien", 10),
        ("Europa: Champions League", sports_data.champions_league_results, "Champions League", 8),
        ("Europa: Europa League", sports_data.europa_league_results, "Europa League", 8),
    ]:
        result_pages = make_result_pages(next_page, title, events, fallback_title, per_page=per_page)
        pages.extend(result_pages)
        next_page = int(result_pages[-1]["number"]) + 1

    return {
        "id": "results",
        "title": "Resultater",
        "startPage": "240",
        "colorName": "purple",
        "pages": pages,
    }


def make_tables_section(sports_data: SportsData) -> dict:
    pages = []
    table_pages = make_table_pages(
        270,
        "Engelsk: PL-tabell",
        sports_data.premier_league_table,
        "Premier League",
        per_page=24,
    )
    pages.extend(table_pages)
    next_page = int(table_pages[-1]["number"]) + 1

    table_pages = make_table_pages(
        next_page,
        "Norsk: ES-tabell",
        sports_data.eliteserien_table,
        "Eliteserien",
        per_page=18,
    )
    pages.extend(table_pages)
    next_page = int(table_pages[-1]["number"]) + 1

    table_pages = make_table_pages(
        next_page,
        "Europa: CL-tabell",
        sports_data.champions_league_table,
        "Champions League",
        per_page=18,
    )
    pages.extend(table_pages)

    return {
        "id": "tables",
        "title": "Tabeller",
        "startPage": "270",
        "colorName": "white",
        "pages": pages,
    }


def make_stats_section(sports_data: SportsData) -> dict:
    pages = [
        make_leaders_page(280, "PL-statistikk", sports_data.premier_league_leaders, "Premier League"),
        make_leaders_page(281, "ES-statistikk", sports_data.eliteserien_leaders, "Eliteserien"),
        make_leaders_page(282, "CL-statistikk", sports_data.champions_league_leaders, "Champions League"),
        make_leaders_page(283, "Liverpool PL", sports_data.liverpool_premier_league_leaders, "Liverpool PL"),
        make_leaders_page(284, "Liverpool alle", sports_data.liverpool_all_leaders, "Liverpool alle turneringer"),
    ]
    return {
        "id": "stats",
        "title": "Statistikk",
        "startPage": "280",
        "colorName": "cyan",
        "pages": pages,
    }


def make_leaders_page(
    page_number: int,
    page_title: str,
    leaders: LeagueLeaders | None,
    fallback_title: str,
) -> dict:
    return {
        "id": str(page_number),
        "number": str(page_number),
        "title": page_title,
        "lines": [make_leaders_line(leaders, fallback_title)],
    }


def make_leaders_line(leaders: LeagueLeaders | None, fallback_title: str) -> dict:
    if not leaders:
        return make_line(
            fallback_title,
            "Spillerstatistikk kunne ikke hentes akkurat nå.",
            "Når sportskilden svarer, fylles siden automatisk med mål og assists.",
            source="Generator",
        )

    body_rows = []
    body_rows.extend(make_stat_rows("Mål", leaders.goals[:7], "yellow", "goals"))
    body_rows.extend(make_stat_rows("Assists", leaders.assists[:7], "cyan", "assists"))
    line = make_line(
        leaders.title,
        "Topplister fra tilgjengelige turneringsdata.",
        source=leaders.source,
    )
    line["bodyRows"] = body_rows
    return line


def make_stat_rows(title: str, rows: list[PlayerStat], color: str, row_id: str) -> list[dict]:
    body_rows = [
        {
            "id": f"{row_id}-heading",
            "text": title,
            "colorName": color,
        }
    ]
    if not rows:
        body_rows.append(
            {
                "id": f"{row_id}-empty",
                "text": "Ingen spillere funnet i lederlisten.",
                "colorName": "white",
            }
        )
        return body_rows

    for index, row in enumerate(rows, start=1):
        team = f" ({short_team_name(row.team)})" if row.team else ""
        body_rows.append(
            {
                "id": f"{row_id}-{index}",
                "text": f"{index:>2}. {row.player:<22} {row.value:>2}{team}",
                "colorName": "white",
            }
        )
    return body_rows


def short_team_name(team: str) -> str:
    replacements = {
        "Manchester United": "Man United",
        "Manchester City": "Man City",
        "Nottingham Forest": "Nottm Forest",
        "Tottenham Hotspur": "Tottenham",
        "Newcastle United": "Newcastle",
        "Bodo/Glimt": "Bodø/Glimt",
    }
    return replacements.get(team, team)


def make_weather_section(forecasts: list[WeatherForecast]) -> dict:
    if not forecasts:
        forecasts = fallback_weather_forecasts()

    norway_forecasts = [forecast for forecast in forecasts if forecast.place.region == "Norge"]
    torrevieja_forecasts = [forecast for forecast in forecasts if forecast.place.name == "Torrevieja"]
    europe_forecasts = torrevieja_forecasts + [
        forecast for forecast in forecasts
        if forecast.place.region == "Europa" and forecast.place.name != "Torrevieja"
    ]
    main_forecasts = norway_forecasts + torrevieja_forecasts
    pages = [
        {
            "id": "300",
            "number": "300",
            "title": "Vær utvalgte",
            "lines": [
                make_weather_overview_line("utvalgte steder", main_forecasts),
            ],
        },
        {
            "id": "301",
            "number": "301",
            "title": "Vær Europa",
            "lines": [
                make_weather_overview_line("Europa", europe_forecasts),
            ],
        },
    ]

    for index, forecast in enumerate(norway_forecasts + europe_forecasts, start=302):
        pages.append(make_weather_page(str(index), forecast))

    return {
        "id": "weather",
        "title": "Vær",
        "startPage": "300",
        "colorName": "teal",
        "pages": pages,
    }


def make_weather_overview_line(title: str, forecasts: list[WeatherForecast]) -> dict:
    if not forecasts:
        return make_line(
            f"Vær {title}",
            "Ingen værsteder tilgjengelig akkurat nå.",
            "Generatoren bruker fallback til MET/Yr svarer igjen.",
            source="Generator",
        )

    body_lines = []
    for forecast in forecasts[:12]:
        body_lines.append(f"{forecast.place.name:<15} {forecast.summary}")

    return make_line(
        f"Vær {title}",
        "Kort oversikt over utvalgte steder.",
        "\n".join(body_lines),
        source="MET/Yr",
    )


def make_weather_page(page_number: str, forecast: WeatherForecast) -> dict:
    line = make_line(
        forecast.place.name,
        forecast.summary,
        source=forecast.source,
    )
    line["bodyRows"] = make_weather_body_rows(forecast)

    return {
        "id": page_number,
        "number": page_number,
        "title": forecast.place.name,
        "lines": [line],
    }


def make_weather_body_rows(forecast: WeatherForecast) -> list[dict]:
    rows: list[dict] = []
    day_colors = ["cyan", "yellow", "teal", "orange", "magenta"]
    day_index = 0

    for index, detail in enumerate(forecast.details.splitlines()):
        clean_detail = detail.strip()
        if not clean_detail or clean_detail == "Kommende dager:" or clean_detail.startswith("Værdata"):
            continue

        is_day_row = clean_detail.lower().startswith(
            ("mandag", "tirsdag", "onsdag", "torsdag", "fredag", "lørdag", "søndag")
        )
        row = {
            "id": f"{slugify(forecast.place.name)}-weather-{index}",
            "text": clean_detail,
            "colorName": day_colors[day_index % len(day_colors)] if is_day_row else "white",
        }

        if ":" in clean_detail:
            label, value = clean_detail.split(":", 1)
            row["label"] = f"{label}:"
            row["detail"] = value.strip()

        rows.append(row)
        if is_day_row:
            day_index += 1

    return rows


def make_line(
    headline: str,
    ingress: str | None = None,
    body: str | None = None,
    source: str | None = None,
    line_id: str | None = None,
    color: str = "yellow",
    important: bool = False,
) -> dict:
    stable_id = line_id or slugify(headline)
    line = {
        "id": stable_id,
        "headline": headline,
        "colorName": color,
        "isImportant": important,
    }
    if ingress:
        line["ingress"] = wrap_text(ingress)
    if body:
        line["body"] = body
    if source:
        line["source"] = source
    return line


def fallback_news_items() -> list[SourceItem]:
    return [
        SourceItem(
            title="Generatoren bruker lokale eksempelnyheter",
            summary="NRK-feeden kunne ikke hentes, eller generatoren ble kjørt uten nett.",
            source="Generator",
        ),
        SourceItem(
            title="Formatet er klart for ekte saker",
            summary="Hver sak har overskrift, ingress, brødtekst og kilde.",
            source="Generator",
        ),
        SourceItem(
            title="Neste steg er AI-sammendrag",
            summary="Når kildeflyten er stabil, kan en modell skrive mer tekst-TV-aktige sammendrag.",
            source="Generator",
        ),
    ]


def fallback_world_items() -> list[SourceItem]:
    return [
        SourceItem(
            title="Utenriksfeed bruker reserveinnhold",
            summary="BBC-feeden kunne ikke hentes, eller generatoren ble kjørt uten nett.",
            source="Generator",
        ),
        SourceItem(
            title="Formatet er klart for BBC og Guardian",
            summary="Utenrikssidene bruker samme tekst-TV-format som innlandssidene.",
            source="Generator",
        ),
    ]


def fallback_local_items() -> list[SourceItem]:
    return [
        SourceItem(
            title="Lokalfeed bruker reserveinnhold",
            summary="NRK-feedene for Troms og Finnmark kunne ikke hentes, eller generatoren ble kjørt uten nett.",
            source="Generator",
        ),
        SourceItem(
            title="Troms og Finnmark får egne sider",
            summary="Lokalsidene bruker samme tekst-TV-format som innland og utland.",
            source="Generator",
        ),
    ]


def fallback_weather_forecasts() -> list[WeatherForecast]:
    return [
        WeatherForecast(
            place=WeatherPlace("Alta", 69.9689, 23.2716, "Norge"),
            source="Generator",
            summary="Reservevarsel",
            details="MET/Yr kunne ikke hentes akkurat nå.",
            days=[],
        ),
        WeatherForecast(
            place=WeatherPlace("Kristiansand", 58.1467, 7.9956, "Norge"),
            source="Generator",
            summary="Reservevarsel",
            details="MET/Yr kunne ikke hentes akkurat nå.",
            days=[],
        ),
        WeatherForecast(
            place=WeatherPlace("London", 51.5072, -0.1276, "Europa"),
            source="Generator",
            summary="Reservevarsel",
            details="MET/Yr kunne ikke hentes akkurat nå.",
            days=[],
        ),
    ]


def fallback_liverpool_items() -> list[SourceItem]:
    return [
        SourceItem(
            title="Liverpool-nyheter kunne ikke hentes",
            summary="Generatoren fant ingen norske Liverpool-saker akkurat nå.",
            body="Siden fylles automatisk når Liverpool.no kan leses igjen. Kilden brukes bare til korte tekst-TV-sammendrag med kildehenvisning.",
            source="Generator",
        )
    ]


def fallback_sports_news_items() -> list[SourceItem]:
    return [
        SourceItem(
            title="Sportsnyheter kunne ikke hentes",
            summary="NRK Sport-feedene svarte ikke akkurat nå.",
            body="Siden fylles automatisk når generatoren får hentet sportsnyheter igjen.",
            source="Generator",
        )
    ]


def parse_rss_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None


def format_timestamp(value: str | None) -> str:
    if not value:
        return ""
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return value
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=ZoneInfo("UTC"))
    norwegian_time = parsed.astimezone(ZoneInfo("Europe/Oslo"))
    return norwegian_time.strftime("%d.%m %H:%M")


def clean_text(value: str | None) -> str:
    if not value:
        return ""
    text = re.sub(r"<[^>]+>", " ", value)
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def safe_sentences(value: str, max_sentences: int = 5) -> list[str]:
    sentences = split_sentences(clean_text(value))
    safe: list[str] = []
    for sentence in sentences:
        if should_skip_sentence(sentence):
            continue
        safe.append(sentence)
        if len(safe) == max_sentences:
            break
    return safe


def split_sentences(value: str) -> list[str]:
    if not value:
        return []
    parts = re.split(r"(?<!\d)(?<=[.!?])\s+", value)
    return [part.strip() for part in parts if part.strip()]


def should_skip_sentence(sentence: str) -> bool:
    # RSS feeds may contain direct quotes or graphic details. The text-TV feed
    # should summarize calmly and point to the source for the full wording.
    direct_quote_markers = ["«", "»", "– ", '"']
    sensitive_terms = ["rasistisk", "seksuelle overgrep", "vold"]
    lowercased = sentence.lower()
    if any(marker in sentence for marker in direct_quote_markers):
        return True
    if any(term in lowercased for term in sensitive_terms):
        return True
    return False


def wrap_text(value: str, width: int = 78) -> str:
    return textwrap.fill(value.strip(), width=width)


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value.lower()).strip("-")
    return slug[:48] or "line"


def chunked(values: list[SourceItem], size: int) -> Iterable[list[SourceItem]]:
    for index in range(0, len(values), size):
        yield values[index : index + size]


def chunked_rows(values: list[dict], size: int) -> Iterable[list[dict]]:
    for index in range(0, len(values), size):
        yield values[index : index + size]


def count_pages(feed: dict) -> int:
    return sum(len(section["pages"]) for section in feed["sections"])


if __name__ == "__main__":
    main()
