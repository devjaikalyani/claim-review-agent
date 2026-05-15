"""
LLM Utilities for Rite Audit System

Uses Anthropic Claude for both reasoning and vision (real multimodal — no OCR pre-step).
System prompts are cached with Anthropic prompt caching to reduce API costs.
"""
import base64
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

# Use an explicit path so the .env is found regardless of the working directory
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from anthropic import Anthropic

_HAIKU_MODEL  = "claude-haiku-4-5-20251001"   # receipt image OCR — fast, cheap
_SONNET_MODEL = "claude-sonnet-4-6"            # agents + voucher PDF — accurate

# ANTHROPIC_MODEL env var overrides the agent model only (for testing)
_DEFAULT_MODEL = os.getenv("ANTHROPIC_MODEL", _SONNET_MODEL)


def validate_api_key() -> None:
    """
    Validate ANTHROPIC_API_KEY at startup.
    Call this from app.py main() so missing keys surface immediately,
    not mid-pipeline during the first LLM call.
    """
    if not os.getenv("ANTHROPIC_API_KEY"):
        raise ValueError(
            "ANTHROPIC_API_KEY is not set. "
            "Add it to your .env file or environment before starting the app."
        )


_MAX_IMAGE_BYTES = 3 * 1024 * 1024   # 3 MB raw → ~4 MB base64, safely under Claude's 5 MB encoded limit


def _encode_file(file_path: str) -> tuple[str, str]:
    """
    Return (base64_data, media_type) for an image or PDF.
    Images larger than 4 MB are automatically compressed with PIL
    (quality reduction then resize) to stay within Claude's 5 MB limit.
    """
    ext = Path(file_path).suffix.lower()
    media_type_map = {
        ".jpg":  "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png":  "image/png",
        ".gif":  "image/gif",
        ".webp": "image/webp",
        ".pdf":  "application/pdf",
    }
    media_type = media_type_map.get(ext, "image/jpeg")

    # Read all bytes once — avoids relying on os.path.getsize which can be
    # unreliable for temp files on some Windows/Streamlit configurations.
    with open(file_path, "rb") as f:
        raw_bytes = f.read()

    # PDFs — send as-is; Claude accepts them natively
    if media_type == "application/pdf":
        return base64.standard_b64encode(raw_bytes).decode("utf-8"), media_type

    # Images within limit — send as-is
    if len(raw_bytes) <= _MAX_IMAGE_BYTES:
        return base64.standard_b64encode(raw_bytes).decode("utf-8"), media_type

    # Image exceeds limit — compress with PIL
    try:
        import io
        from PIL import Image

        img = Image.open(io.BytesIO(raw_bytes))   # open from memory — no second disk read
        if img.mode in ("RGBA", "P", "LA"):
            img = img.convert("RGB")

        # Step 1: quality reduction (original resolution)
        for quality in (82, 65, 50, 35, 20):
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=quality, optimize=True)
            if buf.tell() <= _MAX_IMAGE_BYTES:
                buf.seek(0)
                return base64.standard_b64encode(buf.read()).decode("utf-8"), "image/jpeg"

        # Step 2: resize + quality reduction
        w, h = img.size
        for scale in (0.75, 0.60, 0.50, 0.40, 0.30):
            resized = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
            for q in (70, 50, 35):
                buf = io.BytesIO()
                resized.save(buf, format="JPEG", quality=q, optimize=True)
                if buf.tell() <= _MAX_IMAGE_BYTES:
                    buf.seek(0)
                    return base64.standard_b64encode(buf.read()).decode("utf-8"), "image/jpeg"

        # Step 3: grayscale as last resort
        gray = img.convert("L")
        for q in (50, 30):
            buf = io.BytesIO()
            gray.save(buf, format="JPEG", quality=q, optimize=True)
            if buf.tell() <= _MAX_IMAGE_BYTES:
                buf.seek(0)
                return base64.standard_b64encode(buf.read()).decode("utf-8"), "image/jpeg"

        # All compression attempts failed — raise so the caller can skip this image
        buf.seek(0)
        final_size = buf.tell()
        raise ValueError(
            f"Image too large after all compression attempts "
            f"(~{final_size // 1024} KB). Please reduce the image size before uploading."
        )

    except ImportError:
        # PIL unavailable — cannot compress; raise a clear error
        raise ValueError(
            "Pillow library is required for large image compression. "
            "Run: pip install Pillow"
        )


