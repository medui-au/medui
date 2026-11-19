"""Care plan builder (ADR-129). Design: plans/careplan_data_model.md.

Recipes are the doctor's (or the practice's) issue templates, with targets that each cite a
guideline. A care plan is a draft (one encrypted JSON document, autosaved) until it is filed; filing
writes rows and frozen values that never change afterwards. No column holds a software judgement
about a patient: no "target met", severity, priority or rank.
"""
import enum
from datetime import datetime, timezone

from app.extensions import db
from app.utils.encrypted_type import EncryptedText


def _now():
    return datetime.now(timezone.utc)


class RecipeScope(str, enum.Enum):
    practice = 'practice'
    personal = 'personal'


class RecipeStatus(str, enum.Enum):
    draft = 'draft'
    approved = 'approved'
    retired = 'retired'


class CareplanStatus(str, enum.Enum):
    draft = 'draft'
    filed = 'filed'
    superseded = 'superseded'
    void = 'void'


class CareplanResultToken(db.Model):
    """What a token such as {urate.last} means: a label for the page, LOINC codes for the lookup."""
    __tablename__ = 'careplan_result_tokens'

    id            = db.Column(db.Integer, primary_key=True)
    key           = db.Column(db.String(40), unique=True, nullable=False)
    label         = db.Column(db.String(100), nullable=False)
    loinc_codes   = db.Column(db.JSON, nullable=False, default=list)   # trimmed codes
    expected_unit = db.Column(db.String(30))
    max_age_days  = db.Column(db.Integer)
    active        = db.Column(db.Boolean, nullable=False, default=True)
    created_at    = db.Column(db.DateTime, default=_now)
    updated_at    = db.Column(db.DateTime, default=_now, onupdate=_now)


class CareplanGuideline(db.Model):
    __tablename__ = 'careplan_guidelines'

    id               = db.Column(db.Integer, primary_key=True)
    title            = db.Column(db.String(300), nullable=False)
    publisher        = db.Column(db.String(200))
    edition          = db.Column(db.String(50))
    published_on     = db.Column(db.Date)
    url              = db.Column(db.String(500))
    accessed_on      = db.Column(db.Date)
    licence_note     = db.Column(db.String(200))
    superseded_by_id = db.Column(db.Integer, db.ForeignKey('careplan_guidelines.id'))
    created_by_id    = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at       = db.Column(db.DateTime, default=_now)


class CareplanRecipe(db.Model):
    """A recipe's stable identity; its text lives in immutable versions."""
    __tablename__ = 'careplan_recipes'

    id                     = db.Column(db.Integer, primary_key=True)
    issue_key              = db.Column(db.String(80), nullable=False, index=True)
    issue_label            = db.Column(db.String(150), nullable=False)
    variant_label          = db.Column(db.String(100))
    modifiers              = db.Column(db.JSON)          # display grouping only, never matched to a patient
    always_offer           = db.Column(db.Boolean, nullable=False, default=False)
    scope                  = db.Column(db.Enum(RecipeScope), nullable=False, default=RecipeScope.personal)
    owner_id               = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    copied_from_version_id = db.Column(db.Integer, db.ForeignKey('careplan_recipe_versions.id',
                                                                 use_alter=True, name='fk_recipe_copied_from'))
    current_version_id     = db.Column(db.Integer, db.ForeignKey('careplan_recipe_versions.id',
                                                                 use_alter=True, name='fk_recipe_current'))
    status                 = db.Column(db.Enum(RecipeStatus), nullable=False, default=RecipeStatus.draft)
    created_at             = db.Column(db.DateTime, default=_now)
    updated_at             = db.Column(db.DateTime, default=_now, onupdate=_now)

    owner           = db.relationship('User', foreign_keys=[owner_id], lazy='select')
    current_version = db.relationship('CareplanRecipeVersion', foreign_keys=[current_version_id],
                                      post_update=True, lazy='select')

    @property
    def title(self) -> str:
        return f'{self.issue_label} — {self.variant_label}' if self.variant_label else self.issue_label


