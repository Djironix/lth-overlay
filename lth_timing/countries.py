"""iRacing FlairID -> šalies ISO kodas (vėliavos prie vardų).

Lentelė iš irDashies (MIT License, Copyright (c) 2024 Tarik Alani),
https://github.com/tariknz/irdashies - src/frontend/components/shared/CountryFlag.
"""

FLAIR_TO_ISO = {
    3: "af",  # Afghanistan
    4: "ax",  # Åland Islands
    5: "al",  # Albania
    6: "dz",  # Algeria
    7: "as",  # American Samoa
    8: "ad",  # Andorra
    9: "ao",  # Angola
    10: "ai",  # Anguilla
    11: "aq",  # Antarctica
    12: "ag",  # Antigua and Barbuda
    13: "ar",  # Argentina
    14: "am",  # Armenia
    15: "aw",  # Aruba
    16: "au",  # Australia
    17: "at",  # Austria
    18: "az",  # Azerbaijan
    19: "bs",  # Bahamas
    20: "bh",  # Bahrain
    21: "bd",  # Bangladesh
    22: "bb",  # Barbados
    23: "be",  # Belgium
    24: "bz",  # Belize
    25: "bj",  # Benin
    26: "bm",  # Bermuda
    27: "bt",  # Bhutan
    28: "bo",  # Bolivia
    29: "ba",  # Bosnia and Herzegovina
    30: "bw",  # Botswana
    31: "br",  # Brazil
    32: "vg",  # British Virgin Islands
    33: "bn",  # Brunei Darussalam
    34: "bg",  # Bulgaria
    35: "bf",  # Burkina Faso
    36: "bi",  # Burundi
    37: "kh",  # Cambodia
    38: "cm",  # Cameroon
    39: "ca",  # Canada
    40: "cv",  # Cape Verde
    41: "ky",  # Cayman Islands
    42: "cf",  # Central African Republic
    43: "td",  # Chad
    44: "cl",  # Chile
    45: "cn",  # China
    46: "cx",  # Christmas Island
    47: "cc",  # Cocos (Keeling) Islands
    48: "co",  # Colombia
    49: "km",  # Comoros
    50: "ck",  # Cook Islands
    51: "cr",  # Costa Rica
    52: "hr",  # Croatia
    53: "cy",  # Cyprus
    54: "cz",  # Czechia
    55: "cd",  # Democratic Republic of the Congo
    56: "dk",  # Denmark
    57: "dj",  # Djibouti
    58: "dm",  # Dominica
    59: "do",  # Dominican Republic
    60: "ec",  # Ecuador
    61: "eg",  # Egypt
    62: "sv",  # El Salvador
    63: "gq",  # Equatorial Guinea
    64: "er",  # Eritrea
    65: "ee",  # Estonia
    66: "et",  # Ethiopia
    67: "fk",  # Falkland Islands
    68: "fo",  # Faroe Islands
    69: "fj",  # Fiji
    70: "fi",  # Finland
    71: "fr",  # France
    72: "gf",  # French Guiana
    73: "pf",  # French Polynesia
    74: "ga",  # Gabon
    75: "gm",  # Gambia
    76: "ge",  # Georgia
    77: "de",  # Germany
    78: "gh",  # Ghana
    79: "gi",  # Gibraltar
    80: "gr",  # Greece
    81: "gl",  # Greenland
    82: "gd",  # Grenada
    83: "gp",  # Guadeloupe
    84: "gu",  # Guam
    85: "gt",  # Guatemala
    86: "gg",  # Guernsey
    87: "gn",  # Guinea
    88: "gw",  # Guinea-Bissau
    89: "gy",  # Guyana
    90: "ht",  # Haiti
    91: "hn",  # Honduras
    92: "hk",  # Hong Kong
    93: "hu",  # Hungary
    94: "is",  # Iceland
    95: "in",  # India
    96: "id",  # Indonesia
    97: "iq",  # Iraq
    98: "ie",  # Ireland
    99: "im",  # Isle of Man
    100: "il",  # Israel
    101: "it",  # Italy
    102: "ci",  # Ivory Coast
    103: "jm",  # Jamaica
    104: "jp",  # Japan
    105: "je",  # Jersey
    106: "jo",  # Jordan
    107: "kz",  # Kazakhstan
    108: "ke",  # Kenya
    109: "ki",  # Kiribati
    110: "kw",  # Kuwait
    111: "kg",  # Kyrgyzstan
    112: "la",  # Laos
    113: "lv",  # Latvia
    114: "lb",  # Lebanon
    115: "ls",  # Lesotho
    116: "lr",  # Liberia
    117: "ly",  # Libya
    118: "li",  # Liechtenstein
    119: "lt",  # Lithuania
    120: "lu",  # Luxembourg
    121: "mo",  # Macau
    122: "mk",  # Macedonia
    123: "mg",  # Madagascar
    124: "mw",  # Malawi
    125: "my",  # Malaysia
    126: "mv",  # Maldives
    127: "ml",  # Mali
    128: "mt",  # Malta
    129: "mh",  # Marshall Islands
    130: "mq",  # Martinique
    131: "mr",  # Mauritania
    132: "mu",  # Mauritius
    133: "yt",  # Mayotte
    134: "mx",  # Mexico
    135: "fm",  # Micronesia
    136: "md",  # Moldova
    137: "mc",  # Monaco
    138: "mn",  # Mongolia
    139: "me",  # Montenegro
    140: "ms",  # Montserrat
    141: "ma",  # Morocco
    142: "mz",  # Mozambique
    143: "na",  # Namibia
    144: "nr",  # Nauru
    145: "np",  # Nepal
    146: "nl",  # Netherlands
    148: "nc",  # New Caledonia
    149: "nz",  # New Zealand
    150: "ni",  # Nicaragua
    151: "ne",  # Niger
    152: "ng",  # Nigeria
    153: "nu",  # Niue
    154: "nf",  # Norfolk Island
    155: "mp",  # Northern Mariana Islands
    156: "no",  # Norway
    157: "om",  # Oman
    158: "pk",  # Pakistan
    159: "pw",  # Palau
    160: "ps",  # Palestine
    161: "pa",  # Panama
    162: "pg",  # Papua New Guinea
    163: "py",  # Paraguay
    164: "pe",  # Peru
    165: "ph",  # Philippines
    166: "pn",  # Pitcairn Islands
    167: "pl",  # Poland
    168: "pt",  # Portugal
    169: "pr",  # Puerto Rico
    170: "qa",  # Qatar
    171: "cg",  # Republic of the Congo
    172: "re",  # Reunion
    173: "ro",  # Romania
    174: "rw",  # Rwanda
    175: "sh",  # Saint Helena
    176: "kn",  # Saint Kitts and Nevis
    177: "lc",  # Saint Lucia
    178: "pm",  # Saint Pierre & Miquelon
    179: "vc",  # Saint Vincent and the Grenadines
    180: "bl",  # Saint-Barthélemy
    181: "mf",  # Saint-Martin
    182: "ws",  # Samoa
    183: "sm",  # San Marino
    184: "st",  # Sao Tome and Principe
    185: "sa",  # Saudi Arabia
    186: "sn",  # Senegal
    187: "rs",  # Serbia
    188: "sc",  # Seychelles
    189: "sl",  # Sierra Leone
    190: "sg",  # Singapore
    191: "sk",  # Slovakia
    192: "si",  # Slovenia
    193: "sb",  # Solomon Islands
    194: "so",  # Somalia
    195: "za",  # South Africa
    196: "gs",  # South Georgia & South Sandwich Islands
    197: "kr",  # South Korea
    198: "es",  # Spain
    199: "lk",  # Sri Lanka
    200: "sr",  # Suriname
    201: "sj",  # Svalbard
    202: "sz",  # Eswatini
    203: "se",  # Sweden
    204: "ch",  # Switzerland
    205: "tw",  # Taiwan
    206: "tj",  # Tajikistan
    207: "tz",  # Tanzania
    208: "th",  # Thailand
    209: "tl",  # Timor-Leste
    210: "tg",  # Togo
    211: "tk",  # Tokelau
    212: "to",  # Tonga
    213: "tt",  # Trinidad and Tobago
    214: "tn",  # Tunisia
    215: "tr",  # Türkiye
    216: "tm",  # Turkmenistan
    217: "tc",  # Turks and Caicos Islands
    218: "tv",  # Tuvalu
    219: "ug",  # Uganda
    220: "ua",  # Ukraine
    221: "ae",  # United Arab Emirates
    222: "gb",  # United Kingdom
    223: "us",  # United States
    224: "uy",  # Uruguay
    225: "uz",  # Uzbekistan
    226: "vu",  # Vanuatu
    227: "va",  # Vatican City
    228: "ve",  # Venezuela
    229: "vn",  # Vietnam
    230: "vi",  # Virgin Islands
    231: "wf",  # Wallis and Futuna
    232: "eh",  # Western Sahara
    233: "ye",  # Yemen
    234: "zm",  # Zambia
    235: "zw",  # Zimbabwe
    236: "gb-eng",  # England
    237: "gb-sct",  # Scotland
    238: "gb-wls",  # Wales
    239: "gb-nir",  # Northern Ireland
    240: "bq",  # Bonaire, Sint Eustatius and Saba
    241: "cw",  # Curaçao
    242: "sx",  # Sint Maarten (Dutch part)
}

