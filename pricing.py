"""
Kennewick Cleaning Company — Automated Pricing Engine
Calculates job prices based on service type, bedrooms, bathrooms, sqft, and condition.
"""

# Base prices per service type
SERVICE_TYPES = {
    "simple_clean": {
        "label": "Simple Clean",
        "description": "Light touch-up: surfaces, vacuum, mop",
        "base": 80,
        "per_bedroom": 20,
        "per_bathroom": 15,
        "estimated_hours_base": 1.0,
        "hours_per_bedroom": 0.25,
        "hours_per_bathroom": 0.2,
    },
    "standard_clean": {
        "label": "Standard Clean",
        "description": "Full clean: kitchen, bathrooms, floors, dusting",
        "base": 120,
        "per_bedroom": 30,
        "per_bathroom": 20,
        "estimated_hours_base": 1.5,
        "hours_per_bedroom": 0.4,
        "hours_per_bathroom": 0.3,
    },
    "deep_clean": {
        "label": "Deep Clean",
        "description": "Intensive: baseboards, inside appliances, windows, cabinets",
        "base": 200,
        "per_bedroom": 50,
        "per_bathroom": 35,
        "estimated_hours_base": 3.0,
        "hours_per_bedroom": 0.75,
        "hours_per_bathroom": 0.5,
    },
    "move_out": {
        "label": "Move-Out Clean",
        "description": "Deposit-ready: walls, closets, garage, full detail",
        "base": 250,
        "per_bedroom": 60,
        "per_bathroom": 40,
        "estimated_hours_base": 4.0,
        "hours_per_bedroom": 1.0,
        "hours_per_bathroom": 0.6,
    },
    "airbnb_turnover": {
        "label": "Airbnb Turnover",
        "description": "Guest-ready: linens, restock, stage, quick detail",
        "base": 100,
        "per_bedroom": 25,
        "per_bathroom": 18,
        "estimated_hours_base": 1.25,
        "hours_per_bedroom": 0.35,
        "hours_per_bathroom": 0.25,
    },
}

CONDITION_MULTIPLIERS = {
    "clean": {"label": "Clean (light touch-up)", "multiplier": 0.8},
    "average": {"label": "Average", "multiplier": 1.0},
    "dirty": {"label": "Dirty", "multiplier": 1.3},
    "very_dirty": {"label": "Very Dirty", "multiplier": 1.6},
}

# Sqft surcharge brackets (applied on top)
SQFT_BRACKETS = [
    (0, 1000, 0),
    (1001, 2000, 25),
    (2001, 3000, 60),
    (3001, 4000, 100),
    (4001, 999999, 160),
]

# Default labor cost per hour for profitability calculations
DEFAULT_LABOR_COST_PER_HOUR = 18.00
DEFAULT_SUPPLY_COST_PER_JOB = 8.00


def calculate_price(service_type, bedrooms, bathrooms, condition="average", sqft=None):
    """Calculate the price for a cleaning job.

    Returns dict with price, breakdown, estimated hours, and cost estimates.
    """
    svc = SERVICE_TYPES.get(service_type)
    if not svc:
        raise ValueError(f"Unknown service type: {service_type}")

    cond = CONDITION_MULTIPLIERS.get(condition)
    if not cond:
        raise ValueError(f"Unknown condition: {condition}")

    bedrooms = max(0, int(bedrooms))
    bathrooms = max(0, float(bathrooms))

    base = svc["base"]
    bedroom_cost = svc["per_bedroom"] * bedrooms
    bathroom_cost = svc["per_bathroom"] * bathrooms
    subtotal = base + bedroom_cost + bathroom_cost

    # Condition multiplier
    after_condition = round(subtotal * cond["multiplier"], 2)

    # Sqft surcharge
    sqft_surcharge = 0
    if sqft and sqft > 0:
        for low, high, charge in SQFT_BRACKETS:
            if low <= sqft <= high:
                sqft_surcharge = charge
                break

    total = round(after_condition + sqft_surcharge, 2)

    # Estimated hours
    est_hours = svc["estimated_hours_base"] + svc["hours_per_bedroom"] * bedrooms + svc["hours_per_bathroom"] * bathrooms
    est_hours = round(est_hours * cond["multiplier"], 1)

    # Cost estimates
    labor_cost = round(est_hours * DEFAULT_LABOR_COST_PER_HOUR, 2)
    supply_cost = DEFAULT_SUPPLY_COST_PER_JOB
    total_cost = round(labor_cost + supply_cost, 2)
    profit = round(total - total_cost, 2)
    margin = round((profit / total) * 100, 1) if total > 0 else 0

    return {
        "service_type": service_type,
        "service_label": svc["label"],
        "bedrooms": bedrooms,
        "bathrooms": bathrooms,
        "condition": condition,
        "condition_label": cond["label"],
        "sqft": sqft,
        "breakdown": {
            "base": base,
            "bedroom_cost": bedroom_cost,
            "bathroom_cost": bathroom_cost,
            "subtotal": subtotal,
            "condition_multiplier": cond["multiplier"],
            "after_condition": after_condition,
            "sqft_surcharge": sqft_surcharge,
        },
        "price": total,
        "estimated_hours": est_hours,
        "costs": {
            "labor": labor_cost,
            "supplies": supply_cost,
            "total_cost": total_cost,
            "profit": profit,
            "margin_pct": margin,
        },
    }


def get_all_service_types():
    """Return service types for display."""
    return {k: {"label": v["label"], "description": v["description"]} for k, v in SERVICE_TYPES.items()}
