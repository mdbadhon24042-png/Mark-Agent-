
import os
import json
import base64
import logging

from quart import Quart, request, jsonify, websocket
from google import genai
from elevenlabs.client import ElevenLabs
from websockets.asyncio.client import connect

app = Quart(__name__)
logging.basicConfig(level=logging.INFO)

API_KEY = os.environ.get("API_KEY", "")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.8-flash")

ELEVENLABS_API_KEY = os.environ.get("ELEVENLABS_API_KEY", "")
ELEVENLABS_VOICE_ID = os.environ.get("ELEVENLABS_VOICE_ID", "")

gemini = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None
elevenlabs = ElevenLabs(api_key=ELEVENLABS_API_KEY) if ELEVENLABS_API_KEY else None


def authorized():
    if not API_KEY:
        return True
    return request.headers.get("Authorization", "") == f"Bearer {API_KEY}"


def get_message(data):
    if not isinstance(data, dict):
        return None
    message = data.get("message") or data.get("prompt")
    if not isinstance(message, str):
        return None
    message = message.strip()
    return message if message and len(message) <= 12000 else None


@app.get("/")
async def home():
    return jsonify({
        "status": "online",
        "service": "Real AI Agent",
        "endpoint": "/execute",
        "voice_endpoint": "/voice",
        "websocket_endpoint": "/ws/voice"
    })


@app.get("/health")
async def health():
    return jsonify({
        "status": "ok",
        "gemini_configured": gemini is not None,
        "voice_configured": bool(
            elevenlabs and ELEVENLABS_VOICE_ID and ELEVENLABS_API_KEY
        )
    })


@app.post("/execute")
async def execute():
    if not authorized():
        return jsonify({"error": "Unauthorized"}), 401

    data = await request.get_json(silent=True)
    message = get_message(data)

    if not message:
        return jsonify({"error": "Provide a valid message or prompt"}), 400

    if gemini is None:
        return jsonify({"error": "Set GEMINI_API_KEY in Render"}), 503

    try:
        response = await gemini.aio.models.generate_content(
            model=GEMINI_MODEL,
            contents=message
        )
        answer = response.text
        if not answer:
            return jsonify({"error": "Gemini returned no text"}), 502
        return jsonify({
            "success": True,
            "model": GEMINI_MODEL,
            "answer": answer
        })
    except Exception:
        logging.exception("Gemini request failed")
        return jsonify({"error": "Gemini request failed"}), 502


@app.post("/voice")
async def voice():
    if not authorized():
        return jsonify({"error": "Unauthorized"}), 401

    data = await request.get_json(silent=True)
    message = get_message(data)

    if not message:
        return jsonify({"error": "Provide a valid message or prompt"}), 400

    if gemini is None:
        return jsonify({"error": "Set GEMINI_API_KEY in Render"}), 503

    if elevenlabs is None or not ELEVENLABS_VOICE_ID:
        return jsonify({"error": "Set ElevenLabs API key and Voice ID"}), 503

    try:
        response = await gemini.aio.models.generate_content(
            model=GEMINI_MODEL,
            contents=message
        )
        answer = response.text
        if not answer:
            return jsonify({"error": "Gemini returned no text"}), 502

        audio_chunks = elevenlabs.text_to_speech.convert(
            text=answer,
            voice_id=ELEVENLABS_VOICE_ID,
            model_id="eleven_multilingual_v2",
            output_format="mp3_44100_128"
        )
        audio = b"".join(audio_chunks)

        return jsonify({
            "success": True,
            "answer": answer,
            "audio_base64": base64.b64encode(audio).decode("ascii"),
            "audio_content_type": "audio/mpeg"
        })
    except Exception:
        logging.exception("Voice request failed")
        return jsonify({"error": "Voice generation failed"}), 502


@app.websocket("/ws/voice")
async def voice_stream():
    # প্রথম WebSocket message-এ পাঠাবে:
    # {"api_key":"YOUR_API_KEY","text":"Hello"}
    try:
        first = await websocket.receive()
        data = json.loads(first)

        if API_KEY and data.get("api_key") != API_KEY:
            await websocket.send(json.dumps({"error": "Unauthorized"}))
            await websocket.close(1008)
            return

        text = data.get("text", "")
        if not isinstance(text, str) or not text.strip() or len(text) > 12000:
            await websocket.send(json.dumps({"error": "Invalid text"}))
            await websocket.close(1008)
            return

        if not ELEVENLABS_API_KEY or not ELEVENLABS_VOICE_ID:
            await websocket.send(json.dumps({"error": "ElevenLabs not configured"}))
            await websocket.close(1011)
            return

        url = (
            "wss://api.elevenlabs.io/v1/text-to-speech/"
            f"{ELEVENLABS_VOICE_ID}/stream-input"
            "?model_id=eleven_flash_v2_5&output_format=mp3_44100_128"
        )

        async with connect(
            url,
            additional_headers={"xi-api-key": ELEVENLABS_API_KEY},
            open_timeout=20
        ) as eleven_ws:
            await eleven_ws.send(json.dumps({
                "text": " ",
                "voice_settings": {
                    "stability": 0.5,
                    "similarity_boost": 0.75
                },
                "generation_config": {
                    "chunk_length_schedule": [120, 160, 250, 290]
                }
            }))

            # Send text in small chunks to ElevenLabs.
            for start in range(0, len(text), 180):
                chunk = text[start:start + 180]
                await eleven_ws.send(json.dumps({
                    "text": chunk,
                    "try_trigger_generation": True
                }))

            await eleven_ws.send(json.dumps({"text": ""}))

            async for raw in eleven_ws:
                packet = json.loads(raw)

                if packet.get("audio"):
                    await websocket.send(json.dumps({
                        "type": "audio",
                        "audio_base64": packet["audio"],
                        "audio_content_type": "audio/mpeg"
                    }))

                if packet.get("isFinal"):
                    await websocket.send(json.dumps({"type": "done"}))
                    break

    except Exception:
        logging.exception("WebSocket voice failed")
        try:
            await websocket.send(json.dumps({"error": "Voice streaming failed"}))
        except Exception:
            pass


@app.errorhandler(404)
async def not_found(error):
    return jsonify({"error": "Route not found"}), 404


@app.errorhandler(405)
async def method_not_allowed(error):
    return jsonify({"error": "Method not allowed"}), 405


if __name__ == "__main__":
    app.run()
