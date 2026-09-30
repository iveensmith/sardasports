"""What to show beside a team's name.

A board without crests is harder to scan than it needs to be: a reader
recognises a flag or a badge a good deal faster than they parse a name, and
on a hundred-fixture card that difference is the whole ergonomics of the
page.

Two kinds, because football has two kinds of team:

    flag      a national side. The badge *is* the flag, and the flag is
              derivable from the name, so this needs nothing but a lookup.
    monogram  everything else. Club crests are per-club artwork; we have no
              licensed source for them and no identifier to fetch one with
              (one team row in eight hundred and eighty carries an
              `api_football_id`). A tinted disc with the club's initials is
              an honest placeholder — it is obviously a placeholder, it never
              shows the wrong badge, and it keeps the column aligned.

A name we do not recognise falls through to a monogram rather than guessing
at a country. A wrong flag beside a match is worse than no flag: it is a
factual error about who is playing.

Codes are ISO 3166-1 alpha-2, plus the four UK subdivision codes that
football uses as separate nations and flag sets support directly.
"""

from __future__ import annotations

from dataclasses import dataclass

# National teams, as the fixture feeds spell them. Where a feed's spelling
# differs from the country's own ("Ivory Coast", "Czechia", "FYR Macedonia"),
# the feed's spelling is what appears here, because that is what has to
# match.
NATIONAL_TEAM_CODES: dict[str, str] = {
    # --- UEFA -----------------------------------------------------------
    "Albania": "al",
    "Andorra": "ad",
    "Armenia": "am",
    "Austria": "at",
    "Azerbaijan": "az",
    "Belarus": "by",
    "Belgium": "be",
    "Bosnia & Herzegovina": "ba",
    "Bulgaria": "bg",
    "Croatia": "hr",
    "Cyprus": "cy",
    "Czechia": "cz",
    "Denmark": "dk",
    "England": "gb-eng",
    "Estonia": "ee",
    "Faroe Islands": "fo",
    "Finland": "fi",
    "France": "fr",
    "FYR Macedonia": "mk",
    "Georgia": "ge",
    "Germany": "de",
    "Gibraltar": "gi",
    "Greece": "gr",
    "Hungary": "hu",
    "Iceland": "is",
    "Israel": "il",
    "Italy": "it",
    "Kazakhstan": "kz",
    "Kosovo": "xk",
    "Latvia": "lv",
    "Liechtenstein": "li",
    "Lithuania": "lt",
    "Luxembourg": "lu",
    "Malta": "mt",
    "Moldova": "md",
    "Montenegro": "me",
    "Netherlands": "nl",
    "Northern Ireland": "gb-nir",
    "Norway": "no",
    "Poland": "pl",
    "Portugal": "pt",
    "Republic of Ireland": "ie",
    "Romania": "ro",
    "Russia": "ru",
    "San Marino": "sm",
    "Scotland": "gb-sct",
    "Serbia": "rs",
    "Slovakia": "sk",
    "Slovenia": "si",
    "Spain": "es",
    "Sweden": "se",
    "Switzerland": "ch",
    "Türkiye": "tr",
    "Turkey": "tr",
    "Ukraine": "ua",
    "Wales": "gb-wls",
    # --- CAF --------------------------------------------------------------
    "Algeria": "dz",
    "Angola": "ao",
    "Benin": "bj",
    "Botswana": "bw",
    "Burkina Faso": "bf",
    "Burundi": "bi",
    "Cameroon": "cm",
    "Cape Verde Islands": "cv",
    "Central African Republic": "cf",
    "Chad": "td",
    "Comoros": "km",
    "Congo": "cg",
    "Congo DR": "cd",
    "Egypt": "eg",
    "Equatorial Guinea": "gq",
    "Eswatini": "sz",
    "Ethiopia": "et",
    "Gabon": "ga",
    "Gambia": "gm",
    "Ghana": "gh",
    "Guinea": "gn",
    "Guinea-Bissau": "gw",
    "Ivory Coast": "ci",
    "Kenya": "ke",
    "Lesotho": "ls",
    "Liberia": "lr",
    "Libya": "ly",
    "Madagascar": "mg",
    "Malawi": "mw",
    "Mali": "ml",
    "Mauritania": "mr",
    "Morocco": "ma",
    "Mozambique": "mz",
    "Namibia": "na",
    "Niger": "ne",
    "Nigeria": "ng",
    "Rwanda": "rw",
    "Senegal": "sn",
    "Sierra Leone": "sl",
    "Somalia": "so",
    "South Africa": "za",
    "South Sudan": "ss",
    "Sudan": "sd",
    "Tanzania": "tz",
    "Togo": "tg",
    "Tunisia": "tn",
    "Uganda": "ug",
    "Zambia": "zm",
    "Zimbabwe": "zw",
    "Djibouti": "dj",
    "Eritrea": "er",
    "Mauritius": "mu",
    "Sao Tome and Principe": "st",
    "Seychelles": "sc",
    # --- CONMEBOL ---------------------------------------------------------
    "Argentina": "ar",
    "Bolivia": "bo",
    "Brazil": "br",
    "Chile": "cl",
    "Colombia": "co",
    "Ecuador": "ec",
    "Paraguay": "py",
    "Peru": "pe",
    "Uruguay": "uy",
    "Venezuela": "ve",
    # --- CONCACAF ----------------------------------------------------------
    "Canada": "ca",
    "Costa Rica": "cr",
    "Cuba": "cu",
    "Curaçao": "cw",
    "El Salvador": "sv",
    "Grenada": "gd",
    "Guatemala": "gt",
    "Haiti": "ht",
    "Honduras": "hn",
    "Jamaica": "jm",
    "Mexico": "mx",
    "Panama": "pa",
    "St. Kitts and Nevis": "kn",
    "Trinidad and Tobago": "tt",
    "United States": "us",
    "USA": "us",
    "Anguilla": "ai",
    "Antigua and Barbuda": "ag",
    "Aruba": "aw",
    "Bahamas": "bs",
    "Barbados": "bb",
    "Belize": "bz",
    "Bermuda": "bm",
    "Bonaire": "bq",
    "British Virgin Islands": "vg",
    "Cayman Islands": "ky",
    "Dominica": "dm",
    "Dominican Republic": "do",
    "French Guiana": "gf",
    "Guadeloupe": "gp",
    "Guyana": "gy",
    "Martinique": "mq",
    "Montserrat": "ms",
    "Nicaragua": "ni",
    "Puerto Rico": "pr",
    "St. Lucia": "lc",
    "St. Martin": "mf",
    "St. Vincent and the Grenadines": "vc",
    "Sint Maarten": "sx",
    "Suriname": "sr",
    "Turks and Caicos Islands": "tc",
    "US Virgin Islands": "vi",
    # --- AFC ----------------------------------------------------------------
    "Australia": "au",
    "Bahrain": "bh",
    "Cambodia": "kh",
    "China": "cn",
    "India": "in",
    "Indonesia": "id",
    "Iran": "ir",
    "Iraq": "iq",
    "Japan": "jp",
    "Jordan": "jo",
    "Kuwait": "kw",
    "Kyrgyzstan": "kg",
    "Lebanon": "lb",
    "Malaysia": "my",
    "Maldives": "mv",
    "Oman": "om",
    "Palestine": "ps",
    "Qatar": "qa",
    "Saudi Arabia": "sa",
    "South Korea": "kr",
    "Syria": "sy",
    "Tajikistan": "tj",
    "Thailand": "th",
    "Timor-Leste": "tl",
    "United Arab Emirates": "ae",
    "Uzbekistan": "uz",
    "Vietnam": "vn",
    "Afghanistan": "af",
    "Bangladesh": "bd",
    "Bhutan": "bt",
    "Brunei": "bn",
    "Chinese Taipei": "tw",
    "Guam": "gu",
    "Hong Kong": "hk",
    "Macau": "mo",
    "Mongolia": "mn",
    "Myanmar": "mm",
    "Nepal": "np",
    "North Korea": "kp",
    "Northern Mariana Islands": "mp",
    "Pakistan": "pk",
    "Philippines": "ph",
    "Singapore": "sg",
    "Sri Lanka": "lk",
    "Turkmenistan": "tm",
    "Yemen": "ye",
    # --- OFC ----------------------------------------------------------------
    "Fiji": "fj",
    "New Zealand": "nz",
    "Papua New Guinea": "pg",
    "American Samoa": "as",
    "Cook Islands": "ck",
    "Kiribati": "ki",
    "New Caledonia": "nc",
    "Niue": "nu",
    "Samoa": "ws",
    "Solomon Islands": "sb",
    "Tahiti": "pf",
    "Tonga": "to",
    "Tuvalu": "tv",
    "Vanuatu": "vu",
}

