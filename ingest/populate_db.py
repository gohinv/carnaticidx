import sys
import re
import unicodedata
from pathlib import Path
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Seed alias dictionaries
#   canonical_name (lowercase) -> list of known aliases (lowercase)
#   The canonical name is implicitly also an alias.
# ---------------------------------------------------------------------------

RAGA_ALIASES: dict[str, list[str]] = {
    "abhogi": ["ābhōgi", "abhogoi"],
    "ahiri": ["āhiri"],
    "anandabhairavi": ["ānandabhairavī", "anandhabhairavi"],
    "andolika": [],
    "arabhi": ["ārabhi", "aarabhi"],
    "asaveri": ["āsāvēri"],
    "atana": ["aṭhāṇā", "athana"],
    "bageshri": [],
    "bahudari": ["bahudāri"],
    "bauli": ["baulī", "bowli"],
    "begada": ["bēgaḍā", "begadā"],
    "behag": ["bihāg", "bihag", "bēhag"],
    "bhairavi": ["bhairavī"],
    "bilahari": ["bilahāri"],
    "brindavanasaranga": ["bṛndāvana sāraṅga", "brindavana saranga"],
    "chakravakam": ["cakravākam"],
    "chandrajyothi": ["chandrajyoti"],
    "charukesi": ["cārukēśi"],
    "chayatarangini": ["chayatarangani"],
    "chenchurutti": ["ceñcukāmbhōji", "cencurutti", "senjurutti", "jheñjuṭṭi", "chenjuriti", "senchuruti"],
    "cintamani": ["cintāmaṇi", "chintamani"],
    "darbarikannada": ["darbarikanada"],
    "desh": [],
    "devagandhari": ["dēvagāndhāri", "devagandari", "dēvagandhari"],
    "devamanohari": ["dēvamanōhari", "deva manohari"],
    "devamrutavarshini": ["dēvāmṛtavarśinī"],
    "dhanashri": [],
    "dhanyasi": ["dhanyāsi", "danyasi", "dhanyāśi"],
    "dwijavanti": ["dvijāvanti", "dwijavanthi", "dwijāvanthi"],
    "gambhiranata": [],
    "gambhiravani": ["gambheeravani"],
    "ganamurthi": ["gānamūrti"],
    "gowla": ["gauḷa", "gowlai"],
    "gowlipantu": [],
    "hamir kalyani": ["hamīrkalyāṇi", "hamirkalyani"],
    "hamsadhwani": ["hamsadhvani", "hamsadwani"],
    "hamsanandi": ["hamsānandi"],
    "harikambhoji": ["harikāmbhōji", "harikambodhi", "hari kambhoji"],
    "hemavathi": ["hemāvati", "hemavati"],
    "hindolam": ["hindōḷa", "hindōLam"],
    "hindustani kapi": ["hindustānī kāpi", "hindustānikāpi"],
    "huseni": ["husēni"],
    "jaganmohini": ["jaganmōhinī"],
    "jayamanohari": ["jayamanōharī"],
    "jonpuri": ["jaunpūrī", "jaunpuri", "jōnpuri", "misra jaunpuri"],
    "kalyani": ["kalyāṇī", "kalyaani"],
    "kamavardhini": ["kāmavardhini", "kaamavardhini", "kāmavardhinī"],
    "kambhoji": ["kāmbhōji", "kamboji", "kambodhi", "khamboji", "kambhodi"],
    "kanada": ["kānaḍā", "kānaDA", "kaanada", "kannada", "kannadā"],
    "kannadagowla": [],
    "kadanakuthuhalam": [],
    "kalanidhi": [],
    "kapi": ["kāpi"],
    "karnataka kapi": ["karṇāṭaka kāpi"],
    "kedaragaula": ["kēdāragauḷa", "kedaragoula"],
    "keeravani": ["kīravāṇi"],
    "khamas": ["khamās", "kamas"],
    "kharaharapriya": ["kharaharapriyā", "karaharapriya", "k.priya"],
    "kokiladhvani": ["kōkiladhvanī", "kokiladhwani"],
    "kokilapriya": [],
    "kuntalavarali": ["kunthalavarāḷi", "kunthalvarali"],
    "kurinji": ["kuriñji"],
    "lalitapanchamam": ["lalithapanchamam"],
    "madhyamavathi": ["madhyamāvatī", "madhyamavati"],
    "malavi": [],
    "mandari": ["māndari"],
    "manirangu": ["manirang"],
    "manji": ["mānji"],
    "mayamalavagowla": ["māyāmāḷavagauḷa", "māyāmāLavagauLa", "mayamalavagaula"],
    "mohanam": ["mōhana", "mohana", "mōhanam"],
    "mukhari": ["mukhāri"],
    "nagagandhari": ["nāgagāndhāri"],
    "nagaswaravali": ["nāgasvarāvaḷi", "nagasvaravali"],
    "nalinakanthi": ["nalinakānti"],
    "nata": ["nāṭa"],
    "natakurinji": ["nāṭakuriñji", "nATakurunji", "nattaikurinji"],
    "nattai": ["nāṭṭai"],
    "navarasa kannada": [],
    "navaroj": [],
    "nayaki": ["nāyaki"],
    "neelambari": ["nīlāmbari", "nilāmbari"],
    "niroshta": [],
    "pantuvarali": ["panthvarali", "panthuvarali", "kasiramakriya"],
    "paras": [],
    "pilu": ["pīlū"],
    "poornachandrika": ["pūrṇacandrikā", "poorṇacandrikā"],
    "poorvikalyani": ["pūrvikalyāṇī", "purvikalyani", "purvi kalyani", "poorvi kalyani"],
    "poorvi": ["pūrvī", "purvi"],
    "punnagavarali": ["puṇṇāgavarāḷi"],
    "ranjani": ["rānjani"],
    "rasikapriya": ["rasikāpriyā"],
    "ravichandrika": [],
    "reetigowla": ["rītigauḷa", "reeti gowla", "ritigowla", "reetigaula", "rithigowla", "reethigowla"],
    "revagupti": ["rēvagupti"],
    "sahana": ["sahāna", "sanhana"],
    "sama": ["śyāma", "shyama"],
    "saramati": ["sāramati", "sāramathi", "saramathi"],
    "saranga": ["sāraṅga"],
    "saveri": ["sāvērī"],
    "shankarabharanam": ["śaṅkarābharaṇa", "sankarabharanam", "shankarabaranam", "shankarabharana"],
    "shanmukhapriya": ["śaNmukhapriyA", "shanmukapriya", "shanmukhariya", "shanmugapriya"],
    "shree": ["śrī rāga"],
    "sindhubhairavi": ["sindhubhairavī", "sindubhairavi"],
    "simhendramadhyamam": ["simhēndramadhyama"],
    "sooryakantam": ["sūryakāntam"],
    "sourashtram": ["saurāṣṭra", "saurāshTraM", "saurashtram", "sowrashtram"],
    "sri": ["śrīrāga", "shrī", "shri"],
    "sriranjani": ["śrīranjani", "shrīranjani", "shriranjani"],
    "subhapantuvarali": ["śubhapantuvarāḷi", "shubapantuvarali"],
    "suddhasaveri": ["śuddha sāvērī", "shuddasaveri", "suddha saveri", "suddha sāvēri"],
    "surutti": ["suruṭṭi", "suruti"],
    "tilang": [],
    "todi": ["tōḍi", "thodi"],
    "vagadheeshwari": ["vāgadīśvarī"],
    "valaji": ["vālāji"],
    "varali": ["varāḷi"],
    "vasanta": ["vasantā", "vasantha"],
    "yadukulakambhoji": ["yadukulakāmbhōji", "yadukulakambodhi", "yeedukulakamboji", "yadukula kambhoji"],
    "yamunakalyani": ["yamunākalyāṇi", "yamankalyani", "yamuna kalyani", "yaman kalyani", "yamunkalyani"],
    "dharmavathi": [],
    "chitrambari": [],
    "gamanashrama": [],
    "nagadwani": ["nāgadhvani"],
    "shivapantuvarali": [],
    "suddha dhanyasi": ["śuddha dhanyāsi"],
    "poornashadjam": ["pūrṇaṣaḍjam"],
    "sivarajnani": ["śivarañjani", "shivaranjani"],
    "abheri": ["ābhēri"],
    "maand": ["māṇḍ", "mand"],
    "ahir bhairav": ["ahirbhairav"],
    "malayamarutham": [],
    "dhenuka": [],
    "gundakriya": [],
    "cita ranjani": ["citaranjani"],
    "kiranavali": ["kirāṇāvali"],
    "ragamalika": ["rāgamālikā", "ragamalikā"],
    "bhoopalam": ["bhūpāla", "bhoopala", "bupalam"],
    "vagulabaranam": ["vākulābharaṇam"],
    "suddha sarang": ["śuddha sāraṅga"],
    "manohari": ["manōhari"],
    "nadanamakriya": ["nādanāmakriyā"],
    "janaranjani": ["jānarañjani"],
    "vachaspathi": ["vācaspati"],
    "saraswati manohari": [],
}

