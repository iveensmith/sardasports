"""Country, tier and display metadata for every competition we model.

The board needs to group fixtures by country, the leagues page needs to list
them by nation, and neither is derivable from the data we ingest: a match row
carries a competition name and nothing else. "Spanish La Liga" plainly
belongs to Spain and "UEFA Nations League" plainly does not belong to any
single country, but that is knowledge about football, not a fact in the
fixtures table.

This lives in code rather than a migration on purpose. It is reference data,
not user data: twenty-five rows that change only when we add a competition,
that want reviewing in a diff, and that would otherwise need a seed script
kept in sync with a table nobody looks at. When the catalogue grows past a
few hundred entries — API-Football lists seven hundred — it should become a
table with this as its seed.

`country` is the nation whose league it is. International competitions use
the confederation ("Europe", "Africa", "South America") or "World", which is
what a reader scanning a country list expects to find them under, and is why
this is a display grouping rather than a strict geography.
"""

from __future__ import annotations

from dataclasses import dataclass

from ml.api_competitions import enabled as api_enabled

# Grouping keys for competitions that belong to no single nation.
WORLD = "World"
EUROPE = "Europe"
AFRICA = "Africa"
SOUTH_AMERICA = "South America"

INTERNATIONAL_GROUPS = frozenset({WORLD, EUROPE, AFRICA, SOUTH_AMERICA})


@dataclass(frozen=True)
class CompetitionMeta:
    """What we know about a competition beyond its name."""

    competition: str
    country: str
    # Short name for a narrow column; the full name is often too long for the
    # board's competition cell at phone width.
    short_name: str
    # 1 for a country's top flight, 2 for its second tier, and so on down the
    # pyramid; None for cups and international competitions, where a tier
    # number means nothing.
    tier: int | None = None
    # ISO 3166-1 alpha-2, for the flag beside the country. None for the
    # international groups, which get a globe or confederation mark instead.
    country_code: str | None = None

    @property
    def is_international(self) -> bool:
        return self.country in INTERNATIONAL_GROUPS


