"""DeRedactionNode — restores original text in context.results['final_output'].

The restore is the bps_redaction core's `deredact` (ADR-114), in three passes:
  1. Exact match: replace tokens verbatim using context.token_map
  2. Count any well-formed [Redacted *: XX-<hex>] tokens left (not in the map)
  3. Placeholder sweep: replace any remaining [Redacted *: *] patterns with a
     safe '(redacted)' marker so no token leaks through to the user

A reply that is a JSON object or array (the chatbots' {"Title", "Response"}
envelope) is restored inside its parsed strings and written back as JSON, so
a restored value containing a quote or a backslash cannot break it (ADR-073).

Writes restored text back to context.results['final_output'].
"""

from bps_redaction.deredact import deredact

from app.services.pipeline.context import WorkflowContext
from app.services.pipeline.node import PipelineNode


class DeRedactionNode(PipelineNode):
    node_type = 'deredaction'

    def execute(self, context: WorkflowContext, config: dict) -> WorkflowContext:
        text = context.results.get('final_output', '')
        if not text:
            context.log('DeRedactionNode', 'No final_output to de-redact')
            return context

        token_map = context.token_map
        if not token_map:
            context.log('DeRedactionNode', 'No token_map; skipping (policy may be redact_none)')
            return context

        result = deredact(text, token_map)
        context.results['final_output'] = result.text
        context.log('DeRedactionNode',
                    f'Restored {result.restored} token(s); '
                    f'{result.unresolved} unresolved; {result.swept} swept')
        return context