COMPOSER_ALIASES: dict[str, list[str]] = {
    "tyagaraja": [
        "thyagaraja", "tyāgarāja", "thyagraja", "tyagarajar", "thy",
    ],
    "muthuswamy dikshitar": [
        "dikshitar", "dīkṣita", "deekshitar", "msd",
        "muddusvāmi dīkṣita", "muttuswami dikshitar", "muthuswami dikshitar",
        "muttusvami dikshitar",
    ],
    "shyama shastri": [
        "syama sastri", "śyāma śāstri", "ss", "s. sashtrigal",
    ],
    "purandaradasa": [
        "purandara dasa", "purandaradasar", "pd",
        "purandaradāsa", "puradaradasa", "purandaradasara",
    ],
    "swati tirunal": [
        "swathi thirunal", "mst", "mahārāja svāti tiruṇāḷ",
        "swathitirunal", "maharaja swathi tirunal",
        "maharaja swathitirunal", "svāti tiruṇāḷ",
    ],
    "papanasam sivan": [
        "pāpanāśam śivan", "papanasham sivan", "papanasam shivan",
        "papanasam.s", "papanasham shivan",
    ],
    "gopalakrishna bharati": [
        "gōpālakṛṣṇa bhārati", "gopalakrishna bharatiyar",
        "gopalakrishnabharathi",
    ],
    "patnam subramania iyer": [
        "patnam subramanya iyer", "paṭṇam subrahmaṇya aiyar",
        "patnam subramaniya iyer",
    ],
    "poochi srinivasa iyengar": [
        "poochi srinivasa iyer",
    ],
    "ramanathapuram srinivasa iyengar": [
        "rāmanāthapūram śrīnivāsa aiyaṅgār",
        "ramnād srinivāsa iyengār", "ramanathapuram srinivasa iyengar",
    ],
    "andal": ["āṇḍāḷ"],
    "mysore vasudevacharya": [
        "mysūrū vāsudevācār", "mysore vasudevachar",
    ],
    "subbaraya shastri": [
        "subbarraya shastri", "subbarāya shāsthry",
    ],
    "periyasami thooran": [
        "periyaswamy thooram", "periyasaami thooran",
        "periyasvāmi tūran", "periaswamy thooran",
    ],
    "jayachamaraja wodeyar": [
        "jaychamaraja wodeyar", "jayacamraja",
    ],
    "oothukadu venkata kavi": [
        "oothukādu venkata kavi", "uthukadu venkata kavi",
    ],
    "ariyakudi ramanuja iyengar": [
        "ariyakkuḍi rāmānuja aiyaṅgār",
    ],
    "lalgudi g jayaraman": [
        "lalgudi jayaraman",
    ],
    "arunagirinathar": [
        "arunaagirinaathar", "aruṇagirināthar",
    ],
    "vedanayakam pillai": [],
    "kanakadasa": ["kanakadāsa", "kanakadhāsa"],
    "vyasaraya": ["vyāsarāya", "vyasarayar", "vyāsaraaya"],
    "pallavi gopala iyer": [
        "pallavi gōpāla aiyar", "pallavi gopala aiyar",
    ],
    "paccimiriyam adiyappaiyya": [
        "pachimiriam adiappaier", "pacchimiriyam adippayya",
        "pacchimiri adiappaiah", "paccimiriam ādiyappaiyyā",
    ],
    "arunachala kavi": ["aruṇācala kavi"],
    "vina kuppaiyar": ["vīṇā kuppaiyar", "veena kuppaiyar"],
    "dharmapuri subbaraya iyer": [
        "dharmapuri subbarayar",
    ],
    "mysore sadashiva rao": ["mysore sadhashiva rao"],
    "neelakantha sivan": [],
    "tirugokarnam vaidyanatha iyer": [
        "tirugōkarṇam vaidyanātha aiyar",
        "tirukkokarnam vaidyanatha iyer",
        "tirugokarnam vaidyanatha bhagavathar",
    ],
    "kamalesha vittala dasa": ["kamaleshadaasa", "kamaleshadasa"],
    "naraharidasa": [],
    "surapuram anandadasa": [],
    "ramalinga swamigal": [],
    "marimutha pillai": [],
    "madurai tn seshagopalan": [],
    "muthiah bhagavathar": [],
    "ambujam krishna": [],
    "kavi kunjara bharathi": [],
    "kudhambai siddhar": [],
    "sivanamayogi": [],
    "gnb": ["gn balasubramaniam", "g n balasubramaniam"],
    "karur devudu iyer": [],
    "nagapatnam veeraswamy pillai": [],
    "mayaram viswanatha shastri": [],
    "puliyur doraiswamy iyer": [],
    "vanamamaliah jiyar": [],
    "sadashiva brahmendra": [],
    "tiruvarur ramasvami pillai": [],
    "maharajapuram santhanam": [],
    "madurai t krishnaswamy": [],
    "koteshwara iyer": ["koteshwaraiyyer"],
    "vijaya vittala dasa": [],
    "tirupanandal pattabhiramayya": [
        "tiruppaṇandāḷ paṭṭābhirāmaiyyā",
        "tiruppanandal pattabhiramayya",
    ],
    "pancapakesa shastri": ["pañcāpakēśa śāstri"],
    "rudrapatnam venkataramanayya": [],
}

TALAM_ALIASES: dict[str, list[str]] = {
    "adi": ["ādi", "adhi"],
    "rupakam": ["rūpakam", "rupaka", "roopam", "ruapakam"],
    "misra chapu": [
        "miśra cāpu", "mishra chapu", "mishrachapu", "misra capu",
    ],
    "khanda chapu": ["khaṇḍa cāpu", "khandu chapu"],
    "ata": ["aṭa", "khanda ata", "chatusra ata", "khaṇḍa aṭa", "chatusra gati ata"],
    "deshadi": ["dēśādi", "deshaadi", "deshādi"],
    "tisra eka": ["tisra ekam", "tishra eka"],
    "eka": ["ēka"],
    "khanda triputa": ["khaṇḍa tripuṭa"],
    "triputa": ["tripuṭa"],
    "tisra gati adi": [],
    "viloma chapu": [],
    "khanda eka": [],
    "misra jhampa": ["miśra jhampa"],
    "tisra jhampa": [],
    "khanda capu": [],
    "madhyadi": ["madhyādi", "madyaadi"],
}

# Abbreviations used as standalone tokens for composers
_COMPOSER_ABBREV = {"thy", "msd", "mst", "ss", "pd", "gnb", "mdr"}

