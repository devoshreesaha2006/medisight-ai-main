from datetime import datetime, timezone

from fastapi import HTTPException, Request
from sqlalchemy.orm import Session

from app.models.consent import Consent, ConsentStatus
from app.models.emergency_access import EmergencyAccess
from app.models.user import User, UserRole
from app.services.audit import log_event


SCOPE_ALIASES = {
    "record": {"record", "patient_record", "all_records", "full_record"},
    "visits": {"visits", "all_records", "full_record"},
    "conditions": {"conditions", "all_records", "full_record"},
    "labs": {"labs", "all_records", "full_record"},
    "prescriptions": {"prescriptions", "all_records", "full_record"},
    "qr_access": {"qr_access", "all_records", "full_record"},
}


def _utc(value):
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def enforce_patient_access(
    db: Session, request: Request, user: User, patient_id: int, scope: str
) -> None:
    """Check active, patient-specific, clinician-specific consent on every request.
    A currently active, scoped emergency grant can substitute for ordinary consent.
    """
    now = datetime.now(timezone.utc)
    if user.role != UserRole.CLINICIAN:
        log_event(db, action="PATIENT_ACCESS_DENIED", actor_user_id=user.id,
                  actor_role=user.role.value, resource=f"patient:{patient_id}",
                  success=False, detail="Only clinicians may access identifiable records",
                  ip_address=request.client.host if request.client else "")
        raise HTTPException(status_code=403, detail="Patient record access is restricted")

    allowed_scopes = SCOPE_ALIASES.get(scope, {scope, "all_records", "full_record"})
    consents = db.query(Consent).filter(
        Consent.patient_id == patient_id,
        Consent.authorized_user_id == user.id,
        Consent.status == ConsentStatus.ACTIVE,
    ).all()
    for consent in consents:
        if consent.expires_at is not None and _utc(consent.expires_at) <= now:
            consent.status = ConsentStatus.EXPIRED
            log_event(db, action="CONSENT_EXPIRED", actor_user_id=user.id,
                      actor_role=user.role.value, resource=f"consent:{consent.id}",
                      success=False, detail="Consent expired during access check")
            continue
        if consent.access_scope.strip().lower() in allowed_scopes:
            log_event(db, action="PATIENT_RECORD_READ", actor_user_id=user.id,
                      actor_role=user.role.value, resource=f"patient:{patient_id}",
                      success=True, detail=f"scope={scope}",
                      ip_address=request.client.host if request.client else "")
            db.commit()
            return

    emergency = db.query(EmergencyAccess).filter(
        EmergencyAccess.patient_id == patient_id,
        EmergencyAccess.clinician_user_id == user.id,
        EmergencyAccess.revoked_at.is_(None),
        EmergencyAccess.expires_at > now.replace(tzinfo=None),
    ).order_by(EmergencyAccess.created_at.desc()).first()
    if emergency and scope in emergency.access_scope.split(","):
        log_event(db, action="EMERGENCY_ACCESS_READ", actor_user_id=user.id,
                  actor_role=user.role.value, resource=f"patient:{patient_id}",
                  success=True, detail=f"emergency_access_id={emergency.id}; scope={scope}",
                  ip_address=request.client.host if request.client else "")
        db.commit()
        return

    log_event(db, action="PATIENT_ACCESS_DENIED", actor_user_id=user.id,
              actor_role=user.role.value, resource=f"patient:{patient_id}",
              success=False, detail=f"Missing active consent for scope={scope}",
              ip_address=request.client.host if request.client else "")
    db.commit()
    raise HTTPException(status_code=403, detail="Active patient consent for this scope is required")
