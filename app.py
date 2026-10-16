
import os
from flask import Flask, request, jsonify
from dotenv import load_dotenv
from google import genai

load_dotenv()

app = Flask(__name__)

AGENT_API_KEY = os.getenv("AGENT_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
AI_MODEL = os.getenv("AI_MODEL","gemini-3.8-flash")

client = (
    genai.Client(api_key=GEMINI_API_KEY)
    if GEMINI_API_KEY
    else None
)

SYSTEM_PROMPT = """
You are a personal AI assistant.
Understand Bangla, Banglish and English.
Reply naturally in Bengali unless asked otherwise.
You can answer questions and help plan phone actions.
You cannot directly control the phone from this server.
Never claim an action succeeded without confirmation.
"""


@app.get("/")
def home():
    return jsonify({
        "status": "online",
        "agent": "Personal AI Agent"
    })


@app.get("/health")
def health():
    return jsonify({
        "server": "ok",
        "ai_configured": client is not None
    })


@app.post("/api/chat")
def chat():
    if not AGENT_API_KEY:
        return jsonify({"error": "Server key not configured"}), 500

    auth = request.headers.get("Authorization", "")
    if auth != f"Bearer {AGENT_API_KEY}":
        return jsonify({"error": "Unauthorized"}), 401

    if client is None:
        return jsonify({"error": "Gemini API key not configured"}), 503

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "JSON object required"}), 400

    message = data.get("message")
    if not isinstance(message, str) or not message.strip():
        return jsonify({"error": "Message required"}), 400

    if len(message) > 4000:
        return jsonify({"error": "Message too long"}), 413

    try:
        response = client.models.generate_content(
            model=AI_MODEL,
            contents=SYSTEM_PROMPT + "\n\nUser:\n" + message.strip()
        )

        answer = response.text
        if not answer:
            return jsonify({"error": "Empty AI response"}), 502

        return jsonify({
            "status": "success",
            "reply": answer
        })

    except Exception:
        app.logger.exception("AI request failed")
        return jsonify({"error": "AI request failed"}), 502


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=False)
