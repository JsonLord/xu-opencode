import gradio as gr
import httpx
import json
from src.opencode_api.core.config import settings

def create_gradio_app():
    # Helper to interact with local API via httpx
    # Since we are mounting it on the same app, we can hit localhost:7860
    base_url = f"http://127.0.0.1:{settings.port}"
    headers = {"Authorization": f"Bearer {settings.access_token}"} if settings.access_token else {}

    with gr.Blocks(title="OpenCode API Chat") as demo:
        gr.Markdown("# OpenCode API Chat")

        with gr.Row():
            docs_btn = gr.Button("Docs", link="/docs")

        chatbot = gr.Chatbot(height=600)
        msg = gr.Textbox(placeholder="Type a message...", show_label=False)
        clear = gr.Button("Clear")

        state_session_id = gr.State(value=None)

        async def user(user_message, history):
            return "", history + [[user_message, None]]

        async def bot(history, session_id):
            if not history:
                yield history, session_id
                return

            user_message = history[-1][0]

            async with httpx.AsyncClient(base_url=base_url, headers=headers) as client:
                # Create session if needed
                if not session_id:
                    res = await client.post("/session", json={})
                    if res.status_code == 200:
                        session_id = res.json().get("id")
                    else:
                        history[-1][1] = f"Error creating session: {res.text}"
                        yield history, session_id
                        return

                # Send message (streaming)
                # the SSE endpoint returns strings prefixed with "data: "
                history[-1][1] = ""
                try:
                    async with client.stream(
                        "POST",
                        f"/session/{session_id}/message",
                        json={"content": user_message}
                    ) as response:
                        if response.status_code != 200:
                            history[-1][1] = f"Error: {response.status_code} {response.read().decode()}"
                            yield history, session_id
                            return

                        async for line in response.aiter_lines():
                            if line.startswith("data: ") and line != "data: [DONE]":
                                data_str = line[6:]
                                try:
                                    data = json.loads(data_str)
                                    if "content" in data and data["content"] and isinstance(data["content"], list):
                                        for content_block in data["content"]:
                                            if content_block.get("type") == "text":
                                                history[-1][1] += content_block.get("text", "")
                                                yield history, session_id
                                except Exception as e:
                                    pass
                except Exception as e:
                    history[-1][1] += f"\n\nConnection error: {str(e)}"
                    yield history, session_id

            yield history, session_id

        msg.submit(user, [msg, chatbot], [msg, chatbot], queue=False).then(
            bot, [chatbot, state_session_id], [chatbot, state_session_id]
        )

        clear.click(lambda: (None, None), None, [chatbot, state_session_id], queue=False)

    return demo
