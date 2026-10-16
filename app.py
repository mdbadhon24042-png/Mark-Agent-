
import os
import logging
from flask import Flask, request, jsonify
from google import genai

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

# Render Environment Variables
API_KEY = os.environ.get("API_KEY", "")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL = os.environ.get(
    "GEMINI_MODEL", "gemini-3.8-flash"
)

client = None
if GEMINI_API_KEY:
    client = genai.Client(api_key=GEMINI_API_KEY)


@app.get("/")
def home():
    return jsonify({
        "status": "online",
        "service": "Real AI Agent",
        "endpoint": "/execute",
        "method": "POST"
    }), 200


@app.get("/health")
def health():
    return jsonify({
        "status": "ok",
        "gemini_configured": client is not None
    }), 200


@app.post("/execute")
def execute():
    # API access authentication
    if API_KEY:
        auth = request.headers.get("Authorization", "")
        expected = f"Bearer {API_KEY}"

        if auth != expected:
            return jsonify({
                "error": "Unauthorized",
                "message": "Valid API key required"
            }), 401

    if not request.is_json:
        return jsonify({
            "error": "Content-Type must be application/json"
        }), 415

    data = request.get_json(silent=True)

    if not isinstance(data, dict):
        return jsonify({"error": "Invalid JSON object"}), 400

    message = data.get("message") or data.get("prompt")

    if not isinstance(message, str) or not message.strip():
        return jsonify({
            "error": "Provide a non-empty message or prompt"
        }), 400

    if len(message) > 12000:
        return jsonify({"error": "Message is too long"}), 413

    if client is None:
        return jsonify({
            "error": "Gemini is not configured",
            "message": "Set GEMINI_API_KEY in Render Environment"
        }), 503

    try:
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=message.strip()
        )

        answer = response.text

        if not answer:
            return jsonify({
                "error": "Gemini returned no text"
            }), 502

        return jsonify({
            "success": True,
            "model": GEMINI_MODEL,
            "answer": answer
        }), 200

    except Exception:
        logging.exception("Gemini request failed")
        return jsonify({
            "error": "Gemini request failed",
            "message": (
                "Check Render logs, API key, model name, "
                "API quota and network access."
            )
        }), 502


@app.errorhandler(404)
def not_found(error):
    return jsonify({"error": "Route not found"}), 404


@app.errorhandler(405)
def method_not_allowed(error):
    return jsonify({
        "error": "Method not allowed",
        "hint": "Use POST for /execute and GET for /"
    }), 405


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "10000"))
    app.run(host="0.0.0.0", port=port)