def _parse_json_response(response: str) -> Dict[str, Any]:
    """Safely parse JSON from LLM response."""
    try:
        if "```json" in response:
            json_str = response.split("```json")[1].split("```")[0]
        elif "```" in response:
            json_str = response.split("```")[1].split("```")[0]
        else:
            json_str = response
        return json.loads(json_str.strip())
    except json.JSONDecodeError:
        return {"raw_text": response, "confidence": 0.5, "parse_error": True}


class ClaimReviewLLM:
    """
    LLM client using Anthropic Claude.

    - Text calls use cached system prompts (ephemeral cache_control) to cut costs
      on repeated extraction patterns.
    - Vision calls send actual file bytes — Claude sees the real image or PDF,
      not OCR-extracted text. This handles handwriting, low-contrast receipts,
      and structured table layouts that Tesseract drops.
    - PDFs are sent as document blocks (Claude reads them natively).
    """

    def __init__(
        self,
        model: str = None,
        temperature: float = 0.0,
        max_tokens: int = 1024,
    ):
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError(
                "ANTHROPIC_API_KEY environment variable required. "
                "Add it to your .env file."
            )
        self.model_name = model or os.getenv("ANTHROPIC_MODEL", _DEFAULT_MODEL)
        self.temperature = temperature
        self.max_tokens  = max_tokens
        self.client      = Anthropic(api_key=api_key)

    def invoke(self, prompt: str, system_prompt: str = None, max_tokens: int = None) -> str:
        """Text-only LLM call with optional cached system prompt."""
        kwargs: Dict[str, Any] = {
            "model":       self.model_name,
            "max_tokens":  max_tokens or self.max_tokens,
            "temperature": self.temperature,
            "messages":    [{"role": "user", "content": prompt}],
        }
        if system_prompt:
            # Cache the system prompt — same prompt is reused across many extraction
            # calls during a single pipeline run, so cache hits accumulate quickly.
            kwargs["system"] = [
                {
                    "type":          "text",
                    "text":          system_prompt,
                    "cache_control": {"type": "ephemeral"},
                }
            ]
        response = self.client.messages.create(**kwargs)
        return response.content[0].text

    def invoke_with_images(
        self,
        prompt: str,
        images: List[str],
        system_prompt: str = None,
        max_tokens: int = None,
    ) -> str:
        """
        Vision call — sends actual file bytes to Claude.

        Images are sent as image content blocks.
        PDFs are sent as document content blocks (Claude reads them natively).
        No Tesseract pre-processing step.
        """
        content: List[Dict[str, Any]] = []

        _skipped_indices: list[int] = []   # track skipped positions for the caller
        for idx, image_path in enumerate(images):
            if not os.path.exists(image_path):
                content.append({"type": "text", "text": f"[File not found: {image_path}]"})
                _skipped_indices.append(idx)
                continue

            try:
                data, media_type = _encode_file(image_path)
            except ValueError as enc_err:
                # Image too large or uncompressible — skip with placeholder
                content.append({"type": "text", "text": f"[{enc_err}]"})
                _skipped_indices.append(idx)
                continue

            if media_type == "application/pdf":
                content.append({
                    "type": "document",
                    "source": {
                        "type":       "base64",
                        "media_type": "application/pdf",
                        "data":       data,
                    },
                })
            else:
                content.append({
                    "type": "image",
                    "source": {
                        "type":       "base64",
                        "media_type": media_type,
                        "data":       data,
                    },
                })

        content.append({"type": "text", "text": prompt})

        kwargs: Dict[str, Any] = {
            "model":       self.model_name,
            "max_tokens":  max_tokens or self.max_tokens,
            "temperature": self.temperature,
            "messages":    [{"role": "user", "content": content}],
        }
        if system_prompt:
            kwargs["system"] = [
                {
                    "type":          "text",
                    "text":          system_prompt,
                    "cache_control": {"type": "ephemeral"},
                }
            ]
        response = self.client.messages.create(**kwargs)
        return response.content[0].text

    def extract_receipt_data(self, image_path: str) -> Dict[str, Any]:
        system_prompt = """You are an expert at extracting data from receipts and bills.
Analyse the provided receipt image or document and extract information in JSON format:
{
    "vendor_name": "Name of the business/vendor",
    "date": "Date on receipt (YYYY-MM-DD format)",
    "total_amount": numeric value,
    "items": [{"description": "item name", "amount": numeric}],
    "category": "food|fuel|transport|toll|other",
    "payment_method": "cash|card|upi|other",
    "receipt_number": "receipt/invoice number if visible",
    "confidence": 0.0-1.0 confidence score
}
If any field is not visible or unclear, use null.
Always respond with valid JSON only."""
        response = self.invoke_with_images(
            prompt="Extract all information from this receipt/bill:",
            images=[image_path],
            system_prompt=system_prompt,
        )
        return _parse_json_response(response)

    def extract_fasttag_data(self, image_path: str) -> Dict[str, Any]:
        system_prompt = """You are an expert at extracting toll/FASTag transaction data.
Analyse the provided FASTag screenshot or document and extract in JSON format:
{
    "transactions": [
        {
            "date": "YYYY-MM-DD",
            "time": "HH:MM",
            "toll_plaza": "Name of toll plaza",
            "amount": numeric,
            "vehicle_number": "vehicle registration number",
            "transaction_id": "transaction reference"
        }
    ],
    "total_amount": numeric,
    "period_start": "YYYY-MM-DD",
    "period_end": "YYYY-MM-DD",
    "confidence": 0.0-1.0
}
Always respond with valid JSON only."""
        response = self.invoke_with_images(
            prompt="Extract all FASTag/toll transaction details:",
            images=[image_path],
            system_prompt=system_prompt,
        )
        return _parse_json_response(response)

    def extract_unolo_distance(self, image_path: str) -> Dict[str, Any]:
        system_prompt = """You are an expert at extracting GPS tracking/distance data.
Analyse the provided tracking app screenshot or document and extract in JSON format:
{
    "total_distance_km": numeric,
    "trips": [
        {
            "date": "YYYY-MM-DD",
            "distance_km": numeric,
            "start_location": "starting point",
            "end_location": "ending point",
            "duration_minutes": numeric
        }
    ],
    "period_start": "YYYY-MM-DD",
    "period_end": "YYYY-MM-DD",
    "employee_name": "name if visible",
    "confidence": 0.0-1.0
}
Always respond with valid JSON only."""
        response = self.invoke_with_images(
            prompt="Extract distance tracking data from this GPS/Unolo screenshot:",
            images=[image_path],
            system_prompt=system_prompt,
        )
        return _parse_json_response(response)


