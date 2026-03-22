from __future__ import annotations

from functools import lru_cache

from app.services.convex_client import convex


RegistryEntry = dict[str, object]

STATE_UNEMPLOYMENT = [
    ("ALUR", "Alabama Unemployment Rate", "state", ["alabama", "labor", "employment"]),
    ("AKUR", "Alaska Unemployment Rate", "state", ["alaska", "labor", "employment"]),
    ("AZUR", "Arizona Unemployment Rate", "state", ["arizona", "labor", "employment"]),
    ("CAUR", "California Unemployment Rate", "state", ["california", "labor", "employment"]),
    ("COUR", "Colorado Unemployment Rate", "state", ["colorado", "labor", "employment"]),
    ("CTUR", "Connecticut Unemployment Rate", "state", ["connecticut", "labor", "employment"]),
    ("FLUR", "Florida Unemployment Rate", "state", ["florida", "labor", "employment"]),
    ("GAUR", "Georgia Unemployment Rate", "state", ["georgia", "labor", "employment"]),
    ("ILUR", "Illinois Unemployment Rate", "state", ["illinois", "labor", "employment"]),
    ("INUR", "Indiana Unemployment Rate", "state", ["indiana", "labor", "employment"]),
    ("MAUR", "Massachusetts Unemployment Rate", "state", ["massachusetts", "labor", "employment"]),
    ("MDUR", "Maryland Unemployment Rate", "state", ["maryland", "labor", "employment"]),
    ("MIUR", "Michigan Unemployment Rate", "state", ["michigan", "labor", "employment"]),
    ("MNUR", "Minnesota Unemployment Rate", "state", ["minnesota", "labor", "employment"]),
    ("MOUR", "Missouri Unemployment Rate", "state", ["missouri", "labor", "employment"]),
    ("NCUR", "North Carolina Unemployment Rate", "state", ["north carolina", "labor", "employment"]),
    ("NJUR", "New Jersey Unemployment Rate", "state", ["new jersey", "labor", "employment"]),
    ("NYUR", "New York Unemployment Rate", "state", ["new york", "labor", "employment"]),
    ("OHUR", "Ohio Unemployment Rate", "state", ["ohio", "labor", "employment"]),
    ("ORUR", "Oregon Unemployment Rate", "state", ["oregon", "labor", "employment"]),
    ("PAUR", "Pennsylvania Unemployment Rate", "state", ["pennsylvania", "labor", "employment"]),
    ("TNUR", "Tennessee Unemployment Rate", "state", ["tennessee", "labor", "employment"]),
    ("TXUR", "Texas Unemployment Rate", "state", ["texas", "labor", "employment"]),
    ("VAUR", "Virginia Unemployment Rate", "state", ["virginia", "labor", "employment"]),
    ("WAUR", "Washington Unemployment Rate", "state", ["washington", "labor", "employment"]),
    ("WIUR", "Wisconsin Unemployment Rate", "state", ["wisconsin", "labor", "employment"]),
]


def _fred_yaml(series_id: str) -> str:
    return "\n".join([
        f"name: fred_{series_id.lower()}",
        "type: api",
        "url: https://api.stlouisfed.org/fred/series/observations",
        "response_format: json",
        "params:",
        f"  series_id: {series_id}",
        "  api_key: ${FRED_API_KEY}",
        "  file_type: json",
        "fields:",
        "  - source: observations[].date",
        "    alias: date",
        "  - source: observations[].value",
        "    alias: value",
    ])


def _census_yaml(variable_id: str) -> str:
    return "\n".join([
        f"name: census_{variable_id.lower()}",
        "type: api",
        "url: https://api.census.gov/data/2023/acs/acs5",
        "response_format: census_array",
        "params:",
        f"  get: NAME,{variable_id}",
        "  for: state:*",
        "fields:",
        "  - source: NAME",
        "    alias: geography_name",
        f"  - source: {variable_id}",
        "    alias: value",
    ])


def _worldbank_yaml(indicator_id: str) -> str:
    return "\n".join([
        f"name: worldbank_{indicator_id.lower().replace('.', '_')}",
        "type: api",
        "url: https://api.worldbank.org/v2/country/USA/indicator/" + indicator_id,
        "response_format: json",
        "params:",
        "  format: json",
        "  per_page: 500",
        "fields:",
        "  - source: 1[].date",
        "    alias: date",
        "  - source: 1[].value",
        "    alias: value",
    ])


