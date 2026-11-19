from datetime import datetime, timezone, timedelta

from app.extensions import db
from app.models.adverse_event import (
    AdverseEvent, AdverseEventAction, AdverseEventActionItem, AdverseEventDocument,
    RegisterCrossLink, AEStatus, AEActionType, ActionItemStatus,
    SeverityGrade, EventType, InvolvedPersonType, NotifiedAuthority, CrossLinkType,
)


def _utcnow():
    return datetime.now(timezone.utc)


def _next_seq(year: int) -> int:
    row = db.session.execute(
        db.text('SELECT COALESCE(MAX(seq_num), 0) FROM adverse_events WHERE year = :y'),
        {'y': year},
    ).fetchone()
    return (row[0] or 0) + 1


def _make_reference(year: int, seq: int) -> str:
    return f'AE-{year}-{seq:04d}'


# SAC triage SLAs in hours
_TRIAGE_SLA_HOURS = {
    SeverityGrade.sac1_catastrophic: 24,
    SeverityGrade.sac2_major: 24,
    SeverityGrade.sac3_moderate: 48,
    SeverityGrade.sac4_minor: 120,   # 5 business days ≈ 5×24h
    SeverityGrade.sac5_near_miss: 120,
}

_RCA_REQUIRED_GRADES = {SeverityGrade.sac1_catastrophic, SeverityGrade.sac2_major}
_DISCLOSURE_REQUIRED_GRADES = {
    SeverityGrade.sac1_catastrophic, SeverityGrade.sac2_major, SeverityGrade.sac3_moderate
}


