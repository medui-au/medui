"""GovernanceRegisterService — merges Adverse Events + Complaints into one
sortable/filterable, read-only browse feed for the combined clinical
governance register page.

This is purely a display-layer aggregation over the two existing registers
(AdverseEventService / ComplaintsService remain the canonical place to
create/edit/action records). When a record is linked to a patient_id, patient
PII is redacted via the existing RedactionService before rendering — this
page is meant for broad perusal, so text is never shown unredacted here;
anyone who needs the full record clicks through to its real detail page.
"""

from dataclasses import dataclass
from datetime import datetime
from uuid import uuid4

from app.models.adverse_event import AdverseEvent, AEStatus, SeverityGrade
from app.models.complaint import Complaint, ComplaintStatus
from app.services.adverse_event_service import AdverseEventService
from app.services.complaints_service import ComplaintsService
from app.services.redaction_service import RedactionService
from app.utils.token_vault import TokenVault


_AE_CLOSED_STATUSES = {AEStatus.closed, AEStatus.no_action_required}
_COMPLAINT_CLOSED_STATUSES = {ComplaintStatus.closed, ComplaintStatus.withdrawn}

# Complaints have no severity/priority column (app/models/complaint.py), so a
# severity *filter* simply excludes them, and a severity *sort* ranks them
# after every real SAC grade — this keeps sort order stable regardless of
# direction rather than interleaving "no severity" rows arbitrarily.
_SEVERITY_RANK = {
    SeverityGrade.sac1_catastrophic: 1,
    SeverityGrade.sac2_major: 2,
    SeverityGrade.sac3_moderate: 3,
    SeverityGrade.sac4_minor: 4,
    SeverityGrade.sac5_near_miss: 5,
}
_NO_SEVERITY_RANK = 99


def _label(value) -> str:
    return value.value.replace('_', ' ').title() if value else ''


@dataclass
class GovernanceRegisterEntry:
    record_type: str  # 'adverse_event' | 'complaint'
    id: int
    reference_no: str
    date: datetime | None
    title: str
    status: str
    status_label: str
    is_open: bool
    severity: str | None
    severity_label: str | None
    severity_rank: int
    category_label: str
    patient_id: int | None
    patient_linked: bool
    reported_by: str | None


def _ae_entry(event: AdverseEvent) -> GovernanceRegisterEntry:
    return GovernanceRegisterEntry(
        record_type='adverse_event',
        id=event.id,
        reference_no=event.reference_no,
        date=event.occurred_at,
        title=event.title,
        status=event.status.value,
        status_label=_label(event.status),
        is_open=event.status not in _AE_CLOSED_STATUSES and event.closed_at is None,
        severity=event.severity.value if event.severity else None,
        severity_label=_label(event.severity),
        severity_rank=_SEVERITY_RANK.get(event.severity, _NO_SEVERITY_RANK),
        category_label=_label(event.event_type),
        patient_id=event.patient_id,
        patient_linked=bool(event.patient_id),
        reported_by=event.reported_by.display_name if event.reported_by else None,
    )


def _complaint_entry(complaint: Complaint) -> GovernanceRegisterEntry:
    return GovernanceRegisterEntry(
        record_type='complaint',
        id=complaint.id,
        reference_no=complaint.reference_no,
        date=complaint.received_at,
        title=complaint.subject,
        status=complaint.status.value,
        status_label=_label(complaint.status),
        is_open=complaint.status not in _COMPLAINT_CLOSED_STATUSES and complaint.closed_at is None,
        severity=None,
        severity_label=None,
        severity_rank=_NO_SEVERITY_RANK,
        category_label=_label(complaint.category),
        patient_id=complaint.patient_id,
        patient_linked=bool(complaint.patient_id),
        reported_by=complaint.received_by.display_name if complaint.received_by else None,
    )


def _redact_entry_titles(entries: list[GovernanceRegisterEntry]) -> None:
    """Redact patient-linked entry titles in place, sharing one vault so the
    same identifier maps to the same token across rows in this list."""
    vault = TokenVault(f'govreg-list-{uuid4()}')
    identifier_cache: dict[int, list[str]] = {}
    for entry in entries:
        if not (entry.patient_linked and entry.patient_id):
            continue
        if entry.patient_id not in identifier_cache:
            identifier_cache[entry.patient_id] = RedactionService.get_identifiers(entry.patient_id)
        identifiers = identifier_cache[entry.patient_id]
        if identifiers:
            entry.title = RedactionService.redact(entry.title, identifiers, vault)