def _bls_yaml(series_id: str) -> str:
    return "\n".join([
        f"name: bls_{series_id.lower()}",
        "type: api",
        "url: https://api.bls.gov/publicAPI/v2/timeseries/data/",
        "response_format: json",
        "body:",
        f"  seriesid: [{series_id}]",
        "fields:",
        "  - source: Results.series[0].data[].year",
        "    alias: year",
        "  - source: Results.series[0].data[].value",
        "    alias: value",
    ])


def _entry(
    provider: str,
    source_id: str,
    name: str,
    description: str,
    unit: str,
    frequency: str,
    geography: str,
    tags: list[str],
    example_yaml: str,
) -> RegistryEntry:
    return {
        "provider": provider,
        "id": source_id,
        "name": name,
        "description": description,
        "unit": unit,
        "frequency": frequency,
        "geography": geography,
        "tags": tags,
        "exampleYaml": example_yaml,
        "updatedAt": 0,
    }


@lru_cache(maxsize=1)
def default_registry_entries() -> list[RegistryEntry]:
    fred_entries: list[RegistryEntry] = [
        _entry("fred", "UNRATE", "Unemployment Rate", "Civilian unemployment rate for the United States.", "percent", "monthly", "national", ["labor", "employment", "unemployment"], _fred_yaml("UNRATE")),
        _entry("fred", "CPIAUCSL", "Consumer Price Index for All Urban Consumers: All Items", "Headline CPI index for urban consumers.", "index", "monthly", "national", ["inflation", "prices", "cpi"], _fred_yaml("CPIAUCSL")),
        _entry("fred", "CPILFESL", "Consumer Price Index Less Food and Energy", "Core CPI index excluding food and energy.", "index", "monthly", "national", ["inflation", "prices", "core cpi"], _fred_yaml("CPILFESL")),
        _entry("fred", "FEDFUNDS", "Effective Federal Funds Rate", "Effective federal funds interest rate.", "percent", "monthly", "national", ["interest rates", "federal reserve", "monetary policy"], _fred_yaml("FEDFUNDS")),
        _entry("fred", "DFF", "Effective Federal Funds Rate (Daily)", "Daily effective federal funds rate.", "percent", "daily", "national", ["interest rates", "federal reserve", "daily"], _fred_yaml("DFF")),
        _entry("fred", "DGS10", "10-Year Treasury Constant Maturity Rate", "Market yield on U.S. Treasury securities at 10-year maturity.", "percent", "daily", "national", ["interest rates", "treasury", "bonds"], _fred_yaml("DGS10")),
        _entry("fred", "DGS2", "2-Year Treasury Constant Maturity Rate", "Market yield on U.S. Treasury securities at 2-year maturity.", "percent", "daily", "national", ["interest rates", "treasury", "bonds"], _fred_yaml("DGS2")),
        _entry("fred", "GDP", "Gross Domestic Product", "Current-dollar gross domestic product.", "dollars", "quarterly", "national", ["gdp", "output", "macro"], _fred_yaml("GDP")),
        _entry("fred", "GDPC1", "Real Gross Domestic Product", "Real gross domestic product in chained dollars.", "dollars", "quarterly", "national", ["gdp", "output", "real gdp"], _fred_yaml("GDPC1")),
        _entry("fred", "PCE", "Personal Consumption Expenditures", "Nominal personal consumption expenditures.", "dollars", "monthly", "national", ["consumption", "spending"], _fred_yaml("PCE")),
        _entry("fred", "PAYEMS", "All Employees, Total Nonfarm", "Total nonfarm payroll employment.", "persons", "monthly", "national", ["employment", "payrolls", "labor"], _fred_yaml("PAYEMS")),
        _entry("fred", "ICSA", "Initial Claims", "Initial claims for unemployment insurance.", "claims", "weekly", "national", ["unemployment", "claims", "labor"], _fred_yaml("ICSA")),
        _entry("fred", "HOUST", "Housing Starts", "New privately owned housing units started.", "units", "monthly", "national", ["housing", "construction"], _fred_yaml("HOUST")),
        _entry("fred", "MORTGAGE30US", "30-Year Fixed Rate Mortgage Average", "Average commitment rate on 30-year fixed-rate mortgages.", "percent", "weekly", "national", ["housing", "mortgage", "interest rates"], _fred_yaml("MORTGAGE30US")),
        _entry("fred", "RSAFS", "Advance Retail Sales: Retail and Food Services", "Advance retail and food services sales.", "dollars", "monthly", "national", ["retail", "consumption", "sales"], _fred_yaml("RSAFS")),
        _entry("fred", "INDPRO", "Industrial Production: Total Index", "Federal Reserve industrial production index.", "index", "monthly", "national", ["industry", "manufacturing", "production"], _fred_yaml("INDPRO")),
        _entry("fred", "UMCSENT", "University of Michigan: Consumer Sentiment", "Consumer sentiment survey index.", "index", "monthly", "national", ["sentiment", "consumers", "survey"], _fred_yaml("UMCSENT")),
        _entry("fred", "CIVPART", "Labor Force Participation Rate", "Civilian labor force participation rate.", "percent", "monthly", "national", ["labor", "participation", "employment"], _fred_yaml("CIVPART")),
        _entry("fred", "EMRATIO", "Employment-Population Ratio", "Civilian employment-population ratio.", "percent", "monthly", "national", ["labor", "employment", "population"], _fred_yaml("EMRATIO")),
        _entry("fred", "DEXUSEU", "U.S. / Euro Foreign Exchange Rate", "U.S. dollars to euro exchange rate.", "usd per eur", "daily", "national", ["exchange rates", "trade", "currency"], _fred_yaml("DEXUSEU")),
        _entry("fred", "CSUSHPINSA", "S&P CoreLogic Case-Shiller U.S. National Home Price Index", "National home price index.", "index", "monthly", "national", ["housing", "home prices"], _fred_yaml("CSUSHPINSA")),
        _entry("fred", "TOTALSL", "Consumer Credit Outstanding", "Total consumer credit outstanding.", "dollars", "monthly", "national", ["credit", "households", "debt"], _fred_yaml("TOTALSL")),
        _entry("fred", "BUSLOANS", "Commercial and Industrial Loans", "Commercial and industrial loans, all commercial banks.", "dollars", "weekly", "national", ["banking", "credit", "business"], _fred_yaml("BUSLOANS")),
        _entry("fred", "WTISPLC", "Crude Oil Prices: West Texas Intermediate", "Spot price for WTI crude oil.", "dollars per barrel", "daily", "national", ["energy", "oil", "commodities"], _fred_yaml("WTISPLC")),
    ]

    fred_entries.extend(
        _entry(
            "fred",
            series_id,
            name,
            f"State-level unemployment rate series for {name.split(' Unemployment Rate')[0]}.",
            "percent",
            "monthly",
            geography,
            ["unemployment", *tags],
            _fred_yaml(series_id),
        )
        for series_id, name, geography, tags in STATE_UNEMPLOYMENT
    )

    census_entries: list[RegistryEntry] = [
        _entry("census", "B01003_001E", "Total Population", "ACS 5-year estimate of total population.", "persons", "annual", "state", ["population", "acs", "demographics"], _census_yaml("B01003_001E")),
        _entry("census", "B19013_001E", "Median Household Income", "ACS 5-year estimate of median household income.", "dollars", "annual", "state", ["income", "households", "acs"], _census_yaml("B19013_001E")),
        _entry("census", "B17001_002E", "Population Below Poverty Level", "ACS 5-year estimate of people below poverty level.", "persons", "annual", "state", ["poverty", "income", "acs"], _census_yaml("B17001_002E")),
        _entry("census", "B25077_001E", "Median Home Value", "ACS 5-year estimate of median owner-occupied home value.", "dollars", "annual", "state", ["housing", "home values", "acs"], _census_yaml("B25077_001E")),
        _entry("census", "B25064_001E", "Median Gross Rent", "ACS 5-year estimate of median gross rent.", "dollars", "annual", "state", ["housing", "rent", "acs"], _census_yaml("B25064_001E")),
        _entry("census", "B23025_003E", "Civilian Labor Force", "ACS 5-year estimate of the civilian labor force.", "persons", "annual", "state", ["labor", "employment", "acs"], _census_yaml("B23025_003E")),
        _entry("census", "B23025_005E", "Unemployed Population", "ACS 5-year estimate of unemployed civilians in the labor force.", "persons", "annual", "state", ["labor", "unemployment", "acs"], _census_yaml("B23025_005E")),
        _entry("census", "B23025_004E", "Employed Population", "ACS 5-year estimate of employed civilians.", "persons", "annual", "state", ["labor", "employment", "acs"], _census_yaml("B23025_004E")),
        _entry("census", "B15003_022E", "Bachelor's Degree Holders", "ACS 5-year estimate of people with a bachelor's degree.", "persons", "annual", "state", ["education", "degrees", "acs"], _census_yaml("B15003_022E")),
        _entry("census", "B15003_023E", "Master's Degree Holders", "ACS 5-year estimate of people with a master's degree.", "persons", "annual", "state", ["education", "degrees", "acs"], _census_yaml("B15003_023E")),
        _entry("census", "B15003_024E", "Professional School Degree Holders", "ACS 5-year estimate of people with professional school degrees.", "persons", "annual", "state", ["education", "degrees", "acs"], _census_yaml("B15003_024E")),
        _entry("census", "B15003_025E", "Doctorate Degree Holders", "ACS 5-year estimate of people with doctorates.", "persons", "annual", "state", ["education", "degrees", "acs"], _census_yaml("B15003_025E")),
        _entry("census", "B25002_001E", "Total Housing Units", "ACS 5-year estimate of total housing units.", "units", "annual", "state", ["housing", "units", "acs"], _census_yaml("B25002_001E")),
        _entry("census", "B25002_002E", "Occupied Housing Units", "ACS 5-year estimate of occupied housing units.", "units", "annual", "state", ["housing", "occupancy", "acs"], _census_yaml("B25002_002E")),
        _entry("census", "B25002_003E", "Vacant Housing Units", "ACS 5-year estimate of vacant housing units.", "units", "annual", "state", ["housing", "vacancy", "acs"], _census_yaml("B25002_003E")),
        _entry("census", "B25003_002E", "Owner Occupied Housing Units", "ACS 5-year estimate of owner occupied housing units.", "units", "annual", "state", ["housing", "ownership", "acs"], _census_yaml("B25003_002E")),
        _entry("census", "B25003_003E", "Renter Occupied Housing Units", "ACS 5-year estimate of renter occupied housing units.", "units", "annual", "state", ["housing", "renters", "acs"], _census_yaml("B25003_003E")),
        _entry("census", "B08303_001E", "Workers 16 Years and Over", "ACS 5-year estimate of workers 16 years and over.", "persons", "annual", "state", ["commute", "workers", "acs"], _census_yaml("B08303_001E")),
        _entry("census", "B08303_010E", "Commute Time 25 to 29 Minutes", "ACS 5-year estimate of workers with 25 to 29 minute commute.", "persons", "annual", "state", ["commute", "transportation", "acs"], _census_yaml("B08303_010E")),
        _entry("census", "B08301_010E", "Public Transportation to Work", "ACS 5-year estimate of workers commuting by public transportation.", "persons", "annual", "state", ["commute", "transit", "acs"], _census_yaml("B08301_010E")),
    ]

    world_bank_entries: list[RegistryEntry] = [
        _entry("worldbank", "NY.GDP.MKTP.CD", "GDP (current US$)", "World Bank estimate of GDP in current U.S. dollars.", "dollars", "annual", "national", ["gdp", "world bank", "macro"], _worldbank_yaml("NY.GDP.MKTP.CD")),
        _entry("worldbank", "NY.GDP.PCAP.CD", "GDP per capita (current US$)", "World Bank estimate of GDP per capita.", "dollars", "annual", "national", ["gdp", "income", "world bank"], _worldbank_yaml("NY.GDP.PCAP.CD")),
        _entry("worldbank", "SP.POP.TOTL", "Population, total", "World Bank estimate of total population.", "persons", "annual", "national", ["population", "demographics", "world bank"], _worldbank_yaml("SP.POP.TOTL")),
        _entry("worldbank", "SL.UEM.TOTL.ZS", "Unemployment, total (% of total labor force)", "Modeled ILO estimate of total unemployment rate.", "percent", "annual", "national", ["unemployment", "labor", "world bank"], _worldbank_yaml("SL.UEM.TOTL.ZS")),
        _entry("worldbank", "FP.CPI.TOTL.ZG", "Inflation, consumer prices (annual %)", "Consumer price inflation, annual percent.", "percent", "annual", "national", ["inflation", "prices", "world bank"], _worldbank_yaml("FP.CPI.TOTL.ZG")),
        _entry("worldbank", "NE.TRD.GNFS.ZS", "Trade (% of GDP)", "Sum of exports and imports of goods and services as a share of GDP.", "percent", "annual", "national", ["trade", "gdp", "world bank"], _worldbank_yaml("NE.TRD.GNFS.ZS")),
        _entry("worldbank", "BX.KLT.DINV.CD.WD", "Foreign direct investment, net inflows (BoP, current US$)", "Foreign direct investment inflows.", "dollars", "annual", "national", ["investment", "fdi", "world bank"], _worldbank_yaml("BX.KLT.DINV.CD.WD")),
        _entry("worldbank", "GC.DOD.TOTL.GD.ZS", "Central government debt, total (% of GDP)", "Central government debt as a share of GDP.", "percent", "annual", "national", ["debt", "fiscal", "world bank"], _worldbank_yaml("GC.DOD.TOTL.GD.ZS")),
        _entry("worldbank", "SE.ADT.LITR.ZS", "Literacy rate, adult total (% of people ages 15 and above)", "Adult literacy rate.", "percent", "annual", "national", ["education", "literacy", "world bank"], _worldbank_yaml("SE.ADT.LITR.ZS")),
        _entry("worldbank", "EN.ATM.CO2E.PC", "CO2 emissions (metric tons per capita)", "Per-capita carbon dioxide emissions.", "metric tons per capita", "annual", "national", ["environment", "emissions", "world bank"], _worldbank_yaml("EN.ATM.CO2E.PC")),
    ]

    bls_entries: list[RegistryEntry] = [
        _entry("bls", "CUUR0000SA0", "CPI-U, All Items, U.S. City Average", "Headline CPI-U for all urban consumers.", "index", "monthly", "national", ["cpi", "inflation", "prices"], _bls_yaml("CUUR0000SA0")),
        _entry("bls", "CUUR0000SA0L1E", "CPI-U Less Food and Energy", "Core CPI-U excluding food and energy.", "index", "monthly", "national", ["cpi", "inflation", "core"], _bls_yaml("CUUR0000SA0L1E")),
        _entry("bls", "CEU0000000001", "All Employees, Total Nonfarm", "CES total nonfarm employment.", "persons", "monthly", "national", ["employment", "payrolls", "ces"], _bls_yaml("CEU0000000001")),
        _entry("bls", "CEU0500000001", "All Employees, Total Private", "CES total private employment.", "persons", "monthly", "national", ["employment", "private sector", "ces"], _bls_yaml("CEU0500000001")),
        _entry("bls", "CEU3000000001", "All Employees, Manufacturing", "CES manufacturing employment.", "persons", "monthly", "national", ["employment", "manufacturing", "ces"], _bls_yaml("CEU3000000001")),
        _entry("bls", "CES0500000003", "Average Hourly Earnings, Total Private", "Average hourly earnings of all employees, total private.", "dollars", "monthly", "national", ["wages", "earnings", "ces"], _bls_yaml("CES0500000003")),
        _entry("bls", "LNS14000000", "Unemployment Level", "National unemployment level from CPS.", "persons", "monthly", "national", ["unemployment", "labor", "cps"], _bls_yaml("LNS14000000")),
        _entry("bls", "LNS11300000", "Labor Force Participation Rate", "Labor force participation rate from CPS.", "percent", "monthly", "national", ["labor", "participation", "cps"], _bls_yaml("LNS11300000")),
        _entry("bls", "LNS12300000", "Employment-Population Ratio", "Employment-population ratio from CPS.", "percent", "monthly", "national", ["employment", "population", "cps"], _bls_yaml("LNS12300000")),
        _entry("bls", "PCUOMFGOMFG", "PPI by Industry: Total Manufacturing Industries", "Producer price index for total manufacturing industries.", "index", "monthly", "national", ["ppi", "manufacturing", "prices"], _bls_yaml("PCUOMFGOMFG")),
    ]

    return fred_entries + census_entries + world_bank_entries + bls_entries