class AdverseEventService:

    @staticmethod
    def create(data: dict, actor) -> AdverseEvent:
        now = _utcnow()
        year = now.year
        seq = _next_seq(year)
        ref = _make_reference(year, seq)

        severity = data['severity']
        involved_type = data['involved_person_type']

        rca_required = severity in _RCA_REQUIRED_GRADES
        open_disclosure_required = data.get('open_disclosure_required')
        if open_disclosure_required is None:
            open_disclosure_required = (
                severity in _DISCLOSURE_REQUIRED_GRADES
                and involved_type == InvolvedPersonType.patient
            )

        event = AdverseEvent(
            reference_no=ref,
            seq_num=seq,
            year=year,
            event_type=data['event_type'],
            severity=severity,
            involved_person_type=involved_type,
            patient_id=data.get('patient_id'),
            external_name=data.get('external_name'),
            external_contact=data.get('external_contact'),
            title=data['title'],
            description=data['description'],
            immediate_actions=data.get('immediate_actions'),
            location=data.get('location'),
            occurred_at=data['occurred_at'],
            reported_by_id=actor.id,
            rca_required=rca_required,
            open_disclosure_required=open_disclosure_required,
            status=AEStatus.reported,
        )
        db.session.add(event)
        db.session.flush()

        log = AdverseEventAction(
            adverse_event_id=event.id,
            action_type=AEActionType.created,
            new_status=AEStatus.reported,
            notes=data.get('notes'),
            actor_id=actor.id,
        )
        db.session.add(log)
        db.session.commit()
        return event

    @staticmethod
    def transition(event: AdverseEvent, new_status: AEStatus, notes: str | None, actor) -> None:
        old_status = event.status
        event.status = new_status
        event.updated_at = _utcnow()

        if new_status == AEStatus.closed:
            event.closed_at = _utcnow()
            event.closed_by_id = actor.id

        log = AdverseEventAction(
            adverse_event_id=event.id,
            action_type=AEActionType.status_changed,
            old_status=old_status,
            new_status=new_status,
            notes=notes,
            actor_id=actor.id,
        )
        db.session.add(log)
        db.session.commit()

    @staticmethod
    def triage(event: AdverseEvent, confirmed_severity: SeverityGrade | None,
               notes: str | None, actor) -> None:
        event.triaged_at = _utcnow()
        event.triaged_by_id = actor.id
        event.triage_notes = notes
        if confirmed_severity:
            event.triage_severity_confirmed = True
            if confirmed_severity != event.severity:
                event.severity = confirmed_severity
                event.rca_required = confirmed_severity in _RCA_REQUIRED_GRADES
                event.open_disclosure_required = (
                    confirmed_severity in _DISCLOSURE_REQUIRED_GRADES
                    and event.involved_person_type == InvolvedPersonType.patient
                )
        old_status = event.status
        event.status = AEStatus.triaged
        event.updated_at = _utcnow()

        log = AdverseEventAction(
            adverse_event_id=event.id,
            action_type=AEActionType.triaged,
            old_status=old_status,
            new_status=AEStatus.triaged,
            notes=notes,
            actor_id=actor.id,
        )
        db.session.add(log)
        db.session.commit()

    @staticmethod
    def update_rca(event: AdverseEvent, method: str | None, summary: str,
                   completed: bool, actor) -> None:
        event.rca_method = method
        event.rca_summary = summary
        event.updated_at = _utcnow()
        if completed:
            event.rca_completed_at = _utcnow()
            event.rca_completed_by_id = actor.id

        log = AdverseEventAction(
            adverse_event_id=event.id,
            action_type=AEActionType.rca_updated,
            notes=f'Method: {method or "—"}. Completed: {completed}',
            actor_id=actor.id,
        )
        db.session.add(log)
        db.session.commit()

    @staticmethod
    def set_disclosure_required(event: AdverseEvent, required: bool, actor) -> None:
        event.open_disclosure_required = required
        event.updated_at = _utcnow()

        log = AdverseEventAction(
            adverse_event_id=event.id,
            action_type=AEActionType.disclosure_updated,
            notes=f'Open disclosure requirement set to {"Yes" if required else "No"}',
            actor_id=actor.id,
        )
        db.session.add(log)
        db.session.commit()

    @staticmethod
    def mark_disclosure(event: AdverseEvent, notes: str | None, actor) -> None:
        event.open_disclosure_completed_at = _utcnow()
        event.open_disclosure_by_id = actor.id
        event.open_disclosure_notes = notes
        event.updated_at = _utcnow()

        log = AdverseEventAction(
            adverse_event_id=event.id,
            action_type=AEActionType.disclosure_updated,
            notes=notes,
            actor_id=actor.id,
        )
        db.session.add(log)
        db.session.commit()

    @staticmethod
    def notify_authority(event: AdverseEvent, authority: NotifiedAuthority,
                         ref: str | None, notes: str | None, actor) -> None:
        event.notified_authority = authority
        event.notified_authority_ref = ref
        event.notified_authority_notes = notes
        event.notified_at = _utcnow()
        event.updated_at = _utcnow()

        log = AdverseEventAction(
            adverse_event_id=event.id,
            action_type=AEActionType.authority_notified,
            notes=f'{authority.value}: {ref or ""} — {notes or ""}',
            actor_id=actor.id,
        )
        db.session.add(log)
        db.session.commit()

    @staticmethod
    def add_note(event: AdverseEvent, notes: str, actor) -> None:
        event.updated_at = _utcnow()
        log = AdverseEventAction(
            adverse_event_id=event.id,
            action_type=AEActionType.note_added,
            notes=notes,
            actor_id=actor.id,
        )
        db.session.add(log)
        db.session.commit()

    @staticmethod
    def add_action_item(event: AdverseEvent, description: str, assignee_id: int | None,
                        due_date, actor) -> AdverseEventActionItem:
        item = AdverseEventActionItem(
            adverse_event_id=event.id,
            description=description,
            assigned_to_id=assignee_id,
            due_date=due_date,
            created_by_id=actor.id,
        )
        db.session.add(item)
        db.session.flush()

        log = AdverseEventAction(
            adverse_event_id=event.id,
            action_type=AEActionType.action_item_added,
            notes=description[:200],
            actor_id=actor.id,
        )
        db.session.add(log)
        db.session.commit()
        return item

    @staticmethod
    def complete_action_item(item: AdverseEventActionItem, notes: str | None, actor) -> None:
        item.status = ActionItemStatus.completed
        item.completed_at = _utcnow()
        item.completed_by_id = actor.id
        item.completion_notes = notes
        item.updated_at = _utcnow()

        log = AdverseEventAction(
            adverse_event_id=item.adverse_event_id,
            action_type=AEActionType.action_item_completed,
            notes=f'Action item #{item.id}: {notes or ""}',
            actor_id=actor.id,
        )
        db.session.add(log)
        db.session.commit()

    @staticmethod
    def link_document(event: AdverseEvent, bpsdb_doc_id: int | None,
                      doc_type: str | None, gen5_doc_id: int | None,
                      description: str | None, actor) -> AdverseEventDocument:
        doc = AdverseEventDocument(
            adverse_event_id=event.id,
            bpsdb_document_id=bpsdb_doc_id,
            bpsdb_document_type=doc_type,
            gen5_document_id=gen5_doc_id,
            description=description,
            added_by_id=actor.id,
        )
        db.session.add(doc)
        log = AdverseEventAction(
            adverse_event_id=event.id,
            action_type=AEActionType.document_linked,
            notes=description,
            actor_id=actor.id,
        )
        db.session.add(log)
        db.session.commit()
        return doc

    @staticmethod
    def add_cross_link(complaint_id: int | None, adverse_event_id: int | None,
                       link_type: CrossLinkType, notes: str | None, actor) -> RegisterCrossLink:
        link = RegisterCrossLink(
            complaint_id=complaint_id,
            adverse_event_id=adverse_event_id,
            link_type=link_type,
            notes=notes,
            created_by_id=actor.id,
        )
        db.session.add(link)
        db.session.commit()
        return link

    @staticmethod
    def void(event: AdverseEvent, reason: str, actor) -> None:
        event.voided_at = _utcnow()
        event.voided_by_id = actor.id
        event.void_reason = reason
        log = AdverseEventAction(
            adverse_event_id=event.id,
            action_type=AEActionType.note_added,
            notes=f'[VOIDED] {reason}',
            actor_id=actor.id,
        )
        db.session.add(log)
        db.session.commit()

    @staticmethod
    def get_list(filters: dict | None = None) -> list:
        q = AdverseEvent.query.order_by(AdverseEvent.occurred_at.desc())
        if not (filters or {}).get('show_voided'):
            q = q.filter(AdverseEvent.voided_at.is_(None))
        if filters:
            if filters.get('status'):
                q = q.filter(AdverseEvent.status == filters['status'])
            if filters.get('event_type'):
                q = q.filter(AdverseEvent.event_type == filters['event_type'])
            if filters.get('severity'):
                q = q.filter(AdverseEvent.severity == filters['severity'])
            if filters.get('assigned_to_id'):
                q = q.filter(AdverseEvent.assigned_to_id == filters['assigned_to_id'])
            if filters.get('date_from'):
                q = q.filter(AdverseEvent.occurred_at >= filters['date_from'])
            if filters.get('date_to'):
                q = q.filter(AdverseEvent.occurred_at <= filters['date_to'])
            if filters.get('search'):
                term = f'%{filters["search"]}%'
                note_match = db.exists().where(
                    db.and_(
                        AdverseEventAction.adverse_event_id == AdverseEvent.id,
                        AdverseEventAction.notes.ilike(term),
                    )
                )
                q = q.filter(db.or_(
                    AdverseEvent.reference_no.ilike(term),
                    AdverseEvent.title.ilike(term),
                    AdverseEvent.location.ilike(term),
                    AdverseEvent.immediate_actions.ilike(term),
                    AdverseEvent.triage_notes.ilike(term),
                    AdverseEvent.rca_method.ilike(term),
                    AdverseEvent.rca_summary.ilike(term),
                    AdverseEvent.notified_authority_ref.ilike(term),
                    AdverseEvent.notified_authority_notes.ilike(term),
                    AdverseEvent.open_disclosure_notes.ilike(term),
                    AdverseEvent.void_reason.ilike(term),
                    note_match,
                ))
        return q.all()

    @staticmethod
    def get_detail(event_id: int) -> AdverseEvent | None:
        return AdverseEvent.query.get(event_id)

    @staticmethod
    def overdue_triage(event: AdverseEvent) -> bool:
        if event.triaged_at or event.status not in (AEStatus.reported,):
            return False
        sla_hours = _TRIAGE_SLA_HOURS.get(event.severity, 120)
        return (_utcnow() - event.reported_at.replace(tzinfo=timezone.utc)).total_seconds() > sla_hours * 3600

    @staticmethod
    def all_actions_complete(event: AdverseEvent) -> bool:
        items = event.action_items.all()
        if not items:
            return False
        return all(i.status == ActionItemStatus.completed for i in items)

    @staticmethod
    def can_close(event: AdverseEvent) -> tuple[bool, str]:
        if event.open_disclosure_required and not event.open_disclosure_completed_at:
            return False, 'Open disclosure must be completed before closing.'
        if event.rca_required and not event.rca_completed_at:
            return False, 'Root Cause Analysis must be completed before closing.'
        if event.status == AEStatus.monitoring and not AdverseEventService.all_actions_complete(event):
            return False, 'All corrective action items must be completed before closing.'
        return True, ''
