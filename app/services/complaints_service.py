from datetime import datetime, timezone, date, timedelta

from flask import current_app
from app.extensions import db
from app.models.complaint import (
    Complaint, ComplaintAction, ComplaintDocument,
    ComplaintStatus, ComplaintActionType, EscalationTarget,
)


_BUSINESS_DAY_SLA = 2  # AGPAL: acknowledge within 2 business days


def _utcnow():
    return datetime.now(timezone.utc)


def _next_seq(year: int) -> int:
    row = db.session.execute(
        db.text('SELECT COALESCE(MAX(seq_num), 0) FROM complaints WHERE year = :y'),
        {'y': year},
    ).fetchone()
    return (row[0] or 0) + 1


def _make_reference(year: int, seq: int) -> str:
    return f'CMP-{year}-{seq:04d}'


def _business_days_between(start: datetime, end: datetime) -> int:
    """Count weekday days between two datetimes (exclusive of start, inclusive of end)."""
    d = start.date() if hasattr(start, 'date') else start
    e = end.date() if hasattr(end, 'date') else end
    count = 0
    current = d + timedelta(days=1)
    while current <= e:
        if current.weekday() < 5:  # Mon–Fri
            count += 1
        current += timedelta(days=1)
    return count


class ComplaintsService:

    @staticmethod
    def create(data: dict, actor) -> Complaint:
        now = _utcnow()
        year = now.year
        seq = _next_seq(year)
        ref = _make_reference(year, seq)

        complaint = Complaint(
            reference_no=ref,
            seq_num=seq,
            year=year,
            complainant_type=data['complainant_type'],
            patient_id=data.get('patient_id'),
            external_name=data.get('external_name'),
            external_contact=data.get('external_contact'),
            subject=data['subject'],
            description=data['description'],
            category=data['category'],
            received_at=data.get('received_at') or now,
            received_by_id=actor.id,
            open_disclosure_required=data.get('open_disclosure_required', False),
            status=ComplaintStatus.received,
        )
        db.session.add(complaint)
        db.session.flush()  # get complaint.id before writing action

        log = ComplaintAction(
            complaint_id=complaint.id,
            action_type=ComplaintActionType.created,
            new_status=ComplaintStatus.received,
            notes=data.get('notes'),
            actor_id=actor.id,
        )
        db.session.add(log)
        db.session.commit()
        return complaint

    @staticmethod
    def transition(complaint: Complaint, new_status: ComplaintStatus, notes: str | None, actor) -> None:
        old_status = complaint.status
        complaint.status = new_status
        complaint.updated_at = _utcnow()

        if new_status in (ComplaintStatus.closed, ComplaintStatus.withdrawn):
            complaint.closed_at = _utcnow()
            complaint.closed_by_id = actor.id

        action_type = (ComplaintActionType.withdrawn if new_status == ComplaintStatus.withdrawn
                       else ComplaintActionType.status_changed)
        log = ComplaintAction(
            complaint_id=complaint.id,
            action_type=action_type,
            old_status=old_status,
            new_status=new_status,
            notes=notes,
            actor_id=actor.id,
        )
        db.session.add(log)
        db.session.commit()

    @staticmethod
    def acknowledge(complaint: Complaint, method: str, actor, ack_date=None) -> None:
        complaint.acknowledged_at = ack_date or _utcnow()
        complaint.acknowledgement_method = method
        complaint.status = ComplaintStatus.acknowledged
        complaint.updated_at = _utcnow()

        log = ComplaintAction(
            complaint_id=complaint.id,
            action_type=ComplaintActionType.acknowledged,
            old_status=ComplaintStatus.received,
            new_status=ComplaintStatus.acknowledged,
            notes=f'Method: {method}',
            actor_id=actor.id,
        )
        db.session.add(log)
        db.session.commit()

    @staticmethod
    def add_note(complaint: Complaint, notes: str, actor) -> None:
        complaint.updated_at = _utcnow()
        log = ComplaintAction(
            complaint_id=complaint.id,
            action_type=ComplaintActionType.note_added,
            notes=notes,
            actor_id=actor.id,
        )
        db.session.add(log)
        db.session.commit()

    @staticmethod
    def assign(complaint: Complaint, assignee_id: int, notes: str | None, actor) -> None:
        complaint.assigned_to_id = assignee_id
        complaint.updated_at = _utcnow()
        log = ComplaintAction(
            complaint_id=complaint.id,
            action_type=ComplaintActionType.assigned,
            notes=notes,
            actor_id=actor.id,
        )
        db.session.add(log)
        db.session.commit()

    @staticmethod
    def mark_disclosure(complaint: Complaint, notes: str | None, actor) -> None:
        complaint.open_disclosure_completed_at = _utcnow()
        complaint.open_disclosure_by_id = actor.id
        complaint.open_disclosure_notes = notes
        complaint.updated_at = _utcnow()
        log = ComplaintAction(
            complaint_id=complaint.id,
            action_type=ComplaintActionType.disclosure_updated,
            notes=notes,
            actor_id=actor.id,
        )
        db.session.add(log)
        db.session.commit()

    @staticmethod
    def escalate(complaint: Complaint, target: EscalationTarget, ref: str | None,
                 notes: str | None, actor) -> None:
        complaint.escalated_to = target
        complaint.escalation_ref = ref
        complaint.escalation_notes = notes
        complaint.updated_at = _utcnow()
        log = ComplaintAction(
            complaint_id=complaint.id,
            action_type=ComplaintActionType.escalated,
            notes=f'{target.value}: {notes or ""}',
            actor_id=actor.id,
        )
        db.session.add(log)
        db.session.commit()

    @staticmethod
    def update_resolution(complaint: Complaint, resolution_summary: str,
                          corrective_action: str | None, actor) -> None:
        complaint.resolution_summary = resolution_summary
        complaint.corrective_action = corrective_action
        complaint.updated_at = _utcnow()
        db.session.commit()

    @staticmethod
    def link_document(complaint: Complaint, bpsdb_doc_id: int | None,
                      doc_type: str | None, gen5_doc_id: int | None,
                      description: str | None, actor) -> ComplaintDocument:
        doc = ComplaintDocument(
            complaint_id=complaint.id,
            bpsdb_document_id=bpsdb_doc_id,
            bpsdb_document_type=doc_type,
            gen5_document_id=gen5_doc_id,
            description=description,
            added_by_id=actor.id,
        )
        db.session.add(doc)
        log = ComplaintAction(
            complaint_id=complaint.id,
            action_type=ComplaintActionType.document_linked,
            notes=description,
            actor_id=actor.id,
        )
        db.session.add(log)
        db.session.commit()
        return doc

    @staticmethod
    def void(complaint: Complaint, reason: str, actor) -> None:
        complaint.voided_at = _utcnow()
        complaint.voided_by_id = actor.id
        complaint.void_reason = reason
        log = ComplaintAction(
            complaint_id=complaint.id,
            action_type=ComplaintActionType.note_added,
            notes=f'[VOIDED] {reason}',
            actor_id=actor.id,
        )
        db.session.add(log)
        db.session.commit()

    @staticmethod
    def get_list(filters: dict | None = None) -> list:
        q = Complaint.query.order_by(Complaint.received_at.desc())
        # Exclude voided records unless admin explicitly asks to see them
        if not (filters or {}).get('show_voided'):
            q = q.filter(Complaint.voided_at.is_(None))
        if filters:
            if filters.get('status'):
                q = q.filter(Complaint.status == filters['status'])
            if filters.get('category'):
                q = q.filter(Complaint.category == filters['category'])
            if filters.get('assigned_to_id'):
                q = q.filter(Complaint.assigned_to_id == filters['assigned_to_id'])
            if filters.get('date_from'):
                q = q.filter(Complaint.received_at >= filters['date_from'])
            if filters.get('date_to'):
                q = q.filter(Complaint.received_at <= filters['date_to'])
            if filters.get('search'):
                term = f'%{filters["search"]}%'
                note_match = db.exists().where(
                    db.and_(
                        ComplaintAction.complaint_id == Complaint.id,
                        ComplaintAction.notes.ilike(term),
                    )
                )
                q = q.filter(db.or_(
                    Complaint.reference_no.ilike(term),
                    Complaint.subject.ilike(term),
                    Complaint.resolution_summary.ilike(term),
                    Complaint.corrective_action.ilike(term),
                    Complaint.escalation_ref.ilike(term),
                    Complaint.escalation_notes.ilike(term),
                    Complaint.open_disclosure_notes.ilike(term),
                    Complaint.void_reason.ilike(term),
                    note_match,
                ))
        return q.all()

    @staticmethod
    def get_detail(complaint_id: int) -> Complaint | None:
        return Complaint.query.get(complaint_id)

    @staticmethod
    def days_to_acknowledge(complaint: Complaint) -> int | None:
        if not complaint.acknowledged_at:
            return None
        return _business_days_between(complaint.received_at, complaint.acknowledged_at)

    @staticmethod
    def overdue_acknowledgement(complaint: Complaint) -> bool:
        if complaint.acknowledged_at or complaint.status in (
                ComplaintStatus.closed, ComplaintStatus.withdrawn):
            return False
        return _business_days_between(complaint.received_at, _utcnow()) > _BUSINESS_DAY_SLA

    @staticmethod
    def can_close(complaint: Complaint) -> tuple[bool, str]:
        if complaint.open_disclosure_required and not complaint.open_disclosure_completed_at:
            return False, 'Open disclosure must be completed before closing.'
        if complaint.status == ComplaintStatus.resolved and not complaint.resolution_summary:
            return False, 'Resolution summary is required before closing.'
        return True, ''
