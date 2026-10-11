from collections import defaultdict
from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_role
from app.models.user import User, UserRole
from app.models.patient import Condition, Patient
from app.schemas.misc import DiseaseDistributionItem, DiseaseTrendPoint, RegionalDistributionItem
from app.services.privacy import apply_k_anonymity
from app.services.audit import log_event

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


@router.get("/disease-distribution", response_model=list[DiseaseDistributionItem])
def disease_distribution(
    current_user: User = Depends(require_role(UserRole.ADMIN)),
    db: Session = Depends(get_db),
):
    """
    Admin-only, and even for admins this returns ONLY aggregated counts —
    never patient-level rows. Any bucket below the k-anonymity threshold
    is suppressed server-side before it's serialized.
    """
    rows = (
        db.query(Condition.name, func.count(func.distinct(Condition.patient_id)))
        .filter(Condition.active.is_(True))
        .group_by(Condition.name)
        .all()
    )

    results = []
    for name, count in rows:
        filtered = apply_k_anonymity(count)
        results.append(DiseaseDistributionItem(condition=name, **filtered))

    log_event(
        db, action="ADMIN_ANALYTICS_REQUEST", actor_user_id=current_user.id,
        actor_role=current_user.role.value, resource="disease-distribution", success=True,
    )
    return results


@router.get("/disease-trends", response_model=list[DiseaseTrendPoint])
def disease_trends(
    current_user: User = Depends(require_role(UserRole.ADMIN)),
    db: Session = Depends(get_db),
):
    """
    Aggregate, k-anonymized month-over-month counts, derived from diagnosis
    dates. Two kinds of rows come back, both suppressed the same way as
    distribution data:

      - condition="All conditions": total distinct patients newly diagnosed
        with anything that month. Pooling across conditions makes this the
        most robust line in the chart — individual conditions are common
        enough to dip below k=5 in a given month, but the total rarely does.
      - condition=<name>: the same breakdown per condition, for the months
        where that condition alone has enough patients to report safely.
    """
    rows = (
        db.query(Condition.name, Condition.diagnosed_date, Condition.patient_id)
        .filter(Condition.active.is_(True))
        .all()
    )

    per_condition: dict[tuple[str, str], set[int]] = defaultdict(set)
    total: dict[str, set[int]] = defaultdict(set)
    for name, diagnosed_date, patient_id in rows:
        period = diagnosed_date.strftime("%Y-%m") if isinstance(diagnosed_date, date) else str(diagnosed_date)[:7]
        per_condition[(name, period)].add(patient_id)
        total[period].add(patient_id)

    results = []
    for period, patient_ids in sorted(total.items()):
        filtered = apply_k_anonymity(len(patient_ids))
        results.append(DiseaseTrendPoint(period=period, condition="All conditions", **filtered))
    for (name, period), patient_ids in sorted(per_condition.items(), key=lambda kv: (kv[0][1], kv[0][0])):
        filtered = apply_k_anonymity(len(patient_ids))
        results.append(DiseaseTrendPoint(period=period, condition=name, **filtered))

    log_event(
        db, action="ADMIN_ANALYTICS_REQUEST", actor_user_id=current_user.id,
        actor_role=current_user.role.value, resource="disease-trends", success=True,
    )
    return results


@router.get("/regional-distribution", response_model=list[RegionalDistributionItem])
def regional_distribution(
    current_user: User = Depends(require_role(UserRole.ADMIN)),
    db: Session = Depends(get_db),
):
    """
    Admin-only. Active-case counts by region — the "location" axis the brief
    asks for, alongside condition (disease-distribution) and time
    (disease-trends). Same k-anonymity suppression as the other two: a
    region with fewer than k affected patients is hidden rather than shown
    with a small, potentially re-identifying number.
    """
    rows = (
        db.query(Patient.region, func.count(func.distinct(Condition.patient_id)))
        .join(Condition, Condition.patient_id == Patient.id)
        .filter(Condition.active.is_(True))
        .group_by(Patient.region)
        .all()
    )

    results = []
    for region, count in rows:
        filtered = apply_k_anonymity(count)
        results.append(RegionalDistributionItem(region=region, **filtered))

    log_event(
        db, action="ADMIN_ANALYTICS_REQUEST", actor_user_id=current_user.id,
        actor_role=current_user.role.value, resource="regional-distribution", success=True,
    )
    return sorted(results, key=lambda r: r.region)