# ---------------------------------------------------------------------------
# Piece kind detection
# ---------------------------------------------------------------------------

KIND_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("varnam",    re.compile(r'\b(?:tāna\s+)?var[nṇ]a?m\b', re.IGNORECASE)),
    ("tillana",   re.compile(r'\btill[āa]n[āa]\b|\bthillana\b', re.IGNORECASE)),
    ("javali",    re.compile(r'\bjav[aā][ḷl]i\b|\bj[āa]va[ḷl]i\b', re.IGNORECASE)),
    ("padam",     re.compile(r'\bpadam\b|\bpa[ḍd]am\b', re.IGNORECASE)),
    ("slokam",    re.compile(r'\bśloka[m]?\b|\bsloka[m]?\b', re.IGNORECASE)),
    ("viruttam",  re.compile(r'\bvirut+[aā]m\b|\bvirutuam\b', re.IGNORECASE)),
    ("mangalam",  re.compile(r'\bma[ṅn]gala[m]?\b', re.IGNORECASE)),
    ("tiruppavai", re.compile(r'\btir[u]pp[āa]vai\b', re.IGNORECASE)),
    ("tiruppugazh", re.compile(r'\btir[u]ppuga[zḻ][h]?\b|\bthiruppugazh\b', re.IGNORECASE)),
    ("bhajan",    re.compile(r'\bbhajan\b', re.IGNORECASE)),
    ("rtp",       re.compile(
        r'\bR\.?T\.?P\.?\b'
        r'|r[āa]?g[āa]?m[\s,]*t[āa]?n[āa]?m[\s,]*p[āa]?ll[āa]?v[iī]',
        re.IGNORECASE,
    )),
]


def detect_kind(text: str) -> str | None:
    for kind, pat in KIND_PATTERNS:
        if pat.search(text):
            return kind
    return None


# ---------------------------------------------------------------------------
# Text normalization
# ---------------------------------------------------------------------------

