import gradio as gr
from main import app as fastapi_app
import uvicorn
import os

# Create a simple Gradio UI so Hugging Face registers it as a valid Gradio space
def welcome():
    return "NurseAssist AI Backend is Online! Connect your Flutter app to this URL."

with gr.Blocks(title="NurseAssist AI API") as demo:
    gr.Markdown("# NurseAssist AI Backend")
    gr.Markdown("This space hosts the FastAPI backend for the NurseAssist AI Flutter application.")
    gr.Interface(fn=welcome, inputs=None, outputs="text")

# Mount the FastAPI app onto the Gradio blocks
app = gr.mount_gradio_app(fastapi_app, demo, path="/")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=7860)
