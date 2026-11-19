from abc import ABC, abstractmethod
from app.services.pipeline.context import WorkflowContext


class PipelineNode(ABC):
    node_type: str = 'base'

    @abstractmethod
    def execute(self, context: WorkflowContext, config: dict) -> WorkflowContext:
        """Execute the node and return the (potentially mutated) context."""
        ...