def strip_diacritics(text: str) -> str:
    """Remove combining diacritical marks for fuzzy comparison."""
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def normalize_for_match(text: str) -> str:
    """Lowercase, strip diacritics, collapse whitespace."""
    s = strip_diacritics(text).lower()
    s = re.sub(r"['\u2018\u2019\u201c\u201d]", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


# ---------------------------------------------------------------------------
# Build lookup index: normalized_alias -> canonical_name
# ---------------------------------------------------------------------------

def build_alias_index(seed: dict[str, list[str]]) -> dict[str, str]:
    """Returns {normalized_alias: canonical_name}."""
    index: dict[str, str] = {}
    for canon, aliases in seed.items():
        norm_canon = normalize_for_match(canon)
        index[norm_canon] = canon
        for alias in aliases:
            index[normalize_for_match(alias)] = canon
    return index


RAGA_INDEX = build_alias_index(RAGA_ALIASES)
COMPOSER_INDEX = build_alias_index(COMPOSER_ALIASES)
TALAM_INDEX = build_alias_index(TALAM_ALIASES)


def lookup_raga(token: str) -> str | None:
    return RAGA_INDEX.get(normalize_for_match(token))


def lookup_composer(token: str) -> str | None:
    return COMPOSER_INDEX.get(normalize_for_match(token))


def lookup_talam(token: str) -> str | None:
    """Match talam, stripping common suffixes like ' talam' / ' thalam'."""
    norm = normalize_for_match(token)
    norm = re.sub(r"\s*t[h]?[aā]la[m]?\s*$", "", norm)
    # Also strip common gati prefixes when looking up bare name
    result = TALAM_INDEX.get(norm)
    if result:
        return result
    # Try original (for composite names like "tisra gati adi")
    return TALAM_INDEX.get(normalize_for_match(token))


# ---------------------------------------------------------------------------
# Timestamp parsing
# ---------------------------------------------------------------------------

_TS_RE = re.compile(
    r"[\[\(]?(\d{1,2}):(\d{2})(?::(\d{2}))?[\]\)]?"
)

def parse_timestamp(text: str) -> int | None:
    """Parse a timestamp string like '1:23:45' or '23:45' into total seconds."""
    m = _TS_RE.search(text)
    if not m:
        return None
    a, b = int(m.group(1)), int(m.group(2))
    c = int(m.group(3)) if m.group(3) else None
    if c is not None:
        return a * 3600 + b * 60 + c
    # Two-part: if a > 59 it's probably malformed; if a <= 59 and there's
    # context of being within a multi-hour concert, could be H:MM or M:SS.
    # Heuristic: if a >= 1 and b <= 59 and we're in a concert context,
    # timestamps >=1:00:00 should have 3 parts.  Two-part = M:SS.
    return a * 60 + b


def extract_timestamp(text: str) -> tuple[int | None, str]:
    """Extract the first timestamp from text, returning (seconds, text_with_ts_removed)."""
    m = _TS_RE.search(text)
    if not m:
        return None, text
    ts = parse_timestamp(m.group())
    cleaned = text[:m.start()] + text[m.end():]
    return ts, cleaned


# ---------------------------------------------------------------------------
# Header parser
# ---------------------------------------------------------------------------

_HEADER_RE = re.compile(r"^===\s*(\S+)\s*\|\s*(.+?)\s*===$")

_NON_ARTIST_WORDS = re.compile(
    r"\b("
    r"concert|live|academy|hall|club|sabha|tour|season|birthday|special|"
    r"rare|full|extraordinary|phenomenal|impeccable|electrifying|"
    r"air\b|all india radio|navaratri|mantapam|private|"
    r"madras|chennai|bombay|mumbai|calcutta|kolkata|delhi|"
    r"bangalore|bengaluru|coimbatore|paris|usa|los angeles|new jersey|"
    r"rutgers|iit|ifas|mfac|skgs|kgs|"
    r"the music|fine arts|gana sabha|krishna gana|sangeetha|"
    r"shanmukhananda|sastri hall|raga sudha|music circle|india club|"
    r"musicacademy|bharatiya|nellai|karunagappally|kerala|"
    r"jamshedpur|jemshedpur|jamshed|mulund|"
    r"december|january|august|november|"
    r"photo\s+incorrect|birth\s+anniversary|bicentennial|tribute|"
    r"sammelan|vidwat|"
    r"#\w+"
    r")\b",
    re.IGNORECASE,
)

_DATE_RE = re.compile(
    r"\b\d{1,2}[./]\d{1,2}[./]\d{2,4}\b"
    r"|\b\d{1,2}\s+\d{1,2}\s+\d{4}\b"
    r"|\b\d{4}\b"
)

_YEAR_RE = re.compile(r"\b(19\d{2}|20\d{2})\b")


@dataclass
class ArtistEntry:
    name: str
    role: str          # "main artist" or "accompanist"
    instrument: str | None


@dataclass
class ParsedHeader:
    youtube_id: str
    title: str
    artist_entries: list[ArtistEntry]
    year: int | None
    venue: str | None


_MAIN_ARTIST_RE = re.compile(r"^Main\s+Artist\s*:\s*(.+)$", re.IGNORECASE)
_ACCOMPANIST_RE = re.compile(r"^Accompanist\s*\(([^)]+)\)\s*:\s*(.+)$", re.IGNORECASE)
_YEAR_LABEL_RE  = re.compile(r"^Year\s*:\s*(.+)$", re.IGNORECASE)
_VENUE_LABEL_RE = re.compile(r"^Venue\s*:\s*(.+)$", re.IGNORECASE)


def parse_header(line: str) -> ParsedHeader | None:
    """Parse the === youtube_id | title === banner line only."""
    m = _HEADER_RE.match(line.strip())
    if not m:
        return None
    return ParsedHeader(
        youtube_id=m.group(1),
        title=m.group(2).strip(),
        artist_entries=[],
        year=None,
        venue=None,
    )


def apply_header_metadata(header: ParsedHeader, meta_lines: list[str]) -> None:
    """
    Consume the structured metadata block that follows the === banner:
        Main Artist: <name>
        Accompanist (<instrument>): <name>
        Year: <YYYY | Unknown>
        Venue: <text | Unknown>
    Mutates *header* in place.
    """
    for raw in meta_lines:
        line = raw.strip()
        m = _MAIN_ARTIST_RE.match(line)
        if m:
            header.artist_entries.append(
                ArtistEntry(name=m.group(1).strip(), role="main artist", instrument=None)
            )
            continue
        m = _ACCOMPANIST_RE.match(line)
        if m:
            header.artist_entries.append(
                ArtistEntry(
                    name=m.group(2).strip(),
                    role="accompanist",
                    instrument=m.group(1).strip(),
                )
            )
            continue
        m = _YEAR_LABEL_RE.match(line)
        if m:
            val = m.group(1).strip()
            if val.lower() not in ("unknown", "none", ""):
                year_m = _YEAR_RE.search(val)
                if year_m:
                    header.year = int(year_m.group(1))
            continue
        m = _VENUE_LABEL_RE.match(line)
        if m:
            val = m.group(1).strip()
            if val.lower() not in ("unknown", "none", ""):
                header.venue = val
            continue


# ---------------------------------------------------------------------------
# Line tokenizer
# ---------------------------------------------------------------------------

_SEQ_NUM_RE = re.compile(
    r"^\s*(\d{1,2})\s*[A-Za-z]?\s*[.\-:)\]]+\s*"
    r"|^\s*(\d{1,2})\s+"
)

_THANI_RE = re.compile(
    r"\(w[/.]?\s*than[iy]\)|"
    r"\bthan[iy]\s+only\b|"
    r"\+\s*Tani\b",
    re.IGNORECASE,
)

_SEPARATOR_RE = re.compile(
    r"\s*-{2,}\s*"       # ---- or ---
    r"|\s+[-–]\s+"       # ' - ' or ' – '
    r"|(?<=\w)-(?=\w)"   # word-word (tight dashes, but not inside timestamps)
)

_KIND_PAREN_RE = re.compile(
    r"\(("
    r"var[nṇ]a?m|till[āa]n[āa]|thillana|jav[aā][ḷl]i|j[āa]va[ḷl]i|"
    r"padam|pa[ḍd]am|ślokam?|slokam?|"
    r"virut+[aā]m|virutuam|"
    r"ma[ṅn]gala[m]?|"
    r"tir[u]pp[āa]vai|tir[u]ppuga[zḻ]h?|thiruppugazh|thiruppavai|"
    r"bhajan"
    r")\)",
    re.IGNORECASE,
)


@dataclass
class ParsedLine:
    raw: str
    sequence_number: int | None
    timestamp_seconds: int | None
    tokens: list[str]
    kind: str | None
    has_thani: bool
    is_rtp: bool


def _split_tokens(body: str) -> list[str]:
    """Split the body of a setlist line into tokens on separators."""
    # First try multi-char separators (---, ' - ', ' – ')
    parts = re.split(r"\s*-{2,}\s*|\s+[-–]\s+", body)
    if len(parts) >= 2:
        return [t.strip() for t in parts if t.strip()]

    # Try comma-separated (e.g. "kalyANi, Ata, Pallavi Gopala Iyer")
    parts = re.split(r"\s*,\s+", body)
    if len(parts) >= 3:
        return [t.strip() for t in parts if t.strip()]

    # Fall back to single-dash split, but be careful with CamelCase-dash patterns
    # like "1-name-raga-composer"
    parts = re.split(r"(?<=[a-zA-Z\u0100-\uFFFF])\s*[-–]\s*(?=[a-zA-Z\u0100-\uFFFF])", body)
    if len(parts) >= 2:
        return [t.strip() for t in parts if t.strip()]

    # Last resort: whitespace-only splits won't work well, return as single token
    return [body.strip()] if body.strip() else []


def tokenize_line(line: str) -> ParsedLine:
    raw = line.strip()
    body = raw

    # Detect (w/ thani) and strip it
    has_thani = bool(_THANI_RE.search(body))
    body = _THANI_RE.sub("", body)

    # Detect kind from parenthetical like "(varnam)", "(javali)"
    kind_m = _KIND_PAREN_RE.search(body)
    kind_from_paren = None
    if kind_m:
        kind_from_paren = kind_m.group(1).lower()
        body = body[:kind_m.start()] + body[kind_m.end():]

    # Detect RTP
    is_rtp = bool(re.search(
        r"\bR\.?T\.?P\.?\b"
        r"|r[āa]?g[āa]?m[\s,]*t[āa]?n[āa]?m[\s,]*p[āa]?ll[āa]?v[iī]",
        body, re.IGNORECASE,
    ))

    # Extract all timestamps, pick the first as the canonical one
    ts_matches = list(_TS_RE.finditer(body))
    timestamp = parse_timestamp(ts_matches[0].group()) if ts_matches else None

    # Remove all timestamps from body
    body = _TS_RE.sub("", body)

    # Extract sequence number
    seq_m = _SEQ_NUM_RE.match(body)
    seq = None
    if seq_m:
        seq = int(seq_m.group(1) or seq_m.group(2))
        body = body[seq_m.end():]

    # Clean up leftover punctuation
    body = re.sub(r"[\[\]\(\)]", " ", body)
    body = re.sub(r"\s+", " ", body).strip(" -–.,:;")

    # Remove quoted text (lyrics)
    body = re.sub(r'"[^"]*"', "", body)
    body = re.sub(r"\s+", " ", body).strip(" -–.,:;")

    # Tokenize
    tokens = _split_tokens(body)

    # Clean individual tokens
    tokens = [t.strip(" -–.,:;()[]") for t in tokens]
    tokens = [t for t in tokens if t and t.lower() not in ("", "w")]

    # Detect kind from full text if not found in parens
    kind = kind_from_paren
    if kind is None:
        kind = detect_kind(raw)

    return ParsedLine(
        raw=raw,
        sequence_number=seq,
        timestamp_seconds=timestamp,
        tokens=tokens,
        kind=kind,
        has_thani=has_thani,
        is_rtp=is_rtp,
    )


# ---------------------------------------------------------------------------
# File parser: split into concert blocks
# ---------------------------------------------------------------------------

@dataclass
class ConcertBlock:
    header: ParsedHeader
    lines: list[ParsedLine]


def parse_file(filepath: str) -> list[ConcertBlock]:
    """Parse cleaned_data.txt into concert blocks."""
    path = Path(filepath)
    text = path.read_text(encoding="utf-8")
    raw_lines = text.splitlines()

    blocks: list[ConcertBlock] = []
    current_header: ParsedHeader | None = None
    current_meta: list[str] = []   # buffered metadata lines before first setlist line
    current_lines: list[str] = []
    in_meta: bool = False          # True while collecting metadata lines

    for raw_line in raw_lines:
        stripped = raw_line.strip()

        if stripped.startswith("===") and stripped.endswith("==="):
            # Save previous block
            if current_header and current_lines:
                parsed_lines = [tokenize_line(l) for l in current_lines]
                blocks.append(ConcertBlock(header=current_header, lines=parsed_lines))

            current_header = parse_header(stripped)
            current_meta = []
            current_lines = []
            in_meta = True

        elif current_header is not None:
            if in_meta:
                # Blank line ends the metadata block
                if not stripped:
                    continue
                # Labeled metadata lines
                if (
                    _MAIN_ARTIST_RE.match(stripped)
                    or _ACCOMPANIST_RE.match(stripped)
                    or _YEAR_LABEL_RE.match(stripped)
                    or _VENUE_LABEL_RE.match(stripped)
                ):
                    current_meta.append(stripped)
                    continue
                # First non-meta, non-blank line: apply collected metadata then fall through
                apply_header_metadata(current_header, current_meta)
                in_meta = False
                # fall through to setlist-line handling below

            if not stripped:
                continue
            # Skip non-song commentary lines
            if not _TS_RE.search(stripped) and not stripped[0:1].isdigit():
                continue
            # Skip standalone tani avartanam lines
            bare = _TS_RE.sub("", stripped)
            bare = re.sub(r"^\s*\d+\w*[\s.\-:]+", "", bare).strip(" -:")
            if re.match(r"^than[iy]\b|^tani\b", bare, re.IGNORECASE):
                continue
            # Skip commentary / speech / announcement lines
            if re.search(r"\bspeech\b|\bannouncement\b|\bthank you\b|\baudio complaint\b",
                         bare, re.IGNORECASE):
                continue
            current_lines.append(stripped)

    # Don't forget the last block
    if current_header is not None:
        if in_meta:
            apply_header_metadata(current_header, current_meta)
        if current_lines:
            parsed_lines = [tokenize_line(l) for l in current_lines]
            blocks.append(ConcertBlock(header=current_header, lines=parsed_lines))

    return blocks


# ---------------------------------------------------------------------------
# Token classifier
# ---------------------------------------------------------------------------

@dataclass
class ClassifiedLine:
    piece_name: str | None
    raga: str | None
    talam: str | None
    composer: str | None
    kind: str | None
    timestamp_seconds: int | None
    sequence_number: int | None
    has_thani: bool
    is_rtp: bool
    raw: str
    confidence: float


def classify_tokens(parsed: ParsedLine) -> ClassifiedLine:
    """Assign semantic roles to tokens: piece name, raga, talam, composer."""
    tokens = parsed.tokens
    raga = None
    talam = None
    composer = None
    piece_candidates: list[str] = []

    # Track which token indices have been claimed
    claimed: set[int] = set()

    # Pass 1: exact lookup for raga, talam, composer
    for i, tok in enumerate(tokens):
        if raga is None:
            hit = lookup_raga(tok)
            if hit:
                raga = hit
                claimed.add(i)
                continue
        if composer is None:
            hit = lookup_composer(tok)
            if hit:
                composer = hit
                claimed.add(i)
                continue
        if talam is None:
            hit = lookup_talam(tok)
            if hit:
                talam = hit
                claimed.add(i)
                continue

    # Pass 2: unclaimed tokens become piece name candidates
    for i, tok in enumerate(tokens):
        if i not in claimed:
            # Skip tokens that are just kind labels ("Varnam", "Tillana", etc.)
            norm = normalize_for_match(tok)
            if norm in ("varnam", "varna", "rtp", "mangalam", "slokam",
                        "viruttham", "viruttam", "tillana", "thillana",
                        "bhajan", "tiruppugazh", "thiruppugazh"):
                continue
            # Skip ragamalika swarams continuation tokens
            if re.match(r"^ragamalika\s+swarams?", tok, re.IGNORECASE):
                continue
            # Skip solfege patterns like "Ni Ri Ni Ri Ga Ma Ga Ri Sa"
            if re.match(r"^[SsRrGgMmPpDdNn][aāiī]?\s", tok) and len(tok.split()) > 4:
                continue
            # Skip "selection from" etc.
            if re.match(r"^selection\s+from", tok, re.IGNORECASE):
                continue
            piece_candidates.append(tok)

    # The first unclaimed token is most likely the piece name
    piece_name = piece_candidates[0] if piece_candidates else None

    # For RTP lines, override piece name
    if parsed.is_rtp:
        piece_name = "RTP"

    # Determine kind
    kind = parsed.kind
    if kind is None and piece_name:
        kind = detect_kind(piece_name)

    # Confidence scoring
    confidence = _score_confidence(piece_name, raga, talam, composer, kind, parsed.is_rtp)

    return ClassifiedLine(
        piece_name=piece_name,
        raga=raga,
        talam=talam,
        composer=composer,
        kind=kind,
        timestamp_seconds=parsed.timestamp_seconds,
        sequence_number=parsed.sequence_number,
        has_thani=parsed.has_thani,
        is_rtp=parsed.is_rtp,
        raw=parsed.raw,
        confidence=confidence,
    )


def _score_confidence(
    piece: str | None,
    raga: str | None,
    talam: str | None,
    composer: str | None,
    kind: str | None,
    is_rtp: bool,
) -> float:
    """Score how complete the classification is, 0.0 to 1.0."""
    if is_rtp:
        # RTP only needs a raga to be useful
        return 0.8 if raga else 0.4

    if kind in ("mangalam", "tiruppugazh", "bhajan", "slokam", "viruttam"):
        # These often lack some fields; piece + raga is enough
        return 0.7 if raga else 0.3

    score = 0.0
    if piece:
        score += 0.3
    if raga:
        score += 0.3
    if composer:
        score += 0.2
    if talam:
        score += 0.2
    return score


# ---------------------------------------------------------------------------
# Piece resolution (exact → alias → normalized → trgm)
# ---------------------------------------------------------------------------

@dataclass
class PieceMatch:
    piece: object
    method: str


def _alias_exists(session, PieceAlias, piece_id: int, alias_text: str) -> bool:
    norm = normalize_for_match(alias_text)
    for row in session.query(PieceAlias).filter_by(piece_id=piece_id).all():
        if normalize_for_match(row.alias) == norm:
            return True
    return False


def ensure_piece_alias(session, PieceAlias, piece, alias_text: str) -> bool:
    """Add alias if it differs from the canonical piece name. Returns True if added."""
    if normalize_for_match(alias_text) == normalize_for_match(piece.name):
        return False
    if _alias_exists(session, PieceAlias, piece.id, alias_text):
        return False
    session.add(PieceAlias(piece_id=piece.id, alias=alias_text))
    session.flush()
    return True


def get_or_create(session, model, defaults=None, **kwargs):
    """Get existing row or create a new one. Returns (instance, created)."""
    instance = session.query(model).filter_by(**kwargs).first()
    if instance:
        return instance, False
    params = {**kwargs, **(defaults or {})}
    instance = model(**params)
    session.add(instance)
    session.flush()
    return instance, True


def resolve_piece(
    session,
    Piece,
    PieceAlias,
    name: str,
    raga_id: int | None = None,
    trgm_threshold: float = 0.4,
) -> PieceMatch | None:
    """
    Find an existing piece by name/alias.
    When raga_id is given, raga-scoped matches are tried first.
    Falls back to cross-raga name matching when no raga-scoped match is found
    (or when raga_id is None), so partial lines can still match existing pieces.
    """
    from sqlalchemy import func

    norm = normalize_for_match(name)
    if not norm:
        return None

    def _raga_filter(q, model):
        return q.filter(model.raga_id == raga_id) if raga_id is not None else q

    # --- raga-scoped pass (skipped when raga_id is None) ---
    if raga_id is not None:
        piece = session.query(Piece).filter(
            Piece.name == name, Piece.raga_id == raga_id,
        ).first()
        if piece:
            return PieceMatch(piece, "exact_name")

        alias_row = (
            session.query(PieceAlias).join(Piece)
            .filter(PieceAlias.alias == name, Piece.raga_id == raga_id)
            .first()
        )
        if alias_row:
            return PieceMatch(alias_row.piece, "exact_alias")

        for p in session.query(Piece).filter(Piece.raga_id == raga_id).all():
            if normalize_for_match(p.name) == norm:
                return PieceMatch(p, "normalized_name")

        for ar in (
            session.query(PieceAlias).join(Piece)
            .filter(Piece.raga_id == raga_id).all()
        ):
            if normalize_for_match(ar.alias) == norm:
                return PieceMatch(ar.piece, "normalized_alias")

        threshold = trgm_threshold if len(norm) >= 6 else max(trgm_threshold, 0.55)
        alias_hit = (
            session.query(PieceAlias).join(Piece)
            .filter(Piece.raga_id == raga_id)
            .filter(func.similarity(PieceAlias.alias, norm) > threshold)
            .order_by(func.similarity(PieceAlias.alias, norm).desc())
            .first()
        )
        if alias_hit:
            return PieceMatch(alias_hit.piece, "trgm_alias")

        piece_hit = (
            session.query(Piece)
            .filter(Piece.raga_id == raga_id)
            .filter(func.similarity(Piece.name, norm) > threshold)
            .order_by(func.similarity(Piece.name, norm).desc())
            .first()
        )
        if piece_hit:
            return PieceMatch(piece_hit, "trgm_name")

    # --- cross-raga fallback (when raga_id is None, or no raga-scoped match found) ---
    piece = session.query(Piece).filter(Piece.name == name).first()
    if piece:
        return PieceMatch(piece, "exact_name_any_raga")

    alias_row = session.query(PieceAlias).filter(PieceAlias.alias == name).first()
    if alias_row:
        return PieceMatch(alias_row.piece, "exact_alias_any_raga")

    for p in session.query(Piece).all():
        if normalize_for_match(p.name) == norm:
            return PieceMatch(p, "normalized_name_any_raga")

    for ar in session.query(PieceAlias).all():
        if normalize_for_match(ar.alias) == norm:
            return PieceMatch(ar.piece, "normalized_alias_any_raga")

    threshold = trgm_threshold if len(norm) >= 6 else max(trgm_threshold, 0.55)
    alias_hit = (
        session.query(PieceAlias)
        .filter(func.similarity(PieceAlias.alias, norm) > threshold)
        .order_by(func.similarity(PieceAlias.alias, norm).desc())
        .first()
    )
    if alias_hit:
        return PieceMatch(alias_hit.piece, "trgm_alias_any_raga")

    piece_hit = (
        session.query(Piece)
        .filter(func.similarity(Piece.name, norm) > threshold)
        .order_by(func.similarity(Piece.name, norm).desc())
        .first()
    )
    if piece_hit:
        return PieceMatch(piece_hit, "trgm_name_any_raga")

    return None


def get_or_create_piece(
    session,
    Piece,
    PieceAlias,
    name: str,
    raga_id: int | None,
    composer_id: int | None,
    talam_id: int | None,
    kind: str | None,
) -> tuple[object, bool, str | None]:
    """
    Resolve or create a piece. Returns (piece, created, match_method).
    All metadata fields are optional — unknown fields are stored as NULL.
    """
    match = resolve_piece(session, Piece, PieceAlias, name, raga_id)
    if match:
        ensure_piece_alias(session, PieceAlias, match.piece, name)
        return match.piece, False, match.method

    piece, created = get_or_create(
        session,
        Piece,
        name=name,
        defaults={
            "raga_id": raga_id,
            "composer_id": composer_id,
            "talam_id": talam_id,
            "kind": kind,
        },
    )
    return piece, created, None


# ---------------------------------------------------------------------------
# Phase A — wipe
# ---------------------------------------------------------------------------

_WIPE_TABLES = (
    "setlist_items",
    "concert_artists",
    "ingest_drafts",
    "piece_aliases",
    "concerts",
    "artists",
    "pieces",
    "composers",
    "ragas",
    "talams",
)


def wipe(dry_run: bool = False) -> None:
    """Truncate all entity tables in FK-safe order and restart identity sequences."""
    from sqlalchemy import text

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))
    from app import app, db

    table_list = ", ".join(_WIPE_TABLES)
    sql = f"TRUNCATE TABLE {table_list} RESTART IDENTITY CASCADE"

    with app.app_context():
        if dry_run:
            print(f"[DRY RUN] Would execute: {sql}")
            return

        db.session.execute(text(sql))
        db.session.commit()
        print("Database wiped.")


