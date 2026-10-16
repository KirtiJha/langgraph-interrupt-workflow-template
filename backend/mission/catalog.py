"""Static "outside world" data the tools search over, and the starter missions."""

from __future__ import annotations

RESTAURANTS = [
    {"id": "r1", "name": "Olive & Fig", "cuisine": "Mediterranean", "neighborhood": "Hayes Valley",
     "price_per_person": 45, "rating": 4.7, "vegetarian_friendly": True, "noise": "quiet",
     "max_party": 16, "deposit": 120, "refundable": True, "highlight": "Private garden room, big vegetarian menu"},
    {"id": "r2", "name": "Brasa Grill House", "cuisine": "Steakhouse", "neighborhood": "SoMa",
     "price_per_person": 70, "rating": 4.6, "vegetarian_friendly": False, "noise": "lively",
     "max_party": 20, "deposit": 300, "refundable": False, "highlight": "Famous dry-aged steaks"},
    {"id": "r3", "name": "Lotus Garden", "cuisine": "Pan-Asian", "neighborhood": "Inner Sunset",
     "price_per_person": 38, "rating": 4.5, "vegetarian_friendly": True, "noise": "moderate",
     "max_party": 14, "deposit": 80, "refundable": True, "highlight": "Lazy-susan family tables"},
    {"id": "r4", "name": "Trattoria Nonna", "cuisine": "Italian", "neighborhood": "North Beach",
     "price_per_person": 52, "rating": 4.8, "vegetarian_friendly": True, "noise": "moderate",
     "max_party": 12, "deposit": 150, "refundable": True, "highlight": "Handmade pasta, candlelit back room"},
]

BAKERIES = [
    {"id": "b1", "name": "Sugar & Spoon", "item": "Vanilla-berry celebration cake (serves 14)", "price": 85},
    {"id": "b2", "name": "Golden Crumb", "item": "Tres leches cake (serves 16)", "price": 64},
]

FLIGHTS = [
    {"id": "f1", "airline": "TAP Air Portugal", "route": "SFO → LIS", "stops": 1, "duration": "14h 20m", "price": 612, "refundable": False, "depart_time": "16:05"},
    {"id": "f2", "airline": "United + Lufthansa", "route": "SFO → LIS", "stops": 1, "duration": "15h 45m", "price": 548, "refundable": True, "depart_time": "13:40"},
    {"id": "f3", "airline": "Azores Airlines", "route": "SFO → LIS", "stops": 1, "duration": "17h 05m", "price": 471, "refundable": False, "depart_time": "21:30"},
]

HOTELS = [
    {"id": "h1", "name": "Casa do Bairro", "area": "Alfama", "price_per_night": 165, "rating": 4.8, "refundable": True, "highlight": "Rooftop with river views"},
    {"id": "h2", "name": "Lisbon Loft Suites", "area": "Chiado", "price_per_night": 210, "rating": 4.6, "refundable": True, "highlight": "Walk to everything"},
    {"id": "h3", "name": "Hostel Azulejo", "area": "Baixa", "price_per_night": 58, "rating": 4.3, "refundable": False, "highlight": "Budget-friendly, social"},
]

SERVICES = {
    "movers": [
        {"id": "m1", "vendor": "SwiftMove SF", "price": 980, "deposit": 250, "rating": 4.7, "crew": 3, "refundable": True, "note": "Includes packing materials"},
        {"id": "m2", "vendor": "Golden Gate Movers", "price": 1240, "deposit": 300, "rating": 4.9, "crew": 4, "refundable": True, "note": "Fastest — done in half a day"},
        {"id": "m3", "vendor": "BudgetHaul", "price": 690, "deposit": 690, "rating": 3.9, "crew": 2, "refundable": False, "note": "Full prepayment, no insurance"},
    ],
    "cleaners": [
        {"id": "cl1", "vendor": "SparkleSquad", "price": 260, "deposit": 60, "rating": 4.8, "refundable": True, "note": "Move-out deep clean, deposit-back guarantee"},
        {"id": "cl2", "vendor": "QuickClean", "price": 180, "deposit": 180, "rating": 4.1, "refundable": False, "note": "Prepaid"},
    ],
}

# Starter missions shown in the gallery. ``goal`` is what gets sent; the mock
# model recognises these ids and plays a scripted, realistic run offline.
MISSIONS = [
    {
        "id": "birthday",
        "emoji": "🎂",
        "title": "Plan Mom's 60th birthday dinner",
        "goal": "Plan Mom's 60th birthday dinner for the family next month — 12 people, under $600, somewhere she'd love.",
        "blurb": "Finds a venue, books it, orders a cake and invites the family.",
        "tags": ["Booking", "Payments", "Group email"],
        "approvals": 3,
        "accent": "rose",
    },
    {
        "id": "move",
        "emoji": "📦",
        "title": "Handle my apartment move",
        "goal": "I'm moving out on the 1st. Book movers and a move-out clean, tell my landlord, and cancel the gym.",
        "blurb": "Compares quotes, books movers, emails your landlord, cancels the gym.",
        "tags": ["Quotes", "Deposits", "Cancellations"],
        "approvals": 4,
        "accent": "amber",
    },
    {
        "id": "lisbon",
        "emoji": "✈️",
        "title": "Book a long weekend in Lisbon",
        "goal": "Find a free long weekend next month and book me flights and a nice hotel in Lisbon. Keep it under $1,200.",
        "blurb": "Checks your calendar, compares flights and hotels, books the trip.",
        "tags": ["Calendar", "Flights", "Hotels"],
        "approvals": 2,
        "accent": "sky",
    },
    {
        "id": "inbox",
        "emoji": "📬",
        "title": "Get me to inbox zero",
        "goal": "Go through my inbox: reply to what's urgent, schedule what needs a meeting, and clear out the junk.",
        "blurb": "Triages email, drafts replies for you to edit, books a lunch.",
        "tags": ["Email drafts", "Scheduling"],
        "approvals": 3,
        "accent": "violet",
    },
    {
        "id": "subscriptions",
        "emoji": "💳",
        "title": "Cut subscriptions I don't use",
        "goal": "Review my subscriptions, cancel the ones I'm not using, and tell me how much I'll save.",
        "blurb": "Audits spending and cancels unused plans — each one needs your OK.",
        "tags": ["Spending", "Irreversible"],
        "approvals": 3,
        "accent": "emerald",
    },
]

MISSIONS_BY_ID = {m["id"]: m for m in MISSIONS}


def mission_for_goal(goal: str) -> str | None:
    """Recognise a starter mission from its goal text (for the offline pilot)."""
    text = (goal or "").strip().lower()
    for m in MISSIONS:
        if text == m["goal"].lower():
            return m["id"]
    return None
