import logging
import json
import base64
import httpx

import chainlit as cl
from chainlit.input_widget import TextInput

logging.basicConfig(level=logging.INFO)


def _join_url(base_url: str, path: str) -> str:
    """Join base_url and path without adding any extra suffix."""
    return base_url.rstrip("/") + "/" + path.lstrip("/")


def _build_html_elements(html: str):
    """Return a sidebar HtmlPreview element when html content is present."""
    if not html:
        return []
    return [
        cl.CustomElement(
            name="HtmlPreview",
            props={"html": html, "title": "Shopping Report"},
            display="side",
        )
    ]


async def _render_event(event: dict):
    """
    Render a unified event structure into Chainlit.
    Expected keys:
      - type: "message" | "step"
      - name: str (for step)
      - text: str
      - html: str
    """
    t = event.get("type", "message")
    name = event.get("name") or "Run"
    text = event.get("text") or ""
    html = event.get("html") or ""

    elements = _build_html_elements(html)

    # Combine text with workflow structure (markdown)
    if t == "message":
        await cl.Message(content=text, elements=elements).send()
    elif t == "step":
        output = f"{text}\n\n{html}" if html else text
        async with cl.Step(
            name=name,
            type="run",
            show_input=False,
            elements=elements,
        ) as step:
            step.output = output
    else:
        await cl.Message(content=f"Error: unsupported event type '{t}'").send()


# -----------------------------
# Chainlit lifecycle + settings + commands
# -----------------------------
@cl.on_chat_start
async def on_chat_start():
    """
    Initialize chat session:
    1) Register Chainlit commands.
    2) Send ChatSettings (Base URL only).
    """
    # Register commands
    commands = [
        {
            "id": "get_workflow",
            "icon": "hammer",
            "description": "POST {base_url}/get_workflow",
            "persistent": True,
        },
        {
            "id": "run_workflow",
            "icon": "play",
            "description": "POST {base_url}/run_workflow (streaming)",
            "persistent": True,
        },
    ]
    await cl.context.emitter.set_commands(commands)

    # Chat settings: Base URL only
    settings = await cl.ChatSettings(
        [
            TextInput(
                id="base_url",
                label="Base URL",
                initial=cl.user_session.get("base_url") or "http://localhost:8888",
                placeholder="e.g. http://localhost:8888",
                description="Requests will be sent to {base_url}/get_workflow or {base_url}/run_workflow",
            )
        ]
    ).send()

    base_url = (settings.get("base_url") or "http://localhost:8888").strip()
    cl.user_session.set("base_url", base_url)


@cl.on_settings_update
async def on_settings_update(settings: dict):
    """Update base_url when user changes Chat Settings."""
    base_url = (settings.get("base_url") or cl.user_session.get("base_url") or "http://localhost:8888").strip()
    cl.user_session.set("base_url", base_url)


@cl.on_message
async def on_message(message: cl.Message):
    """
    Route user messages based on Chainlit Command (message.command).

    - "get_workflow"   -> POST {base_url}/get_workflow (single response)
    - "run_workflow"   -> POST {base_url}/run_workflow (streaming NDJSON)
    - otherwise        -> error
    """
    base_url = (cl.user_session.get("base_url") or "").strip()
    if not base_url:
        await cl.Message(content="Error: Base URL is empty. Please set it in Chat Settings.").send()
        return

    # Extract files from message
    files = await _get_files_from_message(message)

    cmd = getattr(message, "command", None)
    if cmd == "get_workflow":
        url = _join_url(base_url, "get_workflow")
        await _handle_single_response(url, files)
    elif cmd == "run_workflow":
        url = _join_url(base_url, "run_workflow")
        await _handle_streaming_response(url, files)
    else:
        await cl.Message(
            content="Error: no valid command selected. Please choose 'get_workflow' or 'run_workflow' and resend."
        ).send()


def _get_session_id() -> str:
    """Get the current Chainlit session ID."""
    return cl.context.session.id


async def _get_files_from_message(message: cl.Message) -> list:
    """
    Extract file information from message elements.
    Returns a list of dicts with file metadata and base64 content.
    """
    files = []
    if not message.elements:
        return files

    for element in message.elements:
        # Handle file elements (images, pdfs, etc.)
        if hasattr(element, "path") and element.path:
            try:
                with open(element.path, "rb") as f:
                    content = base64.b64encode(f.read()).decode("utf-8")
                files.append({
                    "name": getattr(element, "name", "unknown"),
                    "mime": getattr(element, "mime", "application/octet-stream"),
                    "size": getattr(element, "size", 0),
                    "content": content,  # base64 encoded
                })
                logging.info(f"Extracted file: {element.name} ({element.mime}, {element.size} bytes)")
            except Exception as e:
                logging.warning(f"Failed to read file {element.path}: {e}")

    return files


async def _handle_single_response(url: str, files: list = None):
    """Handle single JSON response (for get_workflow)."""
    chat_history = cl.chat_context.to_openai()
    session_id = _get_session_id()

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, json={
                "session_id": session_id,
                "chat_history": chat_history,
                "files": files or [],
            })

        if resp.status_code != 200:
            await cl.Message(content=f"HTTP {resp.status_code} from {url}:\n{resp.text}").send()
            return

        try:
            data = resp.json()
            if isinstance(data, dict) and data.get("type") in ("message", "step"):
                await _render_event(data)
                return

            if isinstance(data, dict) and ("text" in data or "html" in data):
                await _render_event({
                    "type": "message",
                    "name": "Result",
                    "text": str(data.get("text") or ""),
                    "html": str(data.get("html") or ""),
                })
                return

            await cl.Message(content=json.dumps(data, ensure_ascii=False, indent=2)).send()
        except Exception:
            await cl.Message(content=resp.text).send()

    except Exception as e:
        await cl.Message(content=f"Request failed: {e}").send()


async def _handle_streaming_response(url: str, files: list = None):
    """
    Handle streaming NDJSON response (for run_workflow).
    Each line is a JSON object, render it immediately as it arrives.
    """
    chat_history = cl.chat_context.to_openai()
    session_id = _get_session_id()

    try:
        async with httpx.AsyncClient(timeout=300.0) as client:
            async with client.stream("POST", url, json={
                "session_id": session_id,
                "chat_history": chat_history,
                "files": files or [],
            }) as resp:
                if resp.status_code != 200:
                    await cl.Message(content=f"HTTP {resp.status_code} from {url}").send()
                    return

                # Read and render each line as it arrives
                async for line in resp.aiter_lines():
                    if line:
                        logging.info(f"Received line: {line[:100]}...")
                        try:
                            data = json.loads(line)
                            await _render_event(data)
                        except json.JSONDecodeError:
                            logging.warning(f"Failed to parse NDJSON line: {line}")
                            continue

    except Exception as e:
        await cl.Message(content=f"Streaming request failed: {e}").send()