# ---------------------------------------------------------------------------
# Phase B — seed master
# ---------------------------------------------------------------------------

_NULL_VALUES = {"unknown", "none", ""}


def _is_null_value(s: str) -> bool:
    return s.strip().lower() in _NULL_VALUES


def seed_master(dry_run: bool = False, verbose: bool = False) -> None:
    """
    Read ingest/pieces_master.csv and insert ragas, talams, composers, and pieces.
    Treats 'Unknown', 'None', or blank cells as NULL for raga/talam/composer.
    """
    import csv

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))
    from app import app, db, Raga, Talam, Composer, Piece

    csv_path = Path(__file__).parent / "pieces_master.csv"
    rows = []
    with csv_path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            rows.append(row)

    stats = {"ragas": 0, "talams": 0, "composers": 0, "pieces": 0}

    with app.app_context():
        for row in rows:
            name     = row.get("Name", "").strip()
            raga_raw = row.get("Raga", "").strip()
            tala_raw = row.get("Tala", "").strip()
            comp_raw = row.get("Composer", "").strip()
            kind_raw = row.get("Kind", "").strip() or None

            if not name:
                continue

            raga_row = None
            if not _is_null_value(raga_raw):
                raga_row, created = get_or_create(db.session, Raga, name=raga_raw)
                if created:
                    stats["ragas"] += 1

            talam_row = None
            if not _is_null_value(tala_raw):
                talam_row, created = get_or_create(db.session, Talam, name=tala_raw)
                if created:
                    stats["talams"] += 1

            composer_row = None
            if not _is_null_value(comp_raw):
                composer_row, created = get_or_create(db.session, Composer, name=comp_raw)
                if created:
                    stats["composers"] += 1

            piece = Piece(
                name=name,
                kind=kind_raw,
                raga_id=raga_row.id if raga_row else None,
                talam_id=talam_row.id if talam_row else None,
                composer_id=composer_row.id if composer_row else None,
            )
            db.session.add(piece)
            db.session.flush()
            stats["pieces"] += 1

            if verbose:
                raga_str = raga_row.name if raga_row else "NULL"
                talam_str = talam_row.name if talam_row else "NULL"
                comp_str = composer_row.name if composer_row else "NULL"
                print(f"  [PIECE] {name!r} raga={raga_str} talam={talam_str} composer={comp_str} kind={kind_raw}")

        if dry_run:
            db.session.rollback()
            print("[DRY RUN] No changes committed.")
        else:
            db.session.commit()
            print("Master seed committed.")

    print(f"\nSeed master results:")
    print(f"  Ragas:     {stats['ragas']}")
    print(f"  Talams:    {stats['talams']}")
    print(f"  Composers: {stats['composers']}")
    print(f"  Pieces:    {stats['pieces']}")


