"""
Business registry — single source of truth for multi-tenant business metadata.
Add a new entry here + run the parameterized seed functions to onboard a new business.
"""

BUSINESSES: dict[str, dict] = {
    "demo-business-001": {
        "name": "Mid-Atlantic Auto Parts Distribution LLC",
        "industry": "Automotive Parts Distribution",
        "contact_email": "ops@midatlanticauto.com",
        "contact_name": "Regional Operations Director",
        "description": "Mid-Atlantic distributor of OEM and aftermarket auto parts serving dealerships and repair shops across MD, VA, PA, DE, and NJ.",
        "primary_port": "Port of Baltimore",
        "product_categories": ["auto_parts", "fasteners"],
    },
    "demo-business-002": {
        "name": "Pacific Rim Electronics Supply Co.",
        "industry": "Consumer Electronics Distribution",
        "contact_email": "ops@pacrimelectronics.com",
        "contact_name": "Supply Chain Director",
        "description": "West Coast distributor of consumer electronics components sourced primarily from Taiwan, South Korea, and Japan.",
        "primary_port": "Port of Los Angeles",
        "product_categories": ["semiconductors", "circuit_boards", "displays"],
    },
}


def get_business(business_id: str) -> dict:
    """Return business metadata. Raises KeyError if not found."""
    if business_id not in BUSINESSES:
        raise KeyError(f"Unknown business_id: {business_id!r}. Valid: {list(BUSINESSES)}")
    return BUSINESSES[business_id]


def list_businesses() -> list[dict]:
    """Return all businesses as a list of dicts with id included."""
    return [{"id": k, **v} for k, v in BUSINESSES.items()]
