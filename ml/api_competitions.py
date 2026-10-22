"""Competitions the engine ingests from API-Football, beyond the Football-Data.co.uk leagues.

This is the registry behind the lower divisions of England, Spain, Germany,
Italy, France, the Netherlands and Portugal, those countries' domestic cups,
and the UEFA club competitions (Champions, Europa and Conference League).
Football-Data.co.uk publishes none of these (see docs/roadmap.md), so every
row here is sourced from API-Football and keyed by its league id.

Provenance: generated from `/leagues?country=...` responses, then reviewed.
Ids, season ranges and names come from that data; the tier and family
assignments are editorial. Ids were never typed from memory — a wrong id would
file another league's matches under these names.

Two ideas the rest of the engine depends on
-------------------------------------------
**Family.** A tier split into regional groups — Spain's eighteen Tercera RFEF
groups, Germany's fourteen Oberligas — is one league statistically: same level,
same kind of football, and teams that never meet. Each group still needs its
own table, so `name` is per group; but the one-hot competition feature and the
Poisson fit use `family`, so eighteen groups cost one feature column, not
eighteen, and each fit sees the whole tier's goal rate rather than one group's.

**Enabled.** Registering a competition changes nothing until it is *enabled*.
Enabling adds its family to `KNOWN_COMPETITIONS`, which widens the feature
vector, which means every model must be retrained and the backend restarted
(see docs/roadmap.md, the standing `KNOWN_COMPETITIONS` rule). So the switch is
`ENABLED_IDS` below, and it is flipped in the same change that carries the
data and the retrained models — never ahead of them.

Cups
----
`neutral_rounds` is a regex on the API's round name. Matches in those rounds
are played at a neutral venue, so the engine gives neither side a home edge
(ml.elo.engine reads `neutral_venue`). Every domestic cup final qualifies; the
FA Cup semi-finals are at Wembley.

Cup results are settled on the 90-minute score, never the final one — see
scripts/fetch_api_competitions.py. About one single-leg cup tie in six goes to
extra time or penalties, and every one of those is level after 90 minutes. A
two-legged tie differs: extra time is triggered by the *aggregate* being level,
so a second leg's own 90-minute score need not be (a Champions League
qualifier went to penalties after a 0-1 second leg). Either way, the 90-minute
score of the match itself is the one that is settled.

National teams
--------------
Men's senior national-team competitions are registered too (kind "national"),
filed under their confederation. They are not clubs, so they do not use a
family of regional groups: every one shares the single international Poisson
pool, and what distinguishes them is the Elo K, taken from the scheme the first
seven were calibrated on — 90 World Cup, 80 continental finals, 70 competitive
fixtures at full strength, 45 friendlies and invitationals. Minor tournaments
share a family so that a few dozen matches do not get a feature column of their
own. The seven competitions already in the engine are registered with
`already_modelled`, so the same ingest can deepen their history.

Not registered, deliberately: super cups (a handful of one-off matches a year
is a feature column fitted on noise), youth and reserve competitions, women's
competitions, play-off rounds (one-off ties whose stakes are not those of the
league they sit above), and competitions that have ended.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

COUNTRY_CODES = {
    "England": "GB",
    "Spain": "ES",
    "Germany": "DE",
    "Italy": "IT",
    "France": "FR",
    "Netherlands": "NL",
    "Portugal": "PT",
}

# `neutral_rounds` value meaning "every match is at a neutral venue".
EVERY_ROUND = "."


@dataclass(frozen=True)
class ApiCompetition:
    api_id: int
    # Our competition name; what `matches.competition` holds. Per group.
    name: str
    country: str
    short_name: str
    # "league", "cup", or "national" (a national-team competition).
    kind: str
    # 1 = top flight. None for cups, where a tier number means nothing.
    tier: int | None
    # What the one-hot feature and the Poisson fit see; equals `name` for a
    # single-division league or a cup.
    family: str
    # API-Football season years (the year a season starts) that exist.
    first_season: int
    last_season: int
    # True if a season runs across the New Year ("2024-2025"); False for a
    # calendar-year competition ("2025"). A fixed fact about the competition,
    # from the season start dates the API publishes — it must not be inferred
    # from whichever matches happen to arrive, or a partial refetch would
    # label the same season two ways.
    split_year: bool = True
    # "core" is fetched by default; "extended" is registered but opt-in.
    scope: str = "core"
    # Regex on the API round name; matching matches are at a neutral venue.
    neutral_rounds: str = ""
    # National-team competitions (kind "national") share one Poisson pool and
    # are weighted by an Elo K — see ml.competitions and ml.elo.football.
    national_teams: bool = False
    elo_k: float | None = None
    # Already in the engine (loaded by scripts/fetch_international.py). Registered
    # so the same ingest can deepen its history, but never re-added as a feature
    # column — it already has one.
    already_modelled: bool = False
    # Drop under-age, reserve and academy sides. The Friendlies feed mixes U17
    # sides in with senior ones; a registered league's reserve sides are real
    # members, so this is off by default and on only for friendlies-type feeds.
    exclude_youth: bool = False

    @property
    def country_code(self) -> str | None:
        """ISO code for the flag; None for a continental competition."""
        return COUNTRY_CODES.get(self.country)

    def is_neutral(self, round_name: str | None) -> bool:
        if self.neutral_rounds == EVERY_ROUND:
            # A single-host tournament is neutral whether or not the feed names
            # the round — a fixture with no round must not lose its neutrality.
            return True
        return bool(
            self.neutral_rounds and round_name and re.search(self.neutral_rounds, round_name)
        )


_LEAGUES: tuple[tuple[int, str, str, int, int, int, bool], ...] = (
    # (api id, family, group, tier, first season, last season, split-year)
    # England, tier 6
    (50, "English National League North", "", 6, 2019, 2026, True),
    (51, "English National League South", "", 6, 2019, 2026, True),
    # England, tier 7
    (58, "English Non League Premier", "Isthmian", 7, 2019, 2026, True),
    (59, "English Non League Premier", "Northern", 7, 2019, 2026, True),
    (60, "English Non League Premier", "Southern South", 7, 2019, 2026, True),
    (931, "English Non League Premier", "Southern Central", 7, 2022, 2026, True),
    # England, tier 8
    (52, "English Non League Division One", "Isthmian North", 8, 2019, 2025, True),
    (53, "English Non League Division One", "Isthmian South Central", 8, 2019, 2025, True),
    (54, "English Non League Division One", "Northern West", 8, 2019, 2025, True),
    (55, "English Non League Division One", "Northern Midlands", 8, 2019, 2025, True),
    (56, "English Non League Division One", "Southern South", 8, 2019, 2025, True),
    (57, "English Non League Division One", "Isthmian South East", 8, 2019, 2025, True),
    (932, "English Non League Division One", "Northern East", 8, 2022, 2025, True),
    (933, "English Non League Division One", "Southern Central", 8, 2022, 2025, True),
    # Spain, tier 3
    (435, "Spanish Primera RFEF", "Group 1", 3, 2019, 2026, True),
    (436, "Spanish Primera RFEF", "Group 2", 3, 2019, 2026, True),
    (437, "Spanish Primera RFEF", "Group 3", 3, 2019, 2020, True),
    (438, "Spanish Primera RFEF", "Group 4", 3, 2019, 2020, True),
    (692, "Spanish Primera RFEF", "Group 5", 3, 2020, 2020, True),
    # Spain, tier 4
    (875, "Spanish Segunda RFEF", "Group 1", 4, 2021, 2026, True),
    (876, "Spanish Segunda RFEF", "Group 2", 4, 2021, 2026, True),
    (877, "Spanish Segunda RFEF", "Group 3", 4, 2021, 2026, True),
    (878, "Spanish Segunda RFEF", "Group 4", 4, 2021, 2026, True),
    (879, "Spanish Segunda RFEF", "Group 5", 4, 2021, 2026, True),
    # Spain, tier 5
    (439, "Spanish Tercera RFEF", "Group 1", 5, 2019, 2026, True),
    (440, "Spanish Tercera RFEF", "Group 2", 5, 2019, 2026, True),
    (441, "Spanish Tercera RFEF", "Group 3", 5, 2019, 2026, True),
    (442, "Spanish Tercera RFEF", "Group 4", 5, 2019, 2026, True),
    (443, "Spanish Tercera RFEF", "Group 5", 5, 2019, 2026, True),
    (444, "Spanish Tercera RFEF", "Group 6", 5, 2019, 2026, True),
    (445, "Spanish Tercera RFEF", "Group 7", 5, 2019, 2026, True),
    (446, "Spanish Tercera RFEF", "Group 8", 5, 2019, 2026, True),
    (447, "Spanish Tercera RFEF", "Group 9", 5, 2019, 2026, True),
    (448, "Spanish Tercera RFEF", "Group 10", 5, 2019, 2026, True),
    (449, "Spanish Tercera RFEF", "Group 11", 5, 2019, 2026, True),
    (450, "Spanish Tercera RFEF", "Group 12", 5, 2019, 2026, True),
    (451, "Spanish Tercera RFEF", "Group 13", 5, 2019, 2026, True),
    (452, "Spanish Tercera RFEF", "Group 14", 5, 2019, 2026, True),
    (453, "Spanish Tercera RFEF", "Group 15", 5, 2019, 2026, True),
    (454, "Spanish Tercera RFEF", "Group 16", 5, 2019, 2026, True),
    (455, "Spanish Tercera RFEF", "Group 17", 5, 2019, 2026, True),
    (456, "Spanish Tercera RFEF", "Group 18", 5, 2019, 2026, True),
    # Germany, tier 3
    (80, "German 3. Liga", "", 3, 2011, 2026, True),
    # Germany, tier 4
    (83, "German Regionalliga", "Bayern", 4, 2019, 2026, True),
    (84, "German Regionalliga", "Nord", 4, 2019, 2026, True),
    (85, "German Regionalliga", "Nordost", 4, 2019, 2026, True),
    (86, "German Regionalliga", "SudWest", 4, 2019, 2026, True),
    (87, "German Regionalliga", "West", 4, 2019, 2026, True),
    # Germany, tier 5
    (744, "German Oberliga", "Schleswig-Holstein", 5, 2020, 2026, True),
    (745, "German Oberliga", "Hamburg", 5, 2020, 2026, True),
    (746, "German Oberliga", "Mittelrhein", 5, 2020, 2026, True),
    (747, "German Oberliga", "Westfalen", 5, 2020, 2026, True),
    (748, "German Oberliga", "Niedersachsen", 5, 2020, 2026, True),
    (749, "German Oberliga", "Bremen", 5, 2020, 2026, True),
    (750, "German Oberliga", "Hessen", 5, 2020, 2026, True),
    (751, "German Oberliga", "Niederrhein", 5, 2020, 2026, True),
    (752, "German Oberliga", "Rheinland-Pfalz / Saar", 5, 2020, 2026, True),
    (753, "German Oberliga", "Baden-Wurttemberg", 5, 2020, 2026, True),
    (754, "German Oberliga", "Nordost-Nord", 5, 2020, 2026, True),
    (755, "German Oberliga", "Nordost-Sud", 5, 2020, 2026, True),
    (938, "German Oberliga", "Bayern Nord", 5, 2022, 2026, True),
    (939, "German Oberliga", "Bayern Sud", 5, 2022, 2026, True),
    # Italy, tier 3
    (138, "Italian Serie C", "Girone A", 3, 2016, 2026, True),
    (139, "Italian Serie C", "", 3, 2016, 2026, True),
    (943, "Italian Serie C", "Girone C", 3, 2018, 2026, True),
    # Italy, tier 4
    (426, "Italian Serie D", "Girone A", 4, 2019, 2026, True),
    (427, "Italian Serie D", "Girone B", 4, 2019, 2026, True),
    (428, "Italian Serie D", "Girone C", 4, 2019, 2026, True),
    (429, "Italian Serie D", "Girone D", 4, 2019, 2026, True),
    (430, "Italian Serie D", "Girone E", 4, 2019, 2026, True),
    (431, "Italian Serie D", "Girone F", 4, 2019, 2026, True),
    (432, "Italian Serie D", "Girone G", 4, 2019, 2026, True),
    (433, "Italian Serie D", "Girone H", 4, 2019, 2026, True),
    (434, "Italian Serie D", "Girone I", 4, 2019, 2026, True),
    # France, tier 3
    (63, "French Ligue 3", "", 3, 2011, 2026, True),
    # France, tier 4
    (67, "French National 2", "Group A", 4, 2011, 2026, True),
    (68, "French National 2", "Group B", 4, 2011, 2026, True),
    (69, "French National 2", "Group C", 4, 2011, 2026, True),
    (70, "French National 2", "Group D", 4, 2011, 2023, True),
    # France, tier 5
    (461, "French National 3", "Group A", 5, 2019, 2025, True),
    (462, "French National 3", "Group B", 5, 2019, 2025, True),
    (463, "French National 3", "Group C", 5, 2019, 2025, True),
    (464, "French National 3", "Group D", 5, 2019, 2025, True),
    (465, "French National 3", "Group E", 5, 2019, 2025, True),
    (466, "French National 3", "Group F", 5, 2019, 2025, True),
    (467, "French National 3", "Group H", 5, 2019, 2025, True),
    (468, "French National 3", "Group I", 5, 2019, 2024, True),
    (469, "French National 3", "Group J", 5, 2019, 2024, True),
    (470, "French National 3", "Group K", 5, 2019, 2023, True),
    (471, "French National 3", "Group L", 5, 2019, 2022, True),
    (472, "French National 3", "Group M", 5, 2019, 2022, True),
    (1029, "French National 3", "Group G", 5, 2023, 2025, True),
    # Netherlands, tier 2
    (89, "Dutch Eerste Divisie", "", 2, 2016, 2026, True),
    # Netherlands, tier 3
    (492, "Dutch Tweede Divisie", "", 3, 2017, 2026, True),
    # Netherlands, tier 4
    (92, "Dutch Derde Divisie", "", 4, 2019, 2026, True),
    (93, "Dutch Derde Divisie", "Sunday", 4, 2019, 2025, True),
    # Portugal, tier 2
    (95, "Portuguese Segunda Liga", "", 2, 2016, 2026, True),
    # Portugal, tier 3
    (865, "Portuguese Liga 3", "", 3, 2021, 2026, True),
    # Portugal, tier 4
    (457, "Portuguese Campeonato de Portugal", "Group A", 4, 2019, 2026, True),
    (458, "Portuguese Campeonato de Portugal", "Group B", 4, 2019, 2026, True),
    (459, "Portuguese Campeonato de Portugal", "Group C", 4, 2019, 2026, True),
    (460, "Portuguese Campeonato de Portugal", "Group D", 4, 2019, 2026, True),
    (681, "Portuguese Campeonato de Portugal", "Group E", 4, 2020, 2021, True),
    (682, "Portuguese Campeonato de Portugal", "Group F", 4, 2020, 2021, True),
    (683, "Portuguese Campeonato de Portugal", "Group G", 4, 2020, 2020, True),
    (684, "Portuguese Campeonato de Portugal", "Group H", 4, 2020, 2020, True),
)

_FAMILY_COUNTRY: dict[str, str] = {
    "English National League North": "England",
    "English National League South": "England",
    "English Non League Premier": "England",
    "English Non League Division One": "England",
    "Spanish Primera RFEF": "Spain",
    "Spanish Segunda RFEF": "Spain",
    "Spanish Tercera RFEF": "Spain",
    "German 3. Liga": "Germany",
    "German Regionalliga": "Germany",
    "German Oberliga": "Germany",
    "Italian Serie C": "Italy",
    "Italian Serie D": "Italy",
    "French Ligue 3": "France",
    "French National 2": "France",
    "French National 3": "France",
    "Dutch Eerste Divisie": "Netherlands",
    "Dutch Tweede Divisie": "Netherlands",
    "Dutch Derde Divisie": "Netherlands",
    "Portuguese Segunda Liga": "Portugal",
    "Portuguese Liga 3": "Portugal",
    "Portuguese Campeonato de Portugal": "Portugal",
}

# (api id, name, country, short name, scope, neutral-round regex, first, last, split-year)
_CUPS: tuple[tuple[int, str, str, str, str, str, int, int, bool], ...] = (
    (45, "English FA Cup", "England", "FA Cup", "core", r"^Final$|^Semi-finals$", 2011, 2026, True),
    (46, "English EFL Trophy", "England", "EFL Trophy", "extended", r"^Final$", 2011, 2026, True),
    (47, "English FA Trophy", "England", "FA Trophy", "extended", r"^Final$", 2011, 2026, True),
    (48, "English League Cup", "England", "League Cup", "core", r"^Final$", 2011, 2026, True),
    (143, "Spanish Copa del Rey", "Spain", "Copa del Rey", "core", r"^Final$", 2018, 2026, True),
    (81, "German DFB Pokal", "Germany", "DFB Pokal", "core", r"^Final$", 2011, 2026, True),
    (137, "Italian Coppa Italia", "Italy", "Coppa Italia", "core", r"^Final$", 2016, 2026, True),
    (
        891,
        "Italian Coppa Italia Serie C",
        "Italy",
        "Coppa Italia Serie C",
        "extended",
        r"^Final$",
        2021,
        2026,
        True,
    ),
    (
        892,
        "Italian Coppa Italia Serie D",
        "Italy",
        "Coppa Italia Serie D",
        "extended",
        r"^Final$",
        2021,
        2026,
        True,
    ),
    (
        66,
        "French Coupe de France",
        "France",
        "Coupe de France",
        "core",
        r"^Final$",
        2011,
        2025,
        True,
    ),
    (90, "Dutch KNVB Beker", "Netherlands", "KNVB Beker", "core", r"^Final$", 2016, 2026, True),
    (
        96,
        "Portuguese Taca de Portugal",
        "Portugal",
        "Taça de Portugal",
        "core",
        r"^Final$",
        2016,
        2026,
        True,
    ),
    (
        97,
        "Portuguese Taca da Liga",
        "Portugal",
        "Taça da Liga",
        "core",
        r"^Final$|^Semi-finals$",
        2019,
        2026,
        True,
    ),
    (
        2,
        "UEFA Champions League",
        "Europe",
        "Champions League",
        "core",
        r"^Final$",
        2011,
        2026,
        True,
    ),
    (3, "UEFA Europa League", "Europe", "Europa League", "core", r"^Final$", 2014, 2026, True),
    (
        848,
        "UEFA Conference League",
        "Europe",
        "Conference League",
        "core",
        r"^Final$",
        2021,
        2026,
        True,
    ),
)

# National-team competitions: (api id, name, short name, confederation, family, Elo K,
# neutral-round regex, first season, last season, already modelled, drop youth sides)
_NATIONALS: tuple[tuple[int, str, str, str, str, int, str, int, int, bool, bool], ...] = (
    (
        1,
        "FIFA World Cup",
        "World Cup",
        "World",
        "FIFA World Cup",
        90,
        r".",
        2010,
        2026,
        True,
        False,
    ),
    (
        29,
        "FIFA World Cup Qualification - Africa",
        "WCQ Africa",
        "Africa",
        "FIFA World Cup Qualification",
        70,
        r"",
        2018,
        2023,
        False,
        False,
    ),
    (
        30,
        "FIFA World Cup Qualification - Asia",
        "WCQ Asia",
        "Asia",
        "FIFA World Cup Qualification",
        70,
        r"",
        2018,
        2026,
        False,
        False,
    ),
    (
        31,
        "FIFA World Cup Qualification - CONCACAF",
        "WCQ CONCACAF",
        "North America",
        "FIFA World Cup Qualification",
        70,
        r"",
        2018,
        2026,
        False,
        False,
    ),
    (
        32,
        "FIFA World Cup Qualification - Europe",
        "WCQ Europe",
        "Europe",
        "FIFA World Cup Qualification",
        70,
        r"",
        2018,
        2024,
        False,
        False,
    ),
    (
        33,
        "FIFA World Cup Qualification - Oceania",
        "WCQ Oceania",
        "Oceania",
        "FIFA World Cup Qualification",
        70,
        r"",
        2018,
        2026,
        False,
        False,
    ),
    (
        34,
        "FIFA World Cup Qualification - South America",
        "WCQ South America",
        "South America",
        "FIFA World Cup Qualification",
        70,
        r"",
        2018,
        2026,
        False,
        False,
    ),
    (
        21,
        "FIFA Confederations Cup",
        "Confederations Cup",
        "World",
        "Intercontinental Tournaments",
        80,
        r".",
        2009,
        2017,
        False,
        False,
    ),
    (
        913,
        "CONMEBOL-UEFA Finalissima",
        "Finalissima",
        "World",
        "Intercontinental Tournaments",
        80,
        r".",
        2022,
        2026,
        False,
        False,
    ),
    (
        10,
        "International Friendlies",
        "Friendlies",
        "World",
        "International Friendlies",
        45,
        r"",
        2017,
        2026,
        True,
        True,
    ),
    (
        1222,
        "FIFA Series",
        "FIFA Series",
        "World",
        "International Friendlies",
        45,
        r"",
        2026,
        2026,
        False,
        True,
    ),
    (
        1247,
        "FIFA ASEAN Cup",
        "FIFA ASEAN Cup",
        "Asia",
        "International Friendlies",
        45,
        r"",
        2026,
        2026,
        False,
        True,
    ),
    (
        4,
        "UEFA European Championship",
        "Euros",
        "Europe",
        "UEFA European Championship",
        80,
        r".",
        2008,
        2024,
        True,
        False,
    ),
    (
        960,
        "UEFA European Championship Qualification",
        "Euro Qualification",
        "Europe",
        "Continental Championship Qualification",
        70,
        r"",
        2023,
        2023,
        False,
        False,
    ),
    (
        5,
        "UEFA Nations League",
        "Nations League",
        "Europe",
        "UEFA Nations League",
        70,
        r"",
        2018,
        2026,
        True,
        False,
    ),
    (
        849,
        "Baltic Cup",
        "Baltic Cup",
        "Europe",
        "Regional Tournaments",
        45,
        r".",
        2020,
        2025,
        False,
        False,
    ),
    (
        9,
        "Copa America",
        "Copa América",
        "South America",
        "Copa America",
        80,
        r".",
        2015,
        2024,
        True,
        False,
    ),
    (
        6,
        "Africa Cup of Nations",
        "AFCON",
        "Africa",
        "Africa Cup of Nations",
        80,
        r".",
        2015,
        2025,
        True,
        False,
    ),
    (
        36,
        "Africa Cup of Nations Qualifiers",
        "AFCON Qualifiers",
        "Africa",
        "Africa Cup of Nations Qualifiers",
        70,
        r"",
        2021,
        2027,
        True,
        False,
    ),
    (
        19,
        "African Nations Championship",
        "CHAN",
        "Africa",
        "Regional Tournaments",
        45,
        r".",
        2014,
        2024,
        False,
        False,
    ),
    (
        1163,
        "African Nations Championship Qualification",
        "CHAN Qualification",
        "Africa",
        "Continental Championship Qualification",
        45,
        r"",
        2024,
        2024,
        False,
        False,
    ),
    (
        859,
        "COSAFA Cup",
        "COSAFA Cup",
        "Africa",
        "Regional Tournaments",
        45,
        r".",
        2021,
        2025,
        False,
        False,
    ),
    (
        535,
        "CECAFA Senior Challenge Cup",
        "CECAFA Cup",
        "Africa",
        "Regional Tournaments",
        45,
        r".",
        2012,
        2021,
        False,
        False,
    ),
    (7, "AFC Asian Cup", "Asian Cup", "Asia", "AFC Asian Cup", 80, r".", 2011, 2027, False, False),
    (
        35,
        "AFC Asian Cup Qualification",
        "Asian Cup Qualification",
        "Asia",
        "Continental Championship Qualification",
        70,
        r"",
        2019,
        2024,
        False,
        False,
    ),
    (
        860,
        "Arab Cup",
        "Arab Cup",
        "Asia",
        "Regional Tournaments",
        70,
        r".",
        2021,
        2025,
        False,
        False,
    ),
    (
        25,
        "Gulf Cup of Nations",
        "Gulf Cup",
        "Asia",
        "Regional Tournaments",
        70,
        r".",
        2016,
        2026,
        False,
        False,
    ),
    (
        24,
        "ASEAN Championship",
        "ASEAN Championship",
        "Asia",
        "Regional Tournaments",
        70,
        r"",
        2014,
        2025,
        False,
        False,
    ),
    (
        28,
        "SAFF Championship",
        "SAFF Championship",
        "Asia",
        "Regional Tournaments",
        70,
        r".",
        2013,
        2023,
        False,
        False,
    ),
    (
        23,
        "EAFF E-1 Football Championship",
        "EAFF E-1",
        "Asia",
        "Regional Tournaments",
        70,
        r".",
        2015,
        2025,
        False,
        False,
    ),
    (
        1008,
        "CAFA Nations Cup",
        "CAFA Nations Cup",
        "Asia",
        "Regional Tournaments",
        70,
        r".",
        2023,
        2025,
        False,
        False,
    ),
    (
        807,
        "AFC Challenge Cup",
        "AFC Challenge Cup",
        "Asia",
        "Regional Tournaments",
        70,
        r".",
        2014,
        2014,
        False,
        False,
    ),
    (
        766,
        "China Cup",
        "China Cup",
        "Asia",
        "Invitational Tournaments",
        45,
        r".",
        2017,
        2019,
        False,
        False,
    ),
    (
        916,
        "Kirin Cup",
        "Kirin Cup",
        "Asia",
        "Invitational Tournaments",
        45,
        r".",
        2022,
        2026,
        False,
        False,
    ),
    (
        1038,
        "King's Cup",
        "King's Cup",
        "Asia",
        "Invitational Tournaments",
        45,
        r".",
        2023,
        2025,
        False,
        False,
    ),
    (
        900,
        "Tipsport Malta Cup",
        "Malta Cup",
        "Europe",
        "Invitational Tournaments",
        45,
        r".",
        2022,
        2024,
        False,
        False,
    ),
    (
        22,
        "CONCACAF Gold Cup",
        "Gold Cup",
        "North America",
        "CONCACAF Gold Cup",
        80,
        r".",
        2015,
        2025,
        False,
        False,
    ),
    (
        858,
        "CONCACAF Gold Cup Qualification",
        "Gold Cup Qualification",
        "North America",
        "Continental Championship Qualification",
        70,
        r"",
        2021,
        2025,
        False,
        False,
    ),
    (
        536,
        "CONCACAF Nations League",
        "CONCACAF Nations League",
        "North America",
        "CONCACAF Nations League",
        70,
        r"",
        2020,
        2025,
        False,
        False,
    ),
    (
        808,
        "CONCACAF Nations League Qualification",
        "CNL Qualification",
        "North America",
        "CONCACAF Nations League",
        70,
        r"",
        2018,
        2018,
        False,
        False,
    ),
    (
        804,
        "Caribbean Cup",
        "Caribbean Cup",
        "North America",
        "Regional Tournaments",
        70,
        r".",
        2010,
        2016,
        False,
        False,
    ),
    (
        805,
        "Copa Centroamericana",
        "Copa Centroamericana",
        "North America",
        "Regional Tournaments",
        70,
        r".",
        2016,
        2016,
        False,
        False,
    ),
    (
        1207,
        "CONCACAF Series",
        "CONCACAF Series",
        "North America",
        "International Friendlies",
        45,
        r"",
        2026,
        2026,
        False,
        True,
    ),
    (
        806,
        "OFC Nations Cup",
        "OFC Nations Cup",
        "Oceania",
        "OFC Nations Cup",
        80,
        r".",
        2016,
        2024,
        False,
        False,
    ),
)


def _league(row: tuple[int, str, str, int, int, int, bool]) -> ApiCompetition:
    api_id, family, group, tier, first, last, split = row
    name = f"{family} - {group}" if group else family
    return ApiCompetition(
        api_id=api_id,
        name=name,
        country=_FAMILY_COUNTRY[family],
        short_name=group or family,
        kind="league",
        tier=tier,
        family=family,
        first_season=first,
        last_season=last,
        split_year=split,
    )


def _cup(row: tuple[int, str, str, str, str, str, int, int, bool]) -> ApiCompetition:
    api_id, name, country, short, scope, neutral, first, last, split = row
    return ApiCompetition(
        api_id=api_id,
        name=name,
        country=country,
        short_name=short,
        kind="cup",
        tier=None,
        family=name,
        first_season=first,
        last_season=last,
        split_year=split,
        scope=scope,
        neutral_rounds=neutral,
    )


def _national(
    row: tuple[int, str, str, str, str, int, str, int, int, bool, bool],
) -> ApiCompetition:
    api_id, name, short, confed, family, k, neutral, first, last, existing, youth = row
    return ApiCompetition(
        api_id=api_id,
        name=name,
        country=confed,
        short_name=short,
        kind="national",
        tier=None,
        family=family,
        first_season=first,
        last_season=last,
        # Tournament years, not split seasons — an AFCON played in January 2024
        # is the "2023" edition, and a qualifying cycle spans years.
        split_year=False,
        neutral_rounds=neutral,
        national_teams=True,
        elo_k=float(k),
        already_modelled=existing,
        exclude_youth=youth,
    )


API_COMPETITIONS: tuple[ApiCompetition, ...] = (
    *(_league(row) for row in _LEAGUES),
    *(_cup(row) for row in _CUPS),
    *(_national(row) for row in _NATIONALS),
)

# Competitions switched on. A competition joins only in the change that carries its data and
# the retrained models — see the module docstring.
#
# 2, 3, 848: the UEFA Champions, Europa and Conference League (history 2016-2026 ingested on
# 22 Oct 2026 with `fetch_api_competitions --ids 2,3,848 --seasons 2016-2026`).
ENABLED_IDS: frozenset[int] = frozenset({2, 3, 848})

BY_ID: dict[int, ApiCompetition] = {c.api_id: c for c in API_COMPETITIONS}
BY_NAME: dict[str, ApiCompetition] = {c.name: c for c in API_COMPETITIONS}


def enabled() -> list[ApiCompetition]:
    """Competitions to add to the engine's schema and catalogue.

    Excludes the ones already modelled: they are in the base lists already, and
    adding them again would give one competition two feature columns.
    """
    return [c for c in API_COMPETITIONS if c.api_id in ENABLED_IDS and not c.already_modelled]


def enabled_national() -> list[ApiCompetition]:
    """Enabled national-team competitions, for the shared pool and the Elo K."""
    return [c for c in enabled() if c.national_teams]


def enabled_families() -> list[str]:
    """Family names to append to `KNOWN_COMPETITIONS`, in registry order."""
    seen: list[str] = []
    for comp in enabled():
        if comp.family not in seen:
            seen.append(comp.family)
    return seen


def family_of(competition: str | None) -> str | None:
    """The modelling family of a competition name; unregistered names map to themselves."""
    if competition is None:
        return None
    comp = BY_NAME.get(competition)
    return comp.family if comp else competition
