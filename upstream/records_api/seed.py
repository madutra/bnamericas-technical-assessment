"""Deterministic fictional seed data. Every name here is invented."""

import random
from datetime import date, timedelta

SECTORS = {
    "energy": ["Solar Park", "Wind Farm", "Transmission Line"],
    "mining": ["Copper Expansion", "Lithium Project", "Tailings Facility"],
    "water": ["Desalination Plant", "Water Treatment Plant"],
    "transport": ["Port Terminal", "Highway Concession", "Metro Line"],
    "oil_and_gas": ["Gas Pipeline", "LNG Terminal"],
    "ict": ["Fiber Backbone", "Data Center"],
}
STAGES = ["idea", "feasibility", "tender", "financing", "construction", "operation", "cancelled"]
COUNTRIES = ["Argentina", "Brazil", "Chile", "Colombia", "Mexico", "Peru"]
COMPANY_ROLES = ["owner", "developer", "epc_contractor", "financier", "consultant"]

_PLACES = ["Cerro Talvi", "Rio Quemen", "Punta Oriveta", "Valle Nevasco", "Laguna Maduri",
           "Bahia Corvalia", "Loma Quintora", "Paso Lumbara", "Llano Varelo", "Monte Ilqui"]
_COMPANY_STEMS = ["Varelo", "Quintora", "Maduri", "Talcora", "Nevasco", "Corvalia", "Lumbara", "Oriveta"]
_COMPANY_KINDS = ["Energia", "Minera", "Infraestructura", "Ingenieria", "Capital", "Obras"]
_COMPANY_FORMS = ["SA", "SpA", "SAC", "SAS"]
_DATE_LABELS = ["Feasibility study completed", "Tender launch", "Financial close",
                "Construction start", "Commercial operation"]
_CAPACITY_UNITS = {"energy": "MW", "mining": "ktpa", "water": "l/s", "transport": "km",
                   "oil_and_gas": "MMcfd", "ict": "Gbps"}


def build_projects(seed: int = 2026, count: int = 30) -> dict[str, dict]:
    rng = random.Random(seed)
    projects: dict[str, dict] = {}
    for n in range(count):
        project_id = f"P-{1001 + n}"
        sector = rng.choice(list(SECTORS))
        country = rng.choice(COUNTRIES)
        start = date(2025, 1, 1) + timedelta(days=rng.randint(0, 700))
        labels = rng.sample(_DATE_LABELS, k=rng.randint(2, 4))
        key_dates = [
            {"label": label, "date": (start + timedelta(days=200 * i)).isoformat()}
            for i, label in enumerate(sorted(labels, key=_DATE_LABELS.index))
        ]
        companies = [
            {
                "name": f"{rng.choice(_COMPANY_STEMS)} {rng.choice(_COMPANY_KINDS)} {rng.choice(_COMPANY_FORMS)}",
                "role": role,
            }
            for role in rng.sample(COMPANY_ROLES, k=rng.randint(1, 3))
        ]
        name = f"{rng.choice(_PLACES)} {rng.choice(SECTORS[sector])}"
        projects[project_id] = {
            "id": project_id,
            # Editable fields
            "name": name,
            "sector": sector,
            "country": country,
            "stage": rng.choice(STAGES),
            "key_dates": key_dates,
            "linked_companies": companies,
            # Read-only fields owned by other systems; the UI does not need them
            "internal_code": f"IC-{rng.randint(100000, 999999)}",
            "region": rng.choice(["north", "centre", "south", "coast", "highlands"]),
            "description": f"Fictional {sector.replace('_', ' ')} project in {country}, used for testing only.",
            "investment_usd_m": round(rng.uniform(15, 4500), 1),
            "currency": "USD",
            "capacity": round(rng.uniform(5, 900), 1),
            "capacity_unit": _CAPACITY_UNITS[sector],
            "latitude": round(rng.uniform(-45, 20), 5),
            "longitude": round(rng.uniform(-80, -40), 5),
            "tags": rng.sample(["ppp", "greenfield", "brownfield", "export", "public", "private"], k=2),
            "owner_team": rng.choice(["team-a", "team-b", "team-c"]),
            "data_quality_score": rng.randint(40, 100),
            "source_count": rng.randint(1, 12),
            "legacy_ref": f"LEG/{rng.randint(1, 9)}/{rng.randint(1000, 9999)}",
            "is_featured": rng.random() < 0.2,
            "visibility": rng.choice(["standard", "restricted"]),
        }
    return projects
