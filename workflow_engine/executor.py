import asyncio
import logging
from .workflow import Workflow
from .context import ExecutionContext
from .models import NodeOutput, NodeNotification

logger = logging.getLogger(__name__)


class WorkflowExecutor:
    def __init__(self, workflow: Workflow):
        self.workflow = workflow
        self._contexts: dict[str, ExecutionContext] = {}

    @classmethod
    def from_json(cls, workflow_json: dict) -> "WorkflowExecutor":
        return cls(Workflow(workflow_json))

    def get_context(self, session_id: str) -> ExecutionContext:
        if session_id not in self._contexts:
            self._contexts[session_id] = ExecutionContext(session_id=session_id)
        return self._contexts[session_id]

    def _get_execution_levels(self) -> list[list[str]]:
        """Group nodes by topological level so nodes at the same level can run in parallel."""
        execution_order = self.workflow.get_execution_order()
        levels = []
        placed: set[str] = set()

        while len(placed) < len(execution_order):
            current_level = []
            for name in execution_order:
                if name in placed:
                    continue
                parents = self.workflow.get_parent_nodes(name)
                if all(p in placed for p in parents):
                    current_level.append(name)
            for name in current_level:
                placed.add(name)
            if current_level:
                levels.append(current_level)

        return levels

    async def _execute_node(self, node_name: str, context: ExecutionContext) -> NodeNotification:
        from nodes import get_executor_class

        node = self.workflow.nodes[node_name]
        executor_class = get_executor_class(node.node_type)
        executor = executor_class(node, self.workflow)
        input_data = context.get_input_for_node(node_name, self.workflow)
        output = await executor.execute(input_data, context)
        context.set_node_output(node_name, output)
        return executor.get_notification(output, context)

    async def _execute_node_with_retry(
        self, node_name: str, context: ExecutionContext, max_retries: int = 3
    ) -> NodeNotification:
        for attempt in range(max_retries):
            try:
                return await self._execute_node(node_name, context)
            except Exception as e:
                if attempt == max_retries - 1:
                    logger.error(f"Node '{node_name}' failed after {max_retries} attempts: {e}")
                    context.set_node_output(node_name, NodeOutput.single({"error": str(e)}))
                    return NodeNotification(
                        node_name=node_name,
                        session_id=context.session_id,
                        message=f"Node failed: {e}",
                        notification_type="step",
                        data={"error": str(e)}
                    )
                wait = 2 ** attempt
                logger.warning(f"Node '{node_name}' attempt {attempt + 1} failed, retrying in {wait}s: {e}")
                await asyncio.sleep(wait)

    async def execute(self, session_id: str, chat_history: list = None, files: list = None):
        """Async generator that yields NodeNotifications as nodes complete."""
        context = self.get_context(session_id)
        context.chat_history = chat_history or []
        context.files = files or []
        context.node_outputs = {}

        levels = self._get_execution_levels()

        for level_nodes in levels:
            if len(level_nodes) == 1:
                yield NodeNotification(
                    node_name=level_nodes[0],
                    session_id=session_id,
                    message=f"Starting {level_nodes[0]}",
                    notification_type="start"
                )
                result = await self._execute_node_with_retry(level_nodes[0], context)
                yield result
            else:
                # Parallel execution
                for name in level_nodes:
                    yield NodeNotification(
                        node_name=name,
                        session_id=session_id,
                        message=f"Starting {name}",
                        notification_type="start"
                    )
                tasks = [self._execute_node_with_retry(name, context) for name in level_nodes]
                results = await asyncio.gather(*tasks, return_exceptions=True)
                for result in results:
                    if isinstance(result, Exception):
                        logger.error(f"Parallel node failed: {result}")
                    else:
                        yield result