def _normalize_custom_entry(entry: dict) -> RegistryEntry:
    return {
        "provider": entry["provider"],
        "id": entry["sourceId"],
        "name": entry["name"],
        "description": entry["description"],
        "unit": entry["unit"],
        "frequency": entry["frequency"],
        "geography": entry["geography"],
        "tags": entry.get("tags", []),
        "exampleYaml": entry["exampleYaml"],
        "updatedAt": entry.get("updatedAt", 0),
    }


async def list_custom_entries(limit: int = 200) -> list[RegistryEntry]:
    try:
        results = await convex.query("registry:list", {"limit": limit})
    except Exception:
        return []
    return [_normalize_custom_entry(item) for item in (results or [])]


async def create_registry_entry(entry: RegistryEntry) -> dict:
    updated_at = entry.get("updatedAt")
    payload = {
        "provider": str(entry["provider"]),
        "sourceId": str(entry["id"]),
        "name": str(entry["name"]),
        "description": str(entry["description"]),
        "unit": str(entry["unit"]),
        "frequency": str(entry["frequency"]),
        "geography": str(entry["geography"]),
        "tags": [str(tag) for tag in entry.get("tags", [])],
        "exampleYaml": str(entry["exampleYaml"]),
        "updatedAt": int(updated_at) if updated_at is not None else None,
    }
    await convex.mutation("registry:create", payload)
    return payload | {"id": payload["sourceId"], "updatedAt": payload["updatedAt"] or 0}


