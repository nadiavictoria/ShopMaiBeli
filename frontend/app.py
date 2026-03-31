import os
import chainlit as cl

USE_MOCK = os.getenv("USE_MOCK", "false").lower() == "true"

if USE_MOCK:
    from services.mock_backend import get_workflow_mock as _get_workflow, run_workflow_mock as _run_workflow
    async def get_workflow_data(chat_history):
        return await _get_workflow(chat_history[-1]["content"] if chat_history else "")
    async def stream_workflow(session_id, chat_history, workflow):
        async for event in _run_workflow(chat_history[-1]["content"] if chat_history else "", workflow):
            yield event
else:
    from services.backend import get_workflow, run_workflow, workflow_for_display
    async def get_workflow_data(chat_history):
        raw = await get_workflow(chat_history)
        return workflow_for_display(raw)
    async def stream_workflow(session_id, chat_history, workflow):
        async for event in run_workflow(session_id, chat_history):
            yield event


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
    cl.user_session.set("chat_history", [])
    await cl.Message(
        content="Welcome to ShopMaiBeli! Describe what you're looking for and I'll find the best options for you."
    ).send()


@cl.on_message
async def on_message(message: cl.Message):
    chat_history = cl.user_session.get("chat_history", [])
    chat_history.append({"role": "user", "content": message.content})
    cl.user_session.set("chat_history", chat_history)

    session_id = cl.user_session.get("id", "default")

    status = cl.Message(content="Generating workflow...")
    await status.send()

    try:
        workflow = await get_workflow_data(chat_history)
    except Exception as e:
        await cl.Message(content=f"Failed to generate workflow: {e}").send()
        return

    completed_nodes = []
    status.content = "Workflow generated."
    await status.update()
    await show_workflow_sidebar(workflow, completed_nodes=completed_nodes)

    stream_msg = cl.Message(content="")
    await stream_msg.send()

    try:
        async for event in stream_workflow(session_id, chat_history, workflow):
            if event["type"] == "workflow_updated":
                workflow = event["workflow"]
                await show_workflow_sidebar(workflow, completed_nodes=completed_nodes)
                await stream_msg.stream_token("
🧠 Workflow adapted")
            elif event["type"] == "node_started":
                await show_workflow_sidebar(
                    workflow,
                    active_node=event["node_name"],
                    completed_nodes=completed_nodes,
                )
                await stream_msg.stream_token(f"
🔄 {event['node_name']}")
            elif event["type"] == "node_completed":
                completed_nodes.append(event["node_name"])
                await show_workflow_sidebar(workflow, completed_nodes=completed_nodes)
                await stream_msg.stream_token(f"
✅ {event['node_name']}")
            elif event["type"] == "final":
                await show_workflow_sidebar(workflow, completed_nodes=completed_nodes)
                await stream_msg.stream_token("
📦 Final report ready
")
                html = event.get("html", "")
                chat_history.append({"role": "assistant", "content": html or event.get("message", "")})
                cl.user_session.set("chat_history", chat_history)
                await cl.Message(content=html).send()
            elif event["type"] == "error":
                await stream_msg.stream_token(f"
❌ Error: {event.get('message', 'Unknown error')}")
    except Exception as e:
        await stream_msg.stream_token(f"
❌ Execution error: {e}")

    await stream_msg.update()
