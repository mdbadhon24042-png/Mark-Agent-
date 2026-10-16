
import os
import logging
import base64

from flask import Flask, request, jsonify
from google import genai
from elevenlabs.client import ElevenLabs

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

API_KEY = os.environ.get("API_KEY", "")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL = os.environ.get(
    "GEMINI_MODEL", "gemini-3.8-flash"
)

ELEVENLABS_API_KEY = os.environ.get(
    "ELEVENLABS_API_KEY", ""
)
ELEVENLABS_VOICE_ID = os.environ.get(
    "ELEVENLABS_VOICE_ID", ""
)

gemini = (
    genai.Client(api_key=GEMINI_API_KEY)
    if GEMINI_API_KEY else None
)

elevenlabs = (
    ElevenLabs(api_key=ELEVENLABS_API_KEY)
    if ELEVENLABS_API_KEY else None
)


def authorized():
    if not API_KEY:
        return True

    return (
        request.headers.get("Authorization", "")
        == f"Bearer {API_KEY}"
    )


def get_message(data):
    message = data.get("message") or data.get("prompt")
    if not isinstance(message, str):
        return None

    message = message.strip()
    if not message or len(message) > 12000:
        return None

    return message


@app.get("/")
def home():
    return jsonify({
        "status": "online",
        "service": "Real AI Agent",
        "endpoint": "/execute",
        "voice_endpoint": "/voice",
        "method": "POST"
    })


@app.get("/health")
def health():
    return jsonify({
        "status": "ok",
        "gemini_configured": gemini is not None,
        "voice_configured": (
            elevenlabs is not None
            and bool(ELEVENLABS_VOICE_ID)
        )
    })


@app.post("/execute")
def execute():
    if not authorized():
        return jsonify({"error": "Unauthorized"}), 401

    if not request.is_json:
        return jsonify({
            "error": "Content-Type must be application/json"
        }), 415

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "Invalid JSON"}), 400

    message = get_message(data)
    if message is None:
        return jsonify({
            "error": "Provide a valid message or prompt"
        }), 400

    if gemini is None:
        return jsonify({
            "error": "Set GEMINI_API_KEY in Render"
        }), 503

    try:
        response = gemini.models.generate_content(
            model=GEMINI_MODEL,
            contents=message
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
        })

    except Exception:
        logging.exception("Gemini request failed")
        return jsonify({
            "error": "Gemini request failed"
        }), 502


@app.post("/voice")
def voice():
    if not authorized():
        return jsonify({"error": "Unauthorized"}), 401

    if not request.is_json:
        return jsonify({
            "error": "Content-Type must be application/json"
        }), 415

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "Invalid JSON"}), 400

    message = get_message(data)
    if message is None:
        return jsonify({
            "error": "Provide a valid message or prompt"
        }), 400

    if gemini is None:
        return jsonify({
            "error": "Set GEMINI_API_KEY in Render"
        }), 503

    if elevenlabs is None or not ELEVENLABS_VOICE_ID:
        return jsonify({
            "error": (
                "Set ELEVENLABS_API_KEY and "
                "ELEVENLABS_VOICE_ID in Render"
            )
        }), 503

    try:
        response = gemini.models.generate_content(
            model=GEMINI_MODEL,
            contents=message
        )

        answer = response.text
        if not answer:
            return jsonify({
                "error": "Gemini returned no text"
            }), 502

        audio_chunks = elevenlabs.text_to_speech.convert(
            text=answer,
            voice_id=ELEVENLABS_VOICE_ID,
            model_id="eleven_multilingual_v2",
            output_format="mp3_44100_128"
        )

        audio_bytes = b"".join(audio_chunks)

        return jsonify({
            "success": True,
            "answer": answer,
            "audio_base64": base64.b64encode(
                audio_bytes
            ).decode("ascii"),
            "audio_content_type": "audio/mpeg"
        })

    except Exception:
        logging.exception("Voice request failed")
        return jsonify({
            "error": "Voice generation failed"
        }), 502


@app.errorhandler(404)
def not_found(error):
    return jsonify({"error": "Route not found"}), 404


@app.errorhandler(405)
def method_not_allowed(error):
    return jsonify({
        "error": "Method not allowed"
    }), 405


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "10000"))
    app.run(host="0.0.0.0", port=port)
