"""Publish — dispara n8n workflow de publicação multi-canal."""
from state.schema import EmpireState
from tools.n8n import trigger_workflow


async def run(state: EmpireState) -> EmpireState:
    for content in state.content_queue:
        if content.status == "approved":
            try:
                result = await trigger_workflow("publish-multi-channel", {
                    "content": content.model_dump(),
                    "channels": content.channels,
                })
                content.status = "published"
                state.published.append(content)
                state.logs.append(f"Published: {content.title} → {content.channels}")
            except Exception as e:
                state.errors.append(f"Publish failed for {content.id}: {e}")
    return state