# Global singletons — created on first use, not at import time
_llm_instance:         Optional[ClaimReviewLLM] = None  # Sonnet — agents
_vision_llm_instance:  Optional[ClaimReviewLLM] = None  # Haiku  — receipt image OCR
_voucher_llm_instance: Optional[ClaimReviewLLM] = None  # Sonnet — PDF voucher extraction


def get_llm() -> ClaimReviewLLM:
    """Sonnet — agent pipeline (admin_judgment, etc.)."""
    global _llm_instance
    if _llm_instance is None:
        _llm_instance = ClaimReviewLLM(model=_DEFAULT_MODEL)
    return _llm_instance


def get_vision_llm() -> ClaimReviewLLM:
    """Haiku — receipt image OCR. Fast and cheap for structured extraction."""
    global _vision_llm_instance
    if _vision_llm_instance is None:
        _vision_llm_instance = ClaimReviewLLM(model=_HAIKU_MODEL)
    return _vision_llm_instance


def get_voucher_llm() -> ClaimReviewLLM:
    """Sonnet — expense voucher PDF extraction. Needs column-level accuracy."""
    global _voucher_llm_instance
    if _voucher_llm_instance is None:
        _voucher_llm_instance = ClaimReviewLLM(model=_SONNET_MODEL)
    return _voucher_llm_instance