# ---------------------------------------------------------------------------
# Phase C helpers
# ---------------------------------------------------------------------------

def _fmt_ts(seconds: int | None) -> str:
    if seconds is None:
        return "?"
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def _tag(created: bool) -> str:
    return "NEW" if created else "EXISTING"


def resolve_master_piece(
    session,
    Piece,
    PieceAlias,
    Raga,
    Composer,
    piece_name: str,
    raga_name: str | None,
    composer_name: str | None,
    trgm_threshold: float = 0.45,
) -> PieceMatch | None:
    """
    Match *piece_name* against the seeded master — never creates anything.

    Resolution order (first hit wins):
      1. Exact normalized name, raga-scoped
      2. Exact normalized name + same composer, raga-scoped
      3. pg_trgm similarity >= trgm_threshold, raga-scoped; tie-break by composer match
      4. Cross-raga exact normalized name (only when exactly one global candidate)

    When raga_name is None or "ragamalika" we skip raga-scoped passes and go
    straight to the cross-raga fallback.

    On a match, adds a PieceAlias if the supplied spelling differs from the
    canonical piece name.
    """
    from sqlalchemy import func

    norm = normalize_for_match(piece_name)
    if not norm:
        return None

    # Resolve raga DB row (None when raga unknown / ragamalika)
    raga_row = None
    if raga_name and raga_name != "ragamalika":
        raga_row = session.query(Raga).filter_by(name=raga_name).first()

    # Resolve composer DB row for tie-breaking
    composer_row = None
    if composer_name:
        composer_row = session.query(Composer).filter_by(name=composer_name).first()

    def _add_alias(piece) -> PieceMatch:
        ensure_piece_alias(session, PieceAlias, piece, piece_name)
        return PieceMatch(piece, "alias_added")

    # -----------------------------------------------------------------------
    # Raga-scoped passes
    # -----------------------------------------------------------------------
    if raga_row is not None:
        candidates = session.query(Piece).filter(Piece.raga_id == raga_row.id).all()

        # Pass 1: exact normalized name, raga-scoped
        exact = [p for p in candidates if normalize_for_match(p.name) == norm]
        if len(exact) == 1:
            m = PieceMatch(exact[0], "exact_norm_raga")
            ensure_piece_alias(session, PieceAlias, exact[0], piece_name)
            return m
        if len(exact) > 1:
            # Multiple pieces with same normalized name in same raga — pick by composer
            if composer_row:
                by_comp = [p for p in exact if p.composer_id == composer_row.id]
                if len(by_comp) == 1:
                    ensure_piece_alias(session, PieceAlias, by_comp[0], piece_name)
                    return PieceMatch(by_comp[0], "exact_norm_raga_composer")
            # Ambiguous: return first exact match
            ensure_piece_alias(session, PieceAlias, exact[0], piece_name)
            return PieceMatch(exact[0], "exact_norm_raga_ambiguous")

        # Pass 2: normalized name via aliases, raga-scoped
        for ar in (
            session.query(PieceAlias)
            .join(Piece)
            .filter(Piece.raga_id == raga_row.id)
            .all()
        ):
            if normalize_for_match(ar.alias) == norm:
                return PieceMatch(ar.piece, "exact_norm_alias_raga")

        # Pass 3: trigram similarity, raga-scoped; tie-break by composer
        min_len = 6
        threshold = trgm_threshold if len(norm) >= min_len else max(trgm_threshold, 0.55)

        trgm_hits = (
            session.query(Piece, func.similarity(Piece.name, norm).label("sim"))
            .filter(Piece.raga_id == raga_row.id)
            .filter(func.similarity(Piece.name, norm) >= threshold)
            .order_by(func.similarity(Piece.name, norm).desc())
            .all()
        )
        if trgm_hits:
            if composer_row:
                by_comp = [p for p, _ in trgm_hits if p.composer_id == composer_row.id]
                if by_comp:
                    ensure_piece_alias(session, PieceAlias, by_comp[0], piece_name)
                    return PieceMatch(by_comp[0], "trgm_raga_composer")
            best_piece, _ = trgm_hits[0]
            ensure_piece_alias(session, PieceAlias, best_piece, piece_name)
            return PieceMatch(best_piece, "trgm_raga")

    # -----------------------------------------------------------------------
    # Cross-raga fallback: exact normalized name, but only one global match
    # -----------------------------------------------------------------------
    global_exact = [
        p for p in session.query(Piece).all()
        if normalize_for_match(p.name) == norm
    ]
    if len(global_exact) == 1:
        ensure_piece_alias(session, PieceAlias, global_exact[0], piece_name)
        return PieceMatch(global_exact[0], "exact_norm_cross_raga")

    # Check aliases cross-raga
    global_alias_exact = [
        ar.piece for ar in session.query(PieceAlias).all()
        if normalize_for_match(ar.alias) == norm
    ]
    if len(global_alias_exact) == 1:
        return PieceMatch(global_alias_exact[0], "exact_norm_alias_cross_raga")

    return None