NAME_TO_ISO = {
    'afghanistan': "af",
    'åland islands': "ax",
    'albania': "al",
    'algeria': "dz",
    'american samoa': "as",
    'andorra': "ad",
    'angola': "ao",
    'anguilla': "ai",
    'antarctica': "aq",
    'antigua and barbuda': "ag",
    'argentina': "ar",
    'armenia': "am",
    'aruba': "aw",
    'australia': "au",
    'austria': "at",
    'azerbaijan': "az",
    'bahamas': "bs",
    'bahrain': "bh",
    'bangladesh': "bd",
    'barbados': "bb",
    'belgium': "be",
    'belize': "bz",
    'benin': "bj",
    'bermuda': "bm",
    'bhutan': "bt",
    'bolivia': "bo",
    'bosnia and herzegovina': "ba",
    'botswana': "bw",
    'brazil': "br",
    'british virgin islands': "vg",
    'brunei darussalam': "bn",
    'bulgaria': "bg",
    'burkina faso': "bf",
    'burundi': "bi",
    'cambodia': "kh",
    'cameroon': "cm",
    'canada': "ca",
    'cape verde': "cv",
    'cayman islands': "ky",
    'central african republic': "cf",
    'chad': "td",
    'chile': "cl",
    'china': "cn",
    'christmas island': "cx",
    'cocos (keeling) islands': "cc",
    'colombia': "co",
    'comoros': "km",
    'cook islands': "ck",
    'costa rica': "cr",
    'croatia': "hr",
    'cyprus': "cy",
    'czechia': "cz",
    'democratic republic of the congo': "cd",
    'denmark': "dk",
    'djibouti': "dj",
    'dominica': "dm",
    'dominican republic': "do",
    'ecuador': "ec",
    'egypt': "eg",
    'el salvador': "sv",
    'equatorial guinea': "gq",
    'eritrea': "er",
    'estonia': "ee",
    'ethiopia': "et",
    'falkland islands': "fk",
    'faroe islands': "fo",
    'fiji': "fj",
    'finland': "fi",
    'france': "fr",
    'french guiana': "gf",
    'french polynesia': "pf",
    'gabon': "ga",
    'gambia': "gm",
    'georgia': "ge",
    'germany': "de",
    'ghana': "gh",
    'gibraltar': "gi",
    'greece': "gr",
    'greenland': "gl",
    'grenada': "gd",
    'guadeloupe': "gp",
    'guam': "gu",
    'guatemala': "gt",
    'guernsey': "gg",
    'guinea': "gn",
    'guinea-bissau': "gw",
    'guyana': "gy",
    'haiti': "ht",
    'honduras': "hn",
    'hong kong': "hk",
    'hungary': "hu",
    'iceland': "is",
    'india': "in",
    'indonesia': "id",
    'iraq': "iq",
    'ireland': "ie",
    'isle of man': "im",
    'israel': "il",
    'italy': "it",
    'ivory coast': "ci",
    'jamaica': "jm",
    'japan': "jp",
    'jersey': "je",
    'jordan': "jo",
    'kazakhstan': "kz",
    'kenya': "ke",
    'kiribati': "ki",
    'kuwait': "kw",
    'kyrgyzstan': "kg",
    'laos': "la",
    'latvia': "lv",
    'lebanon': "lb",
    'lesotho': "ls",
    'liberia': "lr",
    'libya': "ly",
    'liechtenstein': "li",
    'lithuania': "lt",
    'luxembourg': "lu",
    'macau': "mo",
    'macedonia': "mk",
    'madagascar': "mg",
    'malawi': "mw",
    'malaysia': "my",
    'maldives': "mv",
    'mali': "ml",
    'malta': "mt",
    'marshall islands': "mh",
    'martinique': "mq",
    'mauritania': "mr",
    'mauritius': "mu",
    'mayotte': "yt",
    'mexico': "mx",
    'micronesia': "fm",
    'moldova': "md",
    'monaco': "mc",
    'mongolia': "mn",
    'montenegro': "me",
    'montserrat': "ms",
    'morocco': "ma",
    'mozambique': "mz",
    'namibia': "na",
    'nauru': "nr",
    'nepal': "np",
    'netherlands': "nl",
    'new caledonia': "nc",
    'new zealand': "nz",
    'nicaragua': "ni",
    'niger': "ne",
    'nigeria': "ng",
    'niue': "nu",
    'norfolk island': "nf",
    'northern mariana islands': "mp",
    'norway': "no",
    'oman': "om",
    'pakistan': "pk",
    'palau': "pw",
    'palestine': "ps",
    'panama': "pa",
    'papua new guinea': "pg",
    'paraguay': "py",
    'peru': "pe",
    'philippines': "ph",
    'pitcairn islands': "pn",
    'poland': "pl",
    'portugal': "pt",
    'puerto rico': "pr",
    'qatar': "qa",
    'republic of the congo': "cg",
    'reunion': "re",
    'romania': "ro",
    'rwanda': "rw",
    'saint helena': "sh",
    'saint kitts and nevis': "kn",
    'saint lucia': "lc",
    'saint pierre & miquelon': "pm",
    'saint vincent and the grenadines': "vc",
    'saint-barthélemy': "bl",
    'saint-martin': "mf",
    'samoa': "ws",
    'san marino': "sm",
    'sao tome and principe': "st",
    'saudi arabia': "sa",
    'senegal': "sn",
    'serbia': "rs",
    'seychelles': "sc",
    'sierra leone': "sl",
    'singapore': "sg",
    'slovakia': "sk",
    'slovenia': "si",
    'solomon islands': "sb",
    'somalia': "so",
    'south africa': "za",
    'south georgia & south sandwich islands': "gs",
    'south korea': "kr",
    'spain': "es",
    'sri lanka': "lk",
    'suriname': "sr",
    'svalbard': "sj",
    'eswatini': "sz",
    'sweden': "se",
    'switzerland': "ch",
    'taiwan': "tw",
    'tajikistan': "tj",
    'tanzania': "tz",
    'thailand': "th",
    'timor-leste': "tl",
    'togo': "tg",
    'tokelau': "tk",
    'tonga': "to",
    'trinidad and tobago': "tt",
    'tunisia': "tn",
    'türkiye': "tr",
    'turkmenistan': "tm",
    'turks and caicos islands': "tc",
    'tuvalu': "tv",
    'uganda': "ug",
    'ukraine': "ua",
    'united arab emirates': "ae",
    'united kingdom': "gb",
    'united states': "us",
    'uruguay': "uy",
    'uzbekistan': "uz",
    'vanuatu': "vu",
    'vatican city': "va",
    'venezuela': "ve",
    'vietnam': "vn",
    'virgin islands': "vi",
    'wallis and futuna': "wf",
    'western sahara': "eh",
    'yemen': "ye",
    'zambia': "zm",
    'zimbabwe': "zw",
    'england': "gb-eng",
    'scotland': "gb-sct",
    'wales': "gb-wls",
    'northern ireland': "gb-nir",
    'bonaire, sint eustatius and saba': "bq",
    'curaçao': "cw",
    'sint maarten (dutch part)': "sx",
}


def iso_for(flair_id, flair_name="") -> str:
    """ISO kodas mažosiomis (vėliavos failo vardas) arba "" jei šalis nenurodyta."""
    try:
        code = FLAIR_TO_ISO.get(int(flair_id))
    except (TypeError, ValueError):
        code = None
    if not code and flair_name:
        code = NAME_TO_ISO.get(str(flair_name).strip().lower())
    return code or ""