# Youth and reserve sides carry the senior nation's flag. "Croatia U18" is
# still Croatia, and a board that showed a monogram for it while showing a
# flag for the senior team beside it would look broken rather than precise.
_SUFFIXES = (" U15", " U16", " U17", " U18", " U19", " U20", " U21", " U23", " W")


@dataclass(frozen=True)
class Badge:
    """What to render beside a team name."""

    kind: str  # "flag" | "monogram"
    # Lowercase ISO code for a flag; None for a monogram.
    code: str | None
    # One or two letters for a monogram; None for a flag.
    initials: str | None


def _initials(name: str) -> str:
    """Up to two letters, from the words that carry the club's identity.

    Corporate and structural words are skipped so "Al-Hilal Saudi FC" reads
    AH rather than AS, and a single-word name falls back to its first two
    letters so "Barcelona" is BA and not just B.
    """
    skip = {"fc", "cf", "sc", "ac", "afc", "cd", "ud", "sv", "if", "bk", "ii", "b"}
    words = [w for w in name.replace("-", " ").split() if w]
    meaningful = [w for w in words if w.lower().strip(".") not in skip]
    chosen = meaningful or words
    if len(chosen) >= 2:
        return (chosen[0][:1] + chosen[1][:1]).upper()
    return (chosen[0][:2] if chosen else "?").upper()


def badge_for(team_name: str | None) -> Badge:
    """The badge for a team, never None and never a guess.

    An unrecognised name gets a monogram rather than a flag chosen by
    resemblance. A wrong flag beside a match is a factual error about who is
    playing, and worse than no flag at all.
    """
    if not team_name:
        return Badge(kind="monogram", code=None, initials="?")

    name = team_name.strip()
    code = NATIONAL_TEAM_CODES.get(name)

    if code is None:
        # A youth or women's side inherits the senior nation's flag.
        for suffix in _SUFFIXES:
            if name.endswith(suffix):
                code = NATIONAL_TEAM_CODES.get(name[: -len(suffix)].strip())
                if code:
                    break

    if code:
        return Badge(kind="flag", code=code, initials=None)
    return Badge(kind="monogram", code=None, initials=_initials(name))


def badge_dict(team_name: str | None) -> dict:
    badge = badge_for(team_name)
    return {"kind": badge.kind, "code": badge.code, "initials": badge.initials}
