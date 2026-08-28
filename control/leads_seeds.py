"""Israeli mid-size businesses with public sites — fallback when search engines block bots."""

from __future__ import annotations

CITIES = (
    "רעננה",
    "הרצליה",
    "כפר סבא",
    "רמת גן",
    "פתח תקווה",
    "נתניה",
    "ראשון לציון",
    "רחובות",
    "אשדוד",
    "חיפה",
    "באר שבע",
    "מודיעין",
    "הוד השרון",
    "גבעתיים",
    "חולון",
    "נס ציונה",
    "ראש העין",
    "קריית אונו",
    "יבנה",
    "רמת השרון",
)

CITY_TEMPLATES = (
    ("סוכנות ביטוח {city}", "insurance"),
    ("סוכנות לביטוח {city} משרד", "insurance"),
    ("משרד תיווך {city}", "realestate"),
    ("קליניקה אסתטיקה {city}", "clinics"),
    ("יועץ משכנתאות {city}", "mortgage"),
    ("יבואן סיטונאי {city}", "import"),
)

EXTRA_QUERIES = (
    ("סוכנות ביטוח עצמאית ישראל אתר", "insurance"),
    ("סוכן ביטוח פנסיוני משרד ישראל", "insurance"),
    ("סוכנות ביטוח משפחתית צור קשר", "insurance"),
    ("סוכנות ביטוח נתניה משרד", "insurance"),
    ("סוכנות ביטוח פתח תקווה", "insurance"),
    ("משרד תיווך בוטיק תל אביב", "realestate"),
    ("תיווך נדלן משרד רעננה", "realestate"),
    ("משרד תיווך הרצליה דירות", "realestate"),
    ("קליניקה לרפואה אסתטית ישראל", "clinics"),
    ("קליניקת אסתטיקה רעננה", "clinics"),
    ("יועץ משכנתאות עצמאי ישראל", "mortgage"),
    ("ייעוץ משכנתאות משרד רמת גן", "mortgage"),
    ("יועץ משכנתא הרצליה משרד", "mortgage"),
    ("חברה משפחתית יבוא סיטונאות ישראל", "import"),
    ("סיטונאות מזון משפחתית ישראל", "import"),
    ("מפיץ חומרי בניין משפחתי ישראל", "import"),
)

# Boutique / owner-operated sites. Giants are listed in SKIP_HOSTS in research.
SEED_URLS = [
    "https://www.sides-ins.co.il/",
    "https://ramib.co.il/",
    "https://www.manor.co.il/",
    "https://rotlevins.co.il/",
    "https://www.danbit.co.il/",
    "https://livshalom.co.il/",
    "https://www.shaldan.co.il/",
    "https://www.notaly.co.il/",
    "https://oig.co.il/",
    "https://as-titanum.com/",
    "https://www.h-cohen.co.il/",
    "https://segalovich.co.il/",
    "https://www.kaplan-re.co.il/",
    "https://www.gaiahome.co.il/",
    "https://duoo.co.il/",
    "https://b-n.co.il/",
    "https://drhightune.co.il/",
    "https://drchenshevel.co.il/",
    "https://drmosherosen.co.il/",
    "https://aby.clinic/",
    "https://mpersonal.co.il/",
    "https://my-mashkanta.co.il/",
    "https://www.visman.co.il/",
    "https://eliyau-mortgage.co.il/",
    "https://www.win-win.co.il/",
    "https://www.nadlanit.co.il/",
    "https://www.mashkanta.co.il/",
    "https://www.ipm.co.il/",
    "https://www.mashkanta-plus.co.il/",
    "https://www.sela-ins.co.il/",
    "https://www.smartins.co.il/",
    "https://www.yashir-ins.co.il/",
    "https://www.insureme.co.il/",
    "https://www.barlev-ins.co.il/",
    "https://www.amt-ins.co.il/",
    "https://www.home-israel.co.il/",
]


def city_queries() -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for city in CITIES:
        for tmpl, vert in CITY_TEMPLATES:
            out.append((tmpl.format(city=city), vert))
    return out