def _print_staged_records(staged: list) -> None:
    """Print all ORM objects created/added during this ingest run."""
    from collections import defaultdict

    by_type: dict[str, list] = defaultdict(list)
    for obj in staged:
        by_type[type(obj).__name__].append(obj)

    if not by_type:
        print("\nNo records staged in this run.")
        return

    print("\n--- Staged records (this run) ---")
    for type_name in sorted(by_type):
        rows = by_type[type_name]
        print(f"\n{type_name} ({len(rows)}):")
        for row in rows:
            print(f"  {row}")


def ingest(
    filepath: str,
    dry_run: bool = False,
    verbose: bool = False,
    sample: int | None = None,
):
    """Ingest concerts from cleaned_data.txt, matching setlist lines against the seeded master."""
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))
    from app import app, db, Concert, Artist, ConcertArtist, Raga, Talam, Composer, Piece, SetlistItem, PieceAlias, IngestDraft

    blocks = parse_file(filepath)
    if sample is not None:
        blocks = blocks[:sample]

    with app.app_context():
        stats = {
            "concerts": 0, "setlist_items": 0, "drafts": 0,
            "artists": 0, "aliases_added": 0,
        }
        staged: list = []

        for block in blocks:
            h = block.header

            if verbose:
                print(f"\n=== {h.youtube_id} | {h.title} ===")
                for ae in h.artist_entries:
                    instr = f" ({ae.instrument})" if ae.instrument else ""
                    print(f"  {ae.role}{instr}: {ae.name}")
                print(f"  year={h.year}  venue={h.venue}")

            # --- Concert ---
            concert, created = get_or_create(
                db.session, Concert,
                youtube_id=h.youtube_id,
                defaults={"title": h.title, "year": h.year, "venue": h.venue},
            )
            if created:
                stats["concerts"] += 1
                staged.append(concert)
            if verbose:
                print(
                    f"  [{_tag(created)}] Concert id={concert.id} "
                    f"youtube_id={concert.youtube_id!r} year={concert.year}"
                )

            # --- Artists ---
            for entry in h.artist_entries:
                artist, art_created = get_or_create(db.session, Artist, name=entry.name)
                if art_created:
                    stats["artists"] += 1
                    staged.append(artist)
                existing = db.session.query(ConcertArtist).filter_by(
                    concert_id=concert.id,
                    artist_id=artist.id,
                    instrument=entry.instrument,
                    role=entry.role,
                ).first()
                ca_created = False
                if not existing:
                    concert_artist = ConcertArtist(
                        concert_id=concert.id,
                        artist_id=artist.id,
                        role=entry.role,
                        instrument=entry.instrument,
                    )
                    db.session.add(concert_artist)
                    db.session.flush()
                    ca_created = True
                    staged.append(concert_artist)
                if verbose:
                    instr = f" ({entry.instrument})" if entry.instrument else ""
                    print(
                        f"  [{_tag(art_created)}] Artist id={artist.id} "
                        f"name={artist.name!r} role={entry.role}{instr}"
                    )
                    if ca_created:
                        print(
                            f"  [NEW] ConcertArtist concert_id={concert.id} "
                            f"artist_id={artist.id} role={entry.role!r}"
                            + (f" instrument={entry.instrument!r}" if entry.instrument else "")
                        )

            # --- Setlist lines ---
            for seq_idx, parsed_line in enumerate(block.lines, 1):
                cl = classify_tokens(parsed_line)
                seq = cl.sequence_number or seq_idx

                match: PieceMatch | None = None

                if cl.piece_name and cl.raga != "ragamalika":
                    match = resolve_master_piece(
                        db.session, Piece, PieceAlias, Raga, Composer,
                        cl.piece_name, cl.raga, cl.composer,
                    )

                if match:
                    piece = match.piece
                    alias_added = normalize_for_match(cl.piece_name) != normalize_for_match(piece.name)
                    if alias_added:
                        stats["aliases_added"] += 1

                    existing_si = db.session.query(SetlistItem).filter_by(
                        concert_id=concert.id,
                        sequence_number=seq,
                    ).first()
                    si_created = False
                    if not existing_si:
                        setlist_item = SetlistItem(
                            concert_id=concert.id,
                            piece_id=piece.id,
                            timestamp_seconds=cl.timestamp_seconds or 0,
                            sequence_number=seq,
                        )
                        db.session.add(setlist_item)
                        db.session.flush()
                        stats["setlist_items"] += 1
                        si_created = True
                        staged.append(setlist_item)

                    if verbose:
                        kind_str = f" kind={cl.kind}" if cl.kind else ""
                        raga_str = (piece.raga.name if piece.raga_id else cl.raga) or "?"
                        composer_str = piece.composer.name if piece.composer_id else "?"
                        alias_note = ", alias added" if alias_added else ""
                        print(
                            f"  [SETLIST] seq={seq} ts={_fmt_ts(cl.timestamp_seconds)} "
                            f"piece={piece.name!r} raga={raga_str} composer={composer_str}"
                            f"{kind_str} (via {match.method}{alias_note},"
                            f" si={'new' if si_created else 'dup'})"
                        )
                else:
                    draft = IngestDraft(
                        youtube_id=h.youtube_id,
                        sequence_number=seq,
                        timestamp_seconds=cl.timestamp_seconds,
                        raw_line=cl.raw,
                        parsed_piece=cl.piece_name,
                        parsed_raga=cl.raga,
                        parsed_talam=cl.talam,
                        parsed_composer=cl.composer,
                        parsed_kind=cl.kind,
                        confidence=cl.confidence,
                        status="needs_review",
                    )
                    db.session.add(draft)
                    stats["drafts"] += 1
                    staged.append(draft)
                    if verbose:
                        reason = "ragamalika" if cl.raga == "ragamalika" else "no master match"
                        print(
                            f"  [DRAFT]   seq={seq} ts={_fmt_ts(cl.timestamp_seconds)} "
                            f"piece={cl.piece_name!r} raga={cl.raga} composer={cl.composer} "
                            f"kind={cl.kind} conf={cl.confidence:.2f} ({reason})"
                        )

        if verbose:
            db.session.flush()
            _print_staged_records(staged)

        if dry_run:
            db.session.rollback()
            print("[DRY RUN] No changes committed.")
        else:
            db.session.commit()
            print("Ingestion committed.")

        print(f"\nResults:")
        print(f"  Concerts:       {stats['concerts']}")
        print(f"  Artists:        {stats['artists']}")
        print(f"  Aliases added:  {stats['aliases_added']}")
        print(f"  Setlist items:  {stats['setlist_items']}")
        print(f"  Drafts:         {stats['drafts']}")
        print(f"  Total lines:    {stats['setlist_items'] + stats['drafts']}")


