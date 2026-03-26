from services.mock_backend import get_workflow_mock, run_workflow_mock
import chainlit as cl


async def show_workflow_sidebar(
    workflow: dict, active_node: str | None = None, completed_nodes=None
):
    completed_nodes = completed_nodes or []
    workflow_element = cl.CustomElement(
        name="WorkflowGraph",
        props={
            "workflow": workflow,
            "active_node": active_node,
            "completed_nodes": completed_nodes,
        },
        display="side",
    )
    sidebar_key = "|".join(
        [
            ",".join(node["name"] for node in workflow.get("nodes", [])),
            active_node or "",
            ",".join(completed_nodes),
        ]
    )
    await cl.ElementSidebar.set_title("Generated workflow")
    await cl.ElementSidebar.set_elements([workflow_element], key=sidebar_key)


@cl.on_chat_start
async def start():
    await cl.Message(
        content="Welcome to ShopMaiBeli! Try asking for a product recommendation."
    ).send()


@cl.on_message
async def on_message(message: cl.Message):
    status = cl.Message(content="Generating workflow...")
    await status.send()

    workflow = await get_workflow_mock(message.content)
    completed_nodes = []

    status.content = "Workflow generated."
    await status.update()
    await show_workflow_sidebar(workflow, completed_nodes=completed_nodes)

    stream_msg = cl.Message(content="")
    await stream_msg.send()

    async for event in run_workflow_mock(message.content, workflow):
        if event["type"] == "workflow_updated":
            workflow = event["workflow"]
            await show_workflow_sidebar(workflow, completed_nodes=completed_nodes)
            await stream_msg.stream_token("\n🧠 Workflow adapted with parallel branches")
        elif event["type"] == "node_started":
            await show_workflow_sidebar(
                workflow,
                active_node=event["node_name"],
                completed_nodes=completed_nodes,
            )
            await stream_msg.stream_token(f"\n🔄 {event['node_name']}")
        elif event["type"] == "node_completed":
            completed_nodes.append(event["node_name"])
            await show_workflow_sidebar(workflow, completed_nodes=completed_nodes)
            await stream_msg.stream_token(f"\n✅ {event['node_name']}")
        elif event["type"] == "final":
            await show_workflow_sidebar(workflow, completed_nodes=completed_nodes)
            await stream_msg.stream_token("\n📦 Final report ready\n")

            await cl.Message(
                content=f"Here is your report:\n\n{event['html']}",
            ).send()

    await stream_msg.update()