_CATALOGUE: tuple[CompetitionMeta, ...] = (
    # --- England ---------------------------------------------------------
    CompetitionMeta("English Premier League", "England", "Premier League", 1, "GB"),
    CompetitionMeta("English Championship", "England", "Championship", 2, "GB"),
    CompetitionMeta("English League One", "England", "League One", 3, "GB"),
    CompetitionMeta("English League Two", "England", "League Two", 4, "GB"),
    CompetitionMeta("English National League", "England", "National League", 5, "GB"),
    # --- Spain -----------------------------------------------------------
    CompetitionMeta("Spanish La Liga", "Spain", "La Liga", 1, "ES"),
    CompetitionMeta("Spanish Segunda Division", "Spain", "Segunda División", 2, "ES"),
    # --- Germany ---------------------------------------------------------
    CompetitionMeta("German Bundesliga", "Germany", "Bundesliga", 1, "DE"),
    CompetitionMeta("German 2. Bundesliga", "Germany", "2. Bundesliga", 2, "DE"),
    # --- Italy -----------------------------------------------------------
    CompetitionMeta("Italian Serie A", "Italy", "Serie A", 1, "IT"),
    CompetitionMeta("Italian Serie B", "Italy", "Serie B", 2, "IT"),
    # --- France ----------------------------------------------------------
    CompetitionMeta("French Ligue 1", "France", "Ligue 1", 1, "FR"),
    CompetitionMeta("French Ligue 2", "France", "Ligue 2", 2, "FR"),
    # --- Other European top flights --------------------------------------
    CompetitionMeta("Dutch Eredivisie", "Netherlands", "Eredivisie", 1, "NL"),
    CompetitionMeta("Belgian Pro League", "Belgium", "Pro League", 1, "BE"),
    CompetitionMeta("Portuguese Primeira Liga", "Portugal", "Primeira Liga", 1, "PT"),
    CompetitionMeta("Turkish Super Lig", "Türkiye", "Süper Lig", 1, "TR"),
    CompetitionMeta("Greek Super League", "Greece", "Super League", 1, "GR"),
    CompetitionMeta("Scottish Premiership", "Scotland", "Premiership", 1, "GB"),
    # --- Rest of the world ------------------------------------------------
    CompetitionMeta("Major League Soccer", "United States", "MLS", 1, "US"),
    CompetitionMeta("Saudi Pro League", "Saudi Arabia", "Pro League", 1, "SA"),
    CompetitionMeta("Argentine Primera Division", "Argentina", "Primera División", 1, "AR"),
    CompetitionMeta("Brazilian Serie A", "Brazil", "Série A", 1, "BR"),
    CompetitionMeta("Japanese J1 League", "Japan", "J1 League", 1, "JP"),
    CompetitionMeta("Mexican Liga MX", "Mexico", "Liga MX", 1, "MX"),
    CompetitionMeta("Russian Premier League", "Russia", "Premier League", 1, "RU"),
    CompetitionMeta("Polish Ekstraklasa", "Poland", "Ekstraklasa", 1, "PL"),
    CompetitionMeta("Norwegian Eliteserien", "Norway", "Eliteserien", 1, "NO"),
    CompetitionMeta("Austrian Bundesliga", "Austria", "Bundesliga", 1, "AT"),
    CompetitionMeta("Chinese Super League", "China", "Super League", 1, "CN"),
    CompetitionMeta("Danish Superliga", "Denmark", "Superliga", 1, "DK"),
    CompetitionMeta("Finnish Veikkausliiga", "Finland", "Veikkausliiga", 1, "FI"),
    CompetitionMeta("Irish Premier Division", "Ireland", "Premier Division", 1, "IE"),
    CompetitionMeta("Romanian Liga I", "Romania", "Liga I", 1, "RO"),
    CompetitionMeta("Swedish Allsvenskan", "Sweden", "Allsvenskan", 1, "SE"),
    CompetitionMeta("Swiss Super League", "Switzerland", "Super League", 1, "CH"),
    # --- International ----------------------------------------------------
    CompetitionMeta("FIFA World Cup", WORLD, "World Cup"),
    CompetitionMeta("International Friendlies", WORLD, "Friendlies"),
    CompetitionMeta("UEFA European Championship", EUROPE, "Euros"),
    CompetitionMeta("UEFA Nations League", EUROPE, "Nations League"),
    CompetitionMeta("Copa America", SOUTH_AMERICA, "Copa América"),
    CompetitionMeta("Africa Cup of Nations", AFRICA, "AFCON"),
    CompetitionMeta("Africa Cup of Nations Qualifiers", AFRICA, "AFCON Qualifiers"),
)

# Enabled API-Football competitions (ml.api_competitions) join the catalogue
# here, so the board, the leagues index and the league pages know them the
# moment they are switched on — and not before, when they have no matches.
_CATALOGUE = _CATALOGUE + tuple(
    CompetitionMeta(c.name, c.country, c.short_name, c.tier, c.country_code) for c in api_enabled()
)

BY_COMPETITION: dict[str, CompetitionMeta] = {meta.competition: meta for meta in _CATALOGUE}


def meta_for(competition: str | None) -> CompetitionMeta | None:
    """Metadata for a competition, or None if we have not catalogued it.

    Returns None rather than inventing a country. A fixture from an
    uncatalogued competition should appear ungrouped rather than filed under
    a guess, because a wrong flag beside a match is worse than no flag.
    """
    if competition is None:
        return None
    return BY_COMPETITION.get(competition)


def country_of(competition: str | None) -> str | None:
    meta = meta_for(competition)
    return meta.country if meta else None


def short_name_of(competition: str | None) -> str:
    """The short label, falling back to the full name we were given."""
    meta = meta_for(competition)
    return meta.short_name if meta else (competition or "")


def countries() -> list[str]:
    """Every country we carry, nations first then the international groups.

    Nations are alphabetical; the international groups are pinned to the end
    rather than sorted in among them, because "Europe" filed between Estonia
    and France reads as a mistake.
    """
    nations = sorted({m.country for m in _CATALOGUE if not m.is_international})
    groups = [
        g for g in (WORLD, EUROPE, AFRICA, SOUTH_AMERICA) if any(m.country == g for m in _CATALOGUE)
    ]
    return nations + groups


def competitions_in(country: str) -> list[CompetitionMeta]:
    """Competitions for one country, top flight first."""
    found = [m for m in _CATALOGUE if m.country == country]
    return sorted(found, key=lambda m: (m.tier if m.tier is not None else 99, m.competition))
