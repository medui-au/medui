"""GPCCMP reviews (ADR-175, phase 5): progress against the previous plan's goals.

MBS AN.0.47 asks a review (967) to "discuss and document progress against goals". The judgement is
the GP's: they choose a progress word for each issue. MedUI shows the previous goal and, for each
target, the target beside the last recorded value in one fixed sentence (decision 9); it never says
whether a target is met. Nothing here is written by the AI.
"""
import re

from app.services import patient_target_service as targets

PROGRESS_WORDS = ('improved', 'stable', 'worse', 'achieved', 'not assessed')


def target_sentences(patient_id: int, latest: dict) -> list[str]:
    """Decision 9: "Your target {measure} is {target}; your last recorded value was {value} on {date}."
    One sentence per current target. Without a usable latest value the sentence says so; there is
    never a comparison."""
    out = []
    for t in sorted(targets.current_targets(patient_id).values(), key=lambda t: (t.measure.display_order, t.measure.id)):
        v = latest.get(t.measure.token_key) if t.measure.token_key else None
        if v and v.get('value'):
            unit = f" {v['unit']}" if v.get('unit') and v['unit'] not in str(v['value']) else ''
            when = f" on {_date(v.get('date'))}" if v.get('date') else ''
            out.append(f"Your target {t.measure.label} is {t.value_text}; your last recorded value was {v['value']}{unit}{when}.")
        else:
            out.append(f'Your target {t.measure.label} is {t.value_text}; no recent value is recorded.')
    return out


def _date(value) -> str:
    m = re.match(r'(\d{4})-(\d{2})-(\d{2})', str(value or ''))
    return f'{m.group(3)}/{m.group(2)}/{m.group(1)}' if m else str(value or '')


def previous_goals(patient_id: int) -> dict[str, str]:
    """{issue label (lower case): the goal line} from the patient's last filed care plan."""
    from app.services import careplan_service
    plan = careplan_service.last_filed(patient_id)
    out = {}
    for r in (plan.rows if plan else []):
        lines = [ln.strip() for ln in (r.goals_text or '').split('\n') if ln.strip()]
        goal = next((ln for ln in lines if ln.lower().startswith('my goal')), lines[0] if lines else '')
        if r.issue_label and goal:
            out[r.issue_label.strip().lower()] = _untagged(goal)
    return out


def _untagged(text: str) -> str:
    return re.sub(r'\s*\[(?:Discussed|Record|Protocol)\]', '', text).strip()


def goal_for(issue: dict, filed: dict[str, str], module_goal: str = '') -> str:
    """The previous goal for an issue: the last filed plan's, else the goal carried in the decisions,
    else the protocol module's."""
    return filed.get((issue.get('label') or '').strip().lower()) or issue.get('goal') or module_goal or ''


def progress_lines(d: dict) -> list[str]:
    """The GP's progress, one line per issue, for the plan's progress row."""
    out = []
    for i in d.get('issues', []):
        word = i.get('progress') or 'not recorded (GP to complete)'
        line = f"{i['label']}: {word}"
        if i.get('progress_note'):
            line += f". {i['progress_note']}"
        out.append(line)
    return out
