from flask import Flask, request, jsonify
import os
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
API_KEY = os.getenv("API_KEY")

@app.route("/", methods=["GET"])
def home():
    return jsonify({"message": "AI Agent is running!"})

@app.route("/execute", methods=["POST"])
def execute():
    auth_header = request.headers.get("Authorization")
    if auth_header != f"Bearer {API_KEY}":
        return jsonify({"error": "Unauthorized"}), 401
    data = request.json
    # Add agent logic here
    return jsonify({"status": "Success", "received": data})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