class CareplanRecipeVersion(db.Model):
    """Immutable once approved: plans record the version they used."""
    __tablename__ = 'careplan_recipe_versions'
    __table_args__ = (db.UniqueConstraint('recipe_id', 'version', name='uq_recipe_version'),)

    id               = db.Column(db.Integer, primary_key=True)
    recipe_id        = db.Column(db.Integer, db.ForeignKey('careplan_recipes.id'), nullable=False, index=True)
    version          = db.Column(db.Integer, nullable=False)
    goals_text       = db.Column(db.Text, nullable=False, default='')
    management_text  = db.Column(db.Text, nullable=False, default='')
    providers_text   = db.Column(db.Text, nullable=False, default='')
    change_note      = db.Column(db.Text)
    ai_assisted      = db.Column(db.Boolean, nullable=False, default=False)
    authoring_run_id = db.Column(db.Integer, db.ForeignKey('pipeline_runs.id'))
    approved_by_id   = db.Column(db.Integer, db.ForeignKey('users.id'))
    approved_at      = db.Column(db.DateTime)
    review_due_on    = db.Column(db.Date)
    created_by_id    = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at       = db.Column(db.DateTime, default=_now)

    recipe    = db.relationship('CareplanRecipe', foreign_keys=[recipe_id], lazy='select')
    targets   = db.relationship('CareplanRecipeTarget', lazy='select', cascade='all, delete-orphan',
                                order_by='CareplanRecipeTarget.id')
    citations = db.relationship('CareplanRecipeCitation', lazy='select', cascade='all, delete-orphan',
                                order_by='CareplanRecipeCitation.id')

    @property
    def is_approved(self) -> bool:
        return self.approved_at is not None


class CareplanRecipeCitation(db.Model):
    __tablename__ = 'careplan_recipe_citations'

    id                 = db.Column(db.Integer, primary_key=True)
    recipe_version_id  = db.Column(db.Integer, db.ForeignKey('careplan_recipe_versions.id'), nullable=False, index=True)
    guideline_id       = db.Column(db.Integer, db.ForeignKey('careplan_guidelines.id'), nullable=False)
    section_ref        = db.Column(db.String(100))
    quote              = db.Column(db.Text)
    applies_to         = db.Column(db.String(20), nullable=False, default='target')  # goals · management · target
    verified_by_id     = db.Column(db.Integer, db.ForeignKey('users.id'))
    verified_at        = db.Column(db.DateTime)

    guideline = db.relationship('CareplanGuideline', lazy='joined')


class CareplanRecipeTarget(db.Model):
    """One target per token within a recipe version: the software never chooses between targets."""
    __tablename__ = 'careplan_recipe_targets'
    __table_args__ = (db.UniqueConstraint('recipe_version_id', 'token_id', name='uq_target_token'),)

    id                = db.Column(db.Integer, primary_key=True)
    recipe_version_id = db.Column(db.Integer, db.ForeignKey('careplan_recipe_versions.id'), nullable=False, index=True)
    token_id          = db.Column(db.Integer, db.ForeignKey('careplan_result_tokens.id'), nullable=False)
    target_text       = db.Column(db.String(60), nullable=False)
    citation_id       = db.Column(db.Integer, db.ForeignKey('careplan_recipe_citations.id'))

    token    = db.relationship('CareplanResultToken', lazy='joined')
    citation = db.relationship('CareplanRecipeCitation', foreign_keys=[citation_id], lazy='joined')


