import os
import requests
import json
from typing import List, Optional
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from dotenv import load_dotenv
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()

# Get API key from environment variables
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY environment variable not found. Please set it in your .env file.")

# API endpoint for Gemini
API_URL = "https://generativelanguage.googleapis.com/v1beta"
MODEL = "gemini-2.0-flash"  # This should match the model in the curl example

app = FastAPI(title="Intelligent Email Writer API")

# Request schema
class EmailRequest(BaseModel):
    category: str
    recipient: str
    subject: str
    tone: str
    language: str
    urgency_level: Optional[str] = "Biasa"
    points: List[str]
    example_email: Optional[str] = None

# Function to build text prompt from user input data
def build_prompt(body: EmailRequest) -> str:
    """
    Generates a text prompt based on data provided by the user.

    This function builds a prompt structure containing:
    - Email language and tone.
    - Recipient and subject information.
    - Category and urgency level.
    - Email content points to be included.
    - (Optional) Previous email example as reference.

    This prompt will be used as input for LLMs like Gemini.
    """
    lines = [
        f"Tolong buatkan email dalam {body.language.lower()} yang {body.tone.lower()}",
        f"kepada {body.recipient}.",
        f"Subjek: {body.subject}.",
        f"Kategori email: {body.category}.",
        f"Tingkat urgensi: {body.urgency_level}.",
        "",
        "Isi email harus mencakup poin-poin berikut:",
    ]
    for point in body.points:
        lines.append(f"- {point}")
    if body.example_email:
        lines += ["", "Contoh email sebelumnya:", body.example_email]
    lines.append("")
    lines.append("Buat email yang profesional, jelas, dan padat.")
    lines.append("Tolong berikan hasil akhirnya saja tanpa penjelasan tambahan.")
    
    # Add language-specific instructions
    if "inggris" in body.language.lower():
        lines.append("Format email dengan struktur yang baik seperti salutation, pembuka, isi, penutup, dan signature.")
    else:
        lines.append("Format email dengan struktur yang baik seperti salam pembuka, pembuka, isi, penutup, dan tanda tangan.")
    
    return "\n".join(lines)

@app.post("/generate/")
async def generate_email(req: EmailRequest):
    try:
        # Convert request to text prompt using build_prompt function
        prompt_text = build_prompt(req)
        
        # Prepare the request payload for Gemini API
        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": prompt_text}
                    ]
                }
            ],
            "generationConfig": {
                "temperature": 0.7,
                "topP": 0.95,
                "topK": 64,
                "maxOutputTokens": 1024,
            }
        }
        
        # Construct the full API URL with the model name
        request_url = f"{API_URL}/models/{MODEL}:generateContent?key={GEMINI_API_KEY}"
        
        # Log what we're doing (without exposing the full API key)
        logger.info(f"Sending request to Gemini API model: {MODEL}")
        
        # Send the POST request to the Gemini API
        response = requests.post(
            request_url,
            headers={"Content-Type": "application/json"},
            data=json.dumps(payload),
            timeout=30
        )
        
        # Check if the request was successful
        response.raise_for_status()
        
        # Parse the JSON response
        api_response = response.json()
        
        # Extract the generated text from the response
        if "candidates" in api_response and len(api_response["candidates"]) > 0:
            candidate = api_response["candidates"][0]
            if "content" in candidate and "parts" in candidate["content"]:
                parts = candidate["content"]["parts"]
                if len(parts) > 0 and "text" in parts[0]:
                    generated = parts[0]["text"]
                    return {"generated_email": generated}
        
        # If we couldn't extract text using the expected structure
        logger.error(f"Unexpected response structure: {api_response}")
        raise HTTPException(status_code=500, detail="Could not extract generated text from API response")
        
    except requests.exceptions.HTTPError as http_err:
        error_detail = f"HTTP error: {http_err}. Response: {http_err.response.text if hasattr(http_err, 'response') else 'No response'}"
        logger.error(error_detail)
        raise HTTPException(status_code=500, detail=error_detail)
    
    except Exception as e:
        logger.error(f"Error generating email: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error generating email: {str(e)}")

# Health check and debug endpoint
@app.get("/health")
async def health_check():
    try:
        # Make a simple request to list models (to verify API key works)
        list_models_url = f"{API_URL}/models?key={GEMINI_API_KEY}"
        response = requests.get(list_models_url)
        response.raise_for_status()
        models_data = response.json()
        
        # Extract just the model names for cleaner output
        model_names = []
        if "models" in models_data:
            for model in models_data["models"]:
                if "name" in model:
                    model_names.append(model["name"].split("/")[-1])
        
        return {
            "status": "healthy",
            "available_models": model_names
        }
    except Exception as e:
        return {
            "status": "error",
            "message": str(e)
        }
