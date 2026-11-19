"""BundleRenderService — fetches a DataBundle and renders it in text/json/markdown.

Used by the AI pipeline (DataAssemblyNode) and the optional patient API.
Redaction is NOT applied here — callers apply a single-pass redaction on the
fully assembled string after all blocks have been embedded.
"""

import json
from datetime import datetime, date
from decimal import Decimal
from typing import Any

from flask import current_app


def _json_default(obj):
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    return str(obj)


class BundleRenderService:

    VALID_FORMATS = frozenset({'text', 'json', 'markdown'})

    def __init__(self, patient_json_service=None):
        if patient_json_service is None:
            from app.services.patient_json_service import PatientJsonService
            patient_json_service = PatientJsonService()
        self._pjs = patient_json_service

    # ── Public API ─────────────────────────────────────────────────────────────

    def render(
        self,
        bundle_name: str,
        patient_id: int,
        fmt: str = 'text',
        deidentify: bool = False,
    ) -> str:
        """Fetch bundle and render in the requested format.

        Raises ValueError on unknown format or missing bundle.
        Individual block failures are logged and skipped.
        """
        if fmt not in self.VALID_FORMATS:
            raise ValueError(
                f"Invalid format '{fmt}'. Must be one of: {', '.join(sorted(self.VALID_FORMATS))}"
            )

        blocks = self._fetch_blocks(bundle_name, patient_id, deidentify)
        if not blocks:
            return f"[Bundle '{bundle_name}' returned no data]"

        if fmt == 'json':
            return self._render_json(blocks)
        if fmt == 'markdown':
            return self._render_markdown(blocks)
        return self._render_text(blocks)

    # ── Internal ───────────────────────────────────────────────────────────────

    def _fetch_blocks(
        self,
        bundle_name: str,
        patient_id: int,
        deidentify: bool,
    ) -> list[tuple[str, Any]]:
        """Return list of (label, data) pairs in bundle sequence order."""
        from app.models.data_bundle import DataBundle
        from app.services.patient_json_service import BLOCK_LABELS

        bundle_def = DataBundle.query.filter_by(name=bundle_name, is_active=True).first()
        if not bundle_def:
            raise ValueError(f"DataBundle '{bundle_name}' not found.")

        results: list[tuple[str, Any]] = []
        for bb in bundle_def.blocks:
            block_name = bb.block_source
            label = bb.label or BLOCK_LABELS.get(block_name, block_name.replace('_', ' ').title())
            try:
                data = self._pjs.get_atomic_block(block_name, patient_id, deidentify=deidentify)
                results.append((label, data))
            except Exception as exc:
                current_app.logger.warning(
                    'BundleRenderService: block=%s patient=%s error=%s',
                    block_name, patient_id, exc,
                )

        return results

    def _render_text(self, blocks: list[tuple[str, Any]]) -> str:
        sections = [f'## {label}\n{_block_as_text(data)}' for label, data in blocks]
        return '\n\n'.join(sections)

    def _render_markdown(self, blocks: list[tuple[str, Any]]) -> str:
        sections = [f'### {label}\n{_block_as_markdown(data)}' for label, data in blocks]
        return '\n\n'.join(sections)

    def _render_json(self, blocks: list[tuple[str, Any]]) -> str:
        payload = [{'block': label, 'data': data} for label, data in blocks]
        return json.dumps(payload, indent=2, default=_json_default, ensure_ascii=False)


# ── Block-level renderers ──────────────────────────────────────────────────────

def _block_as_text(data: Any) -> str:
    if data is None:
        return 'Not recorded.'
    if isinstance(data, str):
        return data if data.strip() else 'Not recorded.'
    if isinstance(data, list):
        if not data:
            return 'None recorded.'
        lines = []
        for item in data:
            if isinstance(item, dict):
                lines.append('• ' + ' | '.join(
                    f"{k.replace('_', ' ').title()}: {v}"
                    for k, v in item.items()
                    if v is not None and str(v).strip()
                ))
            else:
                lines.append(f'• {item}')
        return '\n'.join(lines)
    if isinstance(data, dict):
        if not data:
            return 'Not recorded.'
        lines = []
        for k, v in data.items():
            if v is None or str(v).strip() == '':
                continue
            label = k.replace('_', ' ').title()
            if isinstance(v, (list, dict)):
                lines.append(f'{label}:\n{_block_as_text(v)}')
            else:
                lines.append(f'{label}: {v}')
        return '\n'.join(lines) if lines else 'Not recorded.'
    return str(data)


def _block_as_markdown(data: Any) -> str:
    if data is None:
        return '*Not recorded.*'
    if isinstance(data, str):
        return data if data.strip() else '*Not recorded.*'
    if isinstance(data, list):
        if not data:
            return '*None recorded.*'
        lines = []
        for item in data:
            if isinstance(item, dict):
                parts = [
                    f"**{k.replace('_', ' ').title()}:** {v}"
                    for k, v in item.items()
                    if v is not None and str(v).strip()
                ]
                lines.append('- ' + ' | '.join(parts))
            else:
                lines.append(f'- {item}')
        return '\n'.join(lines)
    if isinstance(data, dict):
        if not data:
            return '*Not recorded.*'
        lines = []
        for k, v in data.items():
            if v is None or str(v).strip() == '':
                continue
            label = k.replace('_', ' ').title()
            if isinstance(v, (list, dict)):
                lines.append(f'**{label}:**\n{_block_as_markdown(v)}')
            else:
                lines.append(f'- **{label}:** {v}')
        return '\n'.join(lines) if lines else '*Not recorded.*'
    return str(data)