# ---------------------------------------------------------------------------
# CLI: preview parse results
# ---------------------------------------------------------------------------

def preview():
    """Print parse diagnostics to stdout."""
    filepath = Path(__file__).parent / "desc_timestamps.txt"
    blocks = parse_file(str(filepath))

    total_lines = 0
    raga_hits = 0
    composer_hits = 0
    talam_hits = 0
    no_raga: list[tuple[str, ParsedLine]] = []

    for block in blocks:
        for pl in block.lines:
            total_lines += 1
            r = c = t = None
            for tok in pl.tokens:
                if not r:
                    r = lookup_raga(tok)
                if not c:
                    c = lookup_composer(tok)
                if not t:
                    t = lookup_talam(tok)
            if r:
                raga_hits += 1
            elif not pl.is_rtp and pl.kind not in ("mangalam", "tiruppugazh", "bhajan"):
                no_raga.append((block.header.youtube_id, pl))
            if c:
                composer_hits += 1
            if t:
                talam_hits += 1

    print(f"Parsed {len(blocks)} concerts, {total_lines} total lines\n")
    print(f"  Raga matches:     {raga_hits}/{total_lines} ({100*raga_hits/total_lines:.1f}%)")
    print(f"  Composer matches: {composer_hits}/{total_lines} ({100*composer_hits/total_lines:.1f}%)")
    print(f"  Talam matches:    {talam_hits}/{total_lines} ({100*talam_hits/total_lines:.1f}%)")
    print(f"\n  Unmatched ragas: {len(no_raga)} lines (candidates for draft records)")
    for yt_id, pl in no_raga[:15]:
        print(f"    [{yt_id}] {pl.tokens}")


def _parse_cli_sample(argv: list[str]) -> int | None:
    for i, arg in enumerate(argv):
        if arg == "--sample" and i + 1 < len(argv):
            return int(argv[i + 1])
        if arg.startswith("--sample="):
            return int(arg.split("=", 1)[1])
    return None


if __name__ == "__main__":
    filepath = str(Path(__file__).parent / "cleaned_data.txt")
    verbose = "--verbose" in sys.argv
    sample = _parse_cli_sample(sys.argv)
    dry_run = "--dry-run" in sys.argv

    if "--full" in sys.argv:
        wipe(dry_run=dry_run)
        seed_master(dry_run=dry_run, verbose=verbose)
        ingest(filepath, dry_run=dry_run, verbose=verbose, sample=sample)
    elif "--wipe" in sys.argv:
        wipe(dry_run=dry_run)
    elif "--seed-master" in sys.argv:
        seed_master(dry_run=dry_run, verbose=verbose)
    elif "--ingest-concerts" in sys.argv:
        ingest(filepath, dry_run=dry_run, verbose=verbose, sample=sample)
    elif "--preview" in sys.argv:
        preview()
    elif "--classify" in sys.argv:
        blocks = parse_file(filepath)
        full = 0
        draft = 0
        missing = {"piece": 0, "raga": 0, "composer": 0, "talam": 0, "low_conf": 0}
        for block in blocks:
            for pl in block.lines:
                cl = classify_tokens(pl)
                if cl.confidence >= 0.5 and cl.piece_name and cl.raga and cl.composer and cl.talam:
                    full += 1
                else:
                    draft += 1
                    if cl.confidence < 0.5:
                        missing["low_conf"] += 1
                    if not cl.piece_name:
                        missing["piece"] += 1
                    if not cl.raga:
                        missing["raga"] += 1
                    if not cl.composer:
                        missing["composer"] += 1
                    if not cl.talam:
                        missing["talam"] += 1
        total = full + draft
        print(f"Classification results ({total} lines):")
        print(f"  Full records:  {full} ({100*full/total:.1f}%)")
        print(f"  Draft records: {draft} ({100*draft/total:.1f}%)")
        print(f"\n  Draft breakdown (a line can have multiple missing fields):")
        print(f"    Missing composer: {missing['composer']}")
        print(f"    Missing talam:    {missing['talam']}")
        print(f"    Missing raga:     {missing['raga']}")
        print(f"    Missing piece:    {missing['piece']}")
        print(f"    Low confidence:   {missing['low_conf']}")
    elif "--dry-run" in sys.argv:
        ingest(filepath, dry_run=True, verbose=verbose, sample=sample)
    elif "--ingest" in sys.argv:
        ingest(filepath, dry_run=False, verbose=verbose, sample=sample)
    else:
        print("Usage: python populate_db.py <command> [options]")
        print("")
        print("Commands:")
        print("  --full            Wipe + seed master + ingest concerts")
        print("  --wipe            Truncate all entity tables and reset sequences")
        print("  --seed-master     Seed ragas/talams/composers/pieces from pieces_master.csv")
        print("  --ingest-concerts Ingest concerts from cleaned_data.txt")
        print("  --preview         Print parse diagnostics (no DB)")
        print("  --classify        Classify lines and show field-coverage stats")
        print("")
        print("Options:")
        print("  --dry-run         Roll back after run (no DB changes)")
        print("  --verbose         Print each record as it is created")
        print("  --sample N        Process only the first N concerts")
