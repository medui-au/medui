"""Curated brand→generic drug name mapping service.

Mappings are keyed by CURRENTRX.PRODUCTID (stable MIMS integer) and approved
one-at-a-time by admins via the medication card popup. Suggestions come from
the PBS public API (see pbs_api_service.py). Once approved, the mapping is
permanent and the PBS API is never consulted for that product again.
"""
from datetime import datetime, timezone

from app.extensions import db
from app.models.drug_mapping import DrugMapping


def get_mapping(product_id: int) -> DrugMapping | None:
    """Return the approved mapping for a PRODUCTID, or None."""
    return DrugMapping.query.filter_by(product_id=product_id, approved=True).first()


def approve(product_id: int, brand_name: str, generic_name: str,
            atc_code: str, user_id: int) -> DrugMapping:
    """Create or update an approved mapping for the given product_id."""
    m = DrugMapping.query.filter_by(product_id=product_id).first()
    if m is None:
        m = DrugMapping(product_id=product_id)
    m.brand_name     = brand_name.strip()
    m.generic_name   = generic_name.strip()
    m.atc_code       = atc_code.strip() or None
    m.approved       = True
    m.approved_by_id = user_id
    m.approved_at    = datetime.now(timezone.utc)
    db.session.add(m)
    db.session.commit()
    return m


def batch_status(product_ids: list[int]) -> dict[int, bool]:
    """Return {product_id: is_mapped} for a list of PRODUCTID integers."""
    if not product_ids:
        return {}
    id_set = set(product_ids)
    mapped = {
        m.product_id for m in DrugMapping.query.filter(
            DrugMapping.product_id.in_(id_set),
            DrugMapping.approved == True,  # noqa: E712
        ).all()
    }
    return {pid: pid in mapped for pid in id_set}