async def get_registry_entry(provider: str, source_id: str) -> RegistryEntry | None:
    custom = await convex.query("registry:get", {"provider": provider, "sourceId": source_id})
    if custom:
        return _normalize_custom_entry(custom)

    for entry in default_registry_entries():
        if entry["provider"] == provider and entry["id"] == source_id:
            return entry
    return None


def _entry_score(entry: RegistryEntry, query_text: str) -> tuple[int, str]:
    if not query_text:
        return (0, str(entry["name"]).lower())
    query_lower = query_text.lower()
    name = str(entry["name"]).lower()
    source_id = str(entry["id"]).lower()
    tags = [str(tag).lower() for tag in entry.get("tags", [])]
    description = str(entry["description"]).lower()

    score = 0
    if name.startswith(query_lower):
        score += 8
    if query_lower in name:
        score += 4
    if query_lower == source_id:
        score += 7
    elif query_lower in source_id:
        score += 3
    if any(query_lower in tag for tag in tags):
        score += 2
    if query_lower in description:
        score += 1
    return (-score, name)


def _matches(entry: RegistryEntry, query_text: str, provider: str | None, geography: str | None) -> bool:
    if provider and entry["provider"] != provider:
        return False
    if geography and entry["geography"] != geography:
        return False
    if not query_text:
        return True
    haystack = " ".join([
        str(entry["id"]),
        str(entry["name"]),
        str(entry["description"]),
        str(entry["geography"]),
        *[str(tag) for tag in entry.get("tags", [])],
    ]).lower()
    return query_text.lower() in haystack


async def search_registry_entries(
    query_text: str = "",
    provider: str | None = None,
    geography: str | None = None,
    limit: int = 20,
) -> list[RegistryEntry]:
    merged: dict[tuple[str, str], RegistryEntry] = {
        (str(entry["provider"]), str(entry["id"])): entry
        for entry in default_registry_entries()
    }
    for entry in await list_custom_entries(limit=500):
        merged[(str(entry["provider"]), str(entry["id"]))] = entry

    results = [
        entry for entry in merged.values()
        if _matches(entry, query_text, provider, geography)
    ]
    results.sort(key=lambda item: _entry_score(item, query_text))
    return results[:limit]