class GovernanceRegisterService:

    @staticmethod
    def get_list(filters: dict | None = None) -> list[GovernanceRegisterEntry]:
        filters = filters or {}
        record_type = filters.get('record_type') or ''
        status_group = filters.get('status_group') or ''
        severity = filters.get('severity') or ''
        search = filters.get('search') or ''
        sort = filters.get('sort') or 'date'
        direction = filters.get('dir') or 'desc'

        entries: list[GovernanceRegisterEntry] = []

        if record_type != 'complaint':
            ae_filters: dict = {}
            if severity:
                ae_filters['severity'] = severity
            if search:
                ae_filters['search'] = search
            entries.extend(_ae_entry(e) for e in AdverseEventService.get_list(ae_filters))

        if record_type != 'adverse_event' and not severity:
            # A severity filter can never match a complaint — skip the query.
            complaint_filters: dict = {}
            if search:
                complaint_filters['search'] = search
            entries.extend(_complaint_entry(c) for c in ComplaintsService.get_list(complaint_filters))

        if status_group == 'open':
            entries = [e for e in entries if e.is_open]
        elif status_group == 'closed':
            entries = [e for e in entries if not e.is_open]

        if sort == 'severity':
            key = lambda e: e.severity_rank
        elif sort == 'status':
            key = lambda e: e.status_label
        else:
            key = lambda e: e.date or datetime.min
        entries.sort(key=key, reverse=(direction != 'asc'))

        _redact_entry_titles(entries)
        return entries

    @staticmethod
    def get_detail(record_type: str, record_id: int) -> dict | None:
        if record_type == 'adverse_event':
            record = AdverseEventService.get_detail(record_id)
            if not record:
                return None
            entry = _ae_entry(record)
            texts = {
                'title': record.title,
                'description': record.description,
                'immediate_actions': record.immediate_actions or '',
                'triage_notes': record.triage_notes or '',
                'rca_summary': record.rca_summary or '',
            }
            actions = record.actions.all()
        elif record_type == 'complaint':
            record = ComplaintsService.get_detail(record_id)
            if not record:
                return None
            entry = _complaint_entry(record)
            texts = {
                'title': record.subject,
                'description': record.description,
                'resolution_summary': record.resolution_summary or '',
                'corrective_action': record.corrective_action or '',
            }
            actions = record.actions.all()
        else:
            return None

        action_notes = [a.notes or '' for a in actions]

        if entry.patient_linked and entry.patient_id:
            identifiers = RedactionService.get_identifiers(entry.patient_id)
            if identifiers:
                vault = TokenVault(f'govreg-detail-{uuid4()}')
                texts = RedactionService.redact(texts, identifiers, vault)
                action_notes = RedactionService.redact(action_notes, identifiers, vault)

        entry.title = texts['title']

        actions_out = [
            {
                'action_type': _label(a.action_type),
                'timestamp': a.timestamp,
                'actor': a.actor.display_name if a.actor else None,
                'notes': notes,
            }
            for a, notes in zip(actions, action_notes)
        ]

        return {
            'entry': entry,
            'texts': texts,
            'actions': actions_out,
        }

    @staticmethod
    def describe_filters(filters: dict | None = None) -> str:
        filters = filters or {}
        parts = []

        record_type = filters.get('record_type')
        if record_type == 'adverse_event':
            parts.append('Adverse Events only')
        elif record_type == 'complaint':
            parts.append('Complaints only')
        else:
            parts.append('Adverse Events & Complaints')

        status_group = filters.get('status_group')
        if status_group == 'open':
            parts.append('open items only')
        elif status_group == 'closed':
            parts.append('closed items only')

        if filters.get('severity'):
            parts.append(f'severity {filters["severity"].replace("_", " ").title()}')

        if filters.get('search'):
            parts.append(f'matching "{filters["search"]}"')

        return ' · '.join(parts)

    @staticmethod
    def build_report(filters: dict | None = None) -> dict:
        """Assemble the printable report for the currently filtered register view.

        Re-runs get_detail() per matched item so each item's free text is
        redacted the same way as the live detail panel — this report always
        reflects exactly what a user could already see on the register page.
        """
        entries = GovernanceRegisterService.get_list(filters)
        items = []
        for entry in entries:
            detail = GovernanceRegisterService.get_detail(entry.record_type, entry.id)
            if detail:
                items.append(detail)

        total = len(items)
        open_count = sum(1 for i in items if i['entry'].is_open)
        ae_count = sum(1 for i in items if i['entry'].record_type == 'adverse_event')
        redacted_count = sum(1 for i in items if i['entry'].patient_linked)

        return {
            'items': items,
            'filter_description': GovernanceRegisterService.describe_filters(filters),
            'summary': {
                'total': total,
                'open': open_count,
                'closed': total - open_count,
                'adverse_events': ae_count,
                'complaints': total - ae_count,
                'redacted': redacted_count,
            },
        }
