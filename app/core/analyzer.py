"""Gemini vision analyzer - compares photos to definitions."""

import base64
import json
import time
from typing import Any, Optional

import aiohttp

from app.config import settings
from app.core.models import CheckResult, ToSortItem, SpotStatus
from app.core.voices import get_voice_prompt
from app.core.memory import build_memory_context, SpotMemory


GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta"


class AnalyzerError(Exception):
    """Raised when analysis fails."""
    pass


class SpotAnalyzer:
    """Analyzes spot images using Gemini vision."""
    
    def __init__(self):
        self.api_key = settings.gemini_api_key
        self.model = settings.gemini_model
    
    async def analyze(
        self,
        image_bytes: bytes,
        spot_name: str,
        definition: str,
        voice: str,
        memory: SpotMemory,
        custom_voice_prompt: str = None,
    ) -> dict[str, Any]:
        """
        Analyze a spot image against the definition.
        
        Returns dict with:
        - status: "sorted" or "needs_attention"
        - to_sort: list of items
        - looking_good: list of items
        - notes: dict with main/pattern/encouragement
        """
        if not self.api_key:
            raise AnalyzerError("Gemini API key not configured")
        
        start_time = time.time()
        
        # Build prompt
        voice_prompt = get_voice_prompt(voice, custom_voice_prompt)
        memory_context = build_memory_context(memory)
        prompt = self._build_prompt(spot_name, definition, voice_prompt, memory_context)
        
        # Encode image
        image_b64 = base64.b64encode(image_bytes).decode("utf-8")
        
        # Call API
        url = f"{GEMINI_API_BASE}/models/{self.model}:generateContent"
        headers = {
            "Content-Type": "application/json",
            "x-goog-api-key": self.api_key,
        }
        payload = {
            "contents": [{
                "parts": [
                    {"text": prompt},
                    {"inline_data": {"mime_type": "image/jpeg", "data": image_b64}}
                ]
            }],
            "generationConfig": {
                "temperature": 0.4,
                "topK": 32,
                "topP": 1,
                "maxOutputTokens": 2048,
            }
        }
        
        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(url, headers=headers, json=payload, timeout=90) as resp:
                    if resp.status == 429:
                        raise AnalyzerError("Gemini API quota exceeded. Try again later.")
                    if resp.status != 200:
                        text = await resp.text()
                        raise AnalyzerError(f"Gemini API error {resp.status}: {text[:200]}")
                    
                    data = await resp.json()
            except aiohttp.ClientError as e:
                raise AnalyzerError(f"Network error: {e}")
        
        response_time = time.time() - start_time
        
        # Parse response
        result = self._parse_response(data)
        result["api_response_time"] = response_time
        result["image_size"] = len(image_bytes)
        
        return result
    
    def _build_prompt(
        self,
        spot_name: str,
        definition: str,
        voice_prompt: str,
        memory_context: str,
    ) -> str:
        """Build the analysis prompt."""
        return f'''You are checking if "{spot_name}" matches its Ready State.

THE USER'S DEFINITION OF READY STATE:
{definition}

HISTORY (from previous checks):
{memory_context}

YOUR VOICE (how to communicate):
{voice_prompt}

TASK:
Look at the photo and compare it to the user's definition above.

1. List what's "To sort" - things that DON'T match the definition
2. List what's "Looking good" - things that DO match the definition
3. Write brief notes in your voice
4. If the history mentions patterns, you can reference them

RULES:
- Be SPECIFIC about what you see. "Coffee mug on left side of desk" not "items present"
- Reference the user's OWN WORDS from their definition
- If they said "no dishes" and you see dishes, call that out specifically
- Keep notes to 2-3 sentences MAX
- NEVER say "AI" or mention being an AI
- NEVER use generic phrases like "Let's get organized!"
- NEVER use the word "deviation" or "violation" or "spec"

RETURN THIS EXACT JSON FORMAT:
{{
    "status": "sorted" or "needs_attention",
    "to_sort": [
        {{"item": "specific item name", "location": "where it is"}}
    ],
    "looking_good": ["item 1", "item 2"],
    "notes": {{
        "main": "Your main observation in 1-2 sentences",
        "pattern": "Any pattern from history worth mentioning, or null",
        "encouragement": "Something encouraging if appropriate, or null"
    }}
}}

IMPORTANT:
- If EVERYTHING matches the definition, return status "sorted" with empty to_sort
- If ANYTHING doesn't match, return status "needs_attention"
- Return ONLY valid JSON, no markdown, no extra text'''

    def _parse_response(self, data: dict[str, Any]) -> dict[str, Any]:
        """Parse Gemini response."""
        candidates = data.get("candidates", [])
        if not candidates:
            raise AnalyzerError("No response from Gemini")
        
        parts = candidates[0].get("content", {}).get("parts", [])
        text = None
        for part in parts:
            if "text" in part:
                text = part["text"]
                break
        
        if not text:
            raise AnalyzerError("No text in Gemini response")
        
        # Clean markdown
        text = text.strip()
        if text.startswith("```json"):
            text = text[7:]
        if text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        
        try:
            parsed = json.loads(text.strip())
        except json.JSONDecodeError as e:
            raise AnalyzerError(f"Invalid JSON from Gemini: {e}")
        
        return self._validate_response(parsed)
    
    def _validate_response(self, data: dict[str, Any]) -> dict[str, Any]:
        """Validate and normalize response."""
        # Status
        status = data.get("status", "needs_attention")
        if status not in ("sorted", "needs_attention"):
            status = "needs_attention"
        
        # To sort items
        to_sort_raw = data.get("to_sort", [])
        to_sort = []
        for item in to_sort_raw:
            if isinstance(item, dict):
                item.pop("recurring", None)  # We calculate this ourselves
                if item.get("item"):
                    to_sort.append({
                        "item": str(item["item"]).strip(),
                        "location": str(item.get("location", "")) or None,
                    })
            elif isinstance(item, str) and item.strip():
                to_sort.append({"item": item.strip(), "location": None})
        
        # Looking good items
        looking_good_raw = data.get("looking_good", [])
        looking_good = []
        for item in looking_good_raw:
            if isinstance(item, str) and item.strip():
                looking_good.append(item.strip())
            elif isinstance(item, dict) and item.get("item"):
                looking_good.append(str(item["item"]).strip())
        
        # Notes
        notes_raw = data.get("notes", {})
        notes = {
            "main": notes_raw.get("main") or None,
            "pattern": notes_raw.get("pattern") or None,
            "encouragement": notes_raw.get("encouragement") or None,
        }
        
        return {
            "status": status,
            "to_sort": to_sort,
            "looking_good": looking_good,
            "notes": notes,
        }


async def validate_api_key(api_key: str) -> bool:
    """Check if API key is valid."""
    url = f"{GEMINI_API_BASE}/models/gemini-2.0-flash"
    headers = {"x-goog-api-key": api_key}
    
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url, headers=headers, timeout=10) as resp:
                return resp.status == 200
        except Exception:
            return False