class Careplan(db.Model):
    __tablename__ = 'careplans'

    id                   = db.Column(db.Integer, primary_key=True)
    patient_id           = db.Column(db.Integer, nullable=False, index=True)
    previous_careplan_id = db.Column(db.Integer, db.ForeignKey('careplans.id'))
    status               = db.Column(db.Enum(CareplanStatus), nullable=False, default=CareplanStatus.draft)
    author_id            = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    header_text          = db.Column(EncryptedText())
    review_due_on        = db.Column(db.Date)
    draft_json           = db.Column(EncryptedText())        # the working grid while a draft
    draft_schema         = db.Column(db.Integer, nullable=False, default=1)
    draft_revision       = db.Column(db.Integer, nullable=False, default=0)
    draft_saved_at       = db.Column(db.DateTime)
    draft_saved_by_id    = db.Column(db.Integer, db.ForeignKey('users.id'))
    filed_by_id          = db.Column(db.Integer, db.ForeignKey('users.id'))
    filed_at             = db.Column(db.DateTime)
    filed_document       = db.Column(EncryptedText())        # the exact HTML filed
    filed_sha256         = db.Column(db.String(64))
    bp_exported          = db.Column(db.Boolean, nullable=False, default=False)
    bp_exported_at       = db.Column(db.DateTime)
    void_reason          = db.Column(EncryptedText())
    created_at           = db.Column(db.DateTime, default=_now)
    updated_at           = db.Column(db.DateTime, default=_now, onupdate=_now)

    author   = db.relationship('User', foreign_keys=[author_id], lazy='select')
    filed_by = db.relationship('User', foreign_keys=[filed_by_id], lazy='select')
    rows     = db.relationship('CareplanRow', lazy='select', cascade='all, delete-orphan',
                               order_by='CareplanRow.position')
    values   = db.relationship('CareplanValue', lazy='select', cascade='all, delete-orphan',
                               order_by='CareplanValue.id')


class CareplanRow(db.Model):
    """A filed row (drafts keep rows in draft_json)."""
    __tablename__ = 'careplan_rows'

    id                 = db.Column(db.Integer, primary_key=True)
    careplan_id        = db.Column(db.Integer, db.ForeignKey('careplans.id'), nullable=False, index=True)
    position           = db.Column(db.Integer, nullable=False)
    issue_label        = db.Column(EncryptedText(), nullable=False)
    issue_source       = db.Column(db.String(20), nullable=False, default='free_text')  # coded · standing · free_text
    issue_source_ref   = db.Column(EncryptedText())
    recipe_version_id  = db.Column(db.Integer, db.ForeignKey('careplan_recipe_versions.id'))
    goals_text         = db.Column(EncryptedText())
    management_text    = db.Column(EncryptedText())
    providers_text     = db.Column(EncryptedText())
    targets            = db.Column(db.JSON)      # {token_key: target_text} from the chosen recipe
    edited_from_recipe = db.Column(db.Boolean, nullable=False, default=False)


class CareplanValue(db.Model):
    """A value the doctor confirmed in the Fetch values list, frozen at filing."""
    __tablename__ = 'careplan_values'

    id              = db.Column(db.Integer, primary_key=True)
    careplan_id     = db.Column(db.Integer, db.ForeignKey('careplans.id'), nullable=False, index=True)
    token_key       = db.Column(db.String(40), nullable=False)
    label           = db.Column(db.String(100))
    value_text      = db.Column(db.String(60))
    unit            = db.Column(db.String(30))
    result_date     = db.Column(db.Date)
    loinc_code      = db.Column(db.String(20))
    status          = db.Column(db.String(20), nullable=False)  # found · not_found · stale · unit_mismatch · manual
    fetched_at      = db.Column(db.DateTime)
    confirmed_by_id = db.Column(db.Integer, db.ForeignKey('users.id'))


class CareplanEvent(db.Model):
    """Audit: counts and ids only, no clinical text."""
    __tablename__ = 'careplan_events'

    id          = db.Column(db.Integer, primary_key=True)
    careplan_id = db.Column(db.Integer, db.ForeignKey('careplans.id'), index=True)
    recipe_id   = db.Column(db.Integer, db.ForeignKey('careplan_recipes.id'), index=True)
    action      = db.Column(db.String(40), nullable=False)
    user_id     = db.Column(db.Integer, db.ForeignKey('users.id'))
    at          = db.Column(db.DateTime, default=_now)
    detail      = db.Column(db.JSON)
