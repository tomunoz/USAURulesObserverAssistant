import os
import requests
import google.generativeai as genai
from bs4 import BeautifulSoup
from flask import Flask, jsonify, request
from flask_cors import CORS
import logging
import json # Import the json library for safer parsing

# --- App Setup and Configuration ---
app = Flask(__name__)
CORS(app)
logging.basicConfig(level=logging.INFO)

# --- Gemini API Configuration ---
try:
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise ValueError("API key not found. Please set the GOOGLE_API_KEY environment variable.")
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('gemini-2.5-flash')
    logging.info("Gemini model initialized successfully.")
except Exception as e:
    model = None
    logging.error(f"Error initializing Gemini: {e}")

# --- Rulebook Data Loading ---
RULES_URL = "https://usaultimate.org/rules/"

def get_rules_text():
    logging.info(f"Fetching rules from {RULES_URL}...")
    try:
        response = requests.get(RULES_URL, timeout=15)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')
        # Use the corrected class name
        rules_content = soup.find('ul', class_='main-rules')
        if rules_content:
            text = ' '.join(rules_content.get_text(separator=' ', strip=True).split())
            logging.info(f"Successfully scraped {len(text)} characters.")
            return text
        logging.warning("Could not find rules content div on the page.")
        return "Could not find rules content on the page."
    except requests.exceptions.RequestException as e:
        logging.error(f"Error fetching rules: {e}")
        return f"Error: Could not retrieve the rules from {RULES_URL}."

RULES_CONTEXT = get_rules_text()

@app.route('/ask', methods=['POST'])
def ask_question():
    if not model:
        return jsonify({"summary": "The Gemini AI model is not available.", "applicable_rules": []}), 503
    if "Error:" in RULES_CONTEXT:
         return jsonify({"summary": f"Could not load rules. Details: {RULES_CONTEXT}", "applicable_rules": []}), 500

    data = request.get_json()
    if not data or 'question' not in data:
        return jsonify({"error": "Invalid request."}), 400

    user_question = data['question']
    logging.info(f"Received question for Gemini: {user_question}")

    # === THIS IS THE UPDATED PROMPT ===
    # It now asks for an array of objects, each containing the rule number and its full text.
    prompt = f"""
        You are an expert on the rules of Ultimate Frisbee. Your task is to answer a user's question based *only* on the provided official rule text.

        **Official Rule Text:**
        ---
        {RULES_CONTEXT}
        ---

        **User's Question:** "{user_question}"

        **Instructions:**
        1.  Formulate a clear and concise summary that directly answers the question.
        2.  Identify the most relevant rules from the text that support your summary.
        3.  Format your response as a single, valid JSON object with two keys: "summary" (a string) and "applicable_rules" (an array of objects).
        4.  Each object in the "applicable_rules" array must have two keys: "rule" (a string for the rule number/name) and "text" (a string containing the full content of that rule).
        5.  If the answer cannot be found in the text, return a summary explaining that and an empty "applicable_rules" array.

        Example JSON response format:
        {{
            "summary": "A travel occurs if a player illegally changes their pivot foot or takes too many steps after catching the disc. Play stops and the disc is returned to the thrower at the spot of the infraction.",
            "applicable_rules": [
                {{
                    "rule": "18.B.4",
                    "text": "It is a travel violation if a thrower fails to keep all or part of the pivot in contact with a single spot on the playing field for the duration of the throwing motion."
                }},
                {{
                    "rule": "Section V.J",
                    "text": "A player must establish a pivot point after catching the disc. Taking excessive steps before or after establishing this pivot is a travel."
                }}
            ]
        }}
    """

    try:
        logging.info("Sending prompt to Gemini API...")
        response = model.generate_content(prompt)
        
        # Clean the response and parse it safely using the json library
        clean_response_text = response.text.strip().replace("```json", "").replace("```", "")
        response_data = json.loads(clean_response_text)
        
        logging.info("Successfully received and parsed response from Gemini.")
        return jsonify(response_data)

    except Exception as e:
        logging.error(f"Error communicating with Gemini or parsing its response: {e}")
        return jsonify({"summary": "An error occurred while getting an answer from the AI.", "applicable_rules": []}), 500

if __name__ == '__main__':
    app.run(port=5000)
