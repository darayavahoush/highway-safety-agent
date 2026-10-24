"""
Automatic Number Plate Recognition (ANPR) & Multi-Frame Voting Pipeline.
Optimized for Indian High Security Registration Plates (HSRP) on highway corridors.

Features:
- Bumper region localization (bottom 40% of vehicle bounding box).
- Morphological plate candidate isolation (Sobel gradient + Aspect Ratio 2.2-5.5).
- Tesseract OCR engine with alphanumeric character whitelist.
- Indian RTO Regex normalization (State + District Code + Series + Number).
- Multi-frame temporal voting across track lifetime for noise immunity.
- Optional hotlist cross-referencing (empty unless a real list is configured).

Honesty rules (do not weaken):
- A plate that could not be read is reported as NO READ. A plate is NEVER invented.
- Confidence comes from the OCR engine's own per-read score, scaled by how consistently
  the same text was read across frames. It is not a constant.
- The hotlist is empty by default. Demo entries load only when ANPR_DEMO_HOTLIST=1, and
  such hits are marked simulated.
"""

from collections import Counter, defaultdict
import json
import os
import re
import time
from typing import Dict, List, Optional, Tuple, Any
import cv2
import numpy as np
import pytesseract
from pytesseract import Output

# Set Tesseract binary path
if os.path.isfile("/opt/homebrew/bin/tesseract"):
    pytesseract.pytesseract.tesseract_cmd = "/opt/homebrew/bin/tesseract"

# Standard Indian State Codes
INDIAN_STATES = {
    "AP": "Andhra Pradesh",
    "TS": "Telangana",
    "KA": "Karnataka",
    "TN": "Tamil Nadu",
    "MH": "Maharashtra",
    "DL": "Delhi",
    "UP": "Uttar Pradesh",
    "GJ": "Gujarat",
    "HR": "Haryana",
    "WB": "West Bengal",
}

# AP RTO District Codes on NH-16 / NH-44
AP_RTO_DISTRICTS = {
    "05": "Kakinada",
    "07": "Guntur",
    "16": "Vijayawada / Amaravati (NTR District)",
    "21": "Kurnool",
    "26": "Nellore",
    "31": "Visakhapatnam",
    "39": "Tirupati",
}

# Demo-only entries. They are NOT real police data and load only when ANPR_DEMO_HOTLIST=1.
_DEMO_HOTLIST = {
    "AP16TX4921": {"reason": "DEMO ONLY: wanted vehicle (simulated)", "flag": "CRITICAL_WARRANT", "simulated": True},
    "AP07AB1024": {"reason": "DEMO ONLY: stolen vehicle report (simulated)", "flag": "STOLEN_VEHICLE", "simulated": True},
    "TS09EQ8820": {"reason": "DEMO ONLY: repeat speed violator (simulated)", "flag": "HIGH_SPEED_OFFENDER", "simulated": True},
}


def load_hotlist() -> Dict[str, Dict[str, Any]]:
    """Hotlist from ANPR_HOTLIST_PATH (JSON: {"AP16XX1234": {"reason": ..., "flag": ...}}).
    Empty by default. Only an authorised, current list should ever be configured here."""
    hot: Dict[str, Dict[str, Any]] = {}
    if os.environ.get("ANPR_DEMO_HOTLIST") == "1":
        hot.update(_DEMO_HOTLIST)
    path = os.environ.get("ANPR_HOTLIST_PATH")
    if path and os.path.isfile(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                hot.update({k.replace(" ", "").upper(): v for k, v in json.load(f).items()})
        except (OSError, ValueError):
            pass
    return hot


HOTLIST_PLATES = load_hotlist()

INDIAN_PLATE_REGEX = re.compile(
    r"([A-Z]{2})\s*([0-9]{1,2})\s*([A-Z]{1,3})\s*([0-9]{3,4})"
)


class ANPRPipeline:
    def __init__(self, tesseract_cmd: Optional[str] = None):
        if tesseract_cmd and os.path.isfile(tesseract_cmd):
            pytesseract.pytesseract.tesseract_cmd = tesseract_cmd
        # Multi-frame voting bank: track_id -> List[detected_plate_string]
        self._track_votes: Dict[int, List[str]] = defaultdict(list)
        self._track_confidences: Dict[int, List[float]] = defaultdict(list)
        self._track_frames: Dict[int, int] = defaultdict(int)  # frames where a read was attempted

    def extract_plate_region(self, vehicle_crop: np.ndarray) -> List[np.ndarray]:
        """
        Extracts candidate license plate sub-crops from a vehicle crop.
        Focuses on the lower bumper area where plates are physically mounted.
        """
        h, w = vehicle_crop.shape[:2]
        if h < 20 or w < 30:
            return []

        # Slice bottom 45% (bumper zone)
        bumper_y = int(h * 0.55)
        bumper = vehicle_crop[bumper_y:h, 0:w]
        bh, bw = bumper.shape[:2]

        candidates = []
        # Candidate 1: Full bumper region (scaled for OCR)
        candidates.append(bumper)

        # Candidate 2: Morphological rectangular plate isolation
        gray = cv2.cvtColor(bumper, cv2.COLOR_BGR2GRAY)
        blur = cv2.GaussianBlur(gray, (5, 5), 0)
        grad_x = cv2.Sobel(blur, cv2.CV_16S, 1, 0, ksize=3)
        abs_grad_x = cv2.convertScaleAbs(grad_x)
        _, thresh = cv2.threshold(abs_grad_x, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

        # Morphological close with horizontal rectangle kernel (plate aspect ratio)
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (17, 3))
        closed = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)

        contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for c in contours:
            cx, cy, cw, ch = cv2.boundingRect(c)
            if ch == 0:
                continue
            aspect = float(cw) / float(ch)
            area = cw * ch
            # Standard plate aspect ratio: 2.2 to 5.5, minimum area
            if 2.0 <= aspect <= 6.0 and area > (bw * bh * 0.04):
                pad_x = int(cw * 0.05)
                pad_y = int(ch * 0.05)
                px1 = max(0, cx - pad_x)
                py1 = max(0, cy - pad_y)
                px2 = min(bw, cx + cw + pad_x)
                py2 = min(bh, cy + ch + pad_y)
                plate_crop = bumper[py1:py2, px1:px2]
                candidates.append(plate_crop)

        return candidates

    def preprocess_for_ocr(self, img: np.ndarray) -> np.ndarray:
        """Optimizes contrast and removes glare/noise for Tesseract OCR."""
        if len(img.shape) == 3:
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        else:
            gray = img

        # Upscale small plate crops to minimum height 60px for OCR readability
        gh, gw = gray.shape[:2]
        if gh < 60:
            scale = 60.0 / max(1.0, gh)
            gray = cv2.resize(gray, (int(gw * scale), 60), interpolation=cv2.INTER_CUBIC)

        # CLAHE (Contrast Limited Adaptive Histogram Equalization)
        clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8))
        contrast = clahe.apply(gray)

        # Bilateral filter for edge-preserving denoising
        denoised = cv2.bilateralFilter(contrast, 9, 75, 75)

        # Otsu thresholding
        _, binary = cv2.threshold(denoised, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        return binary

    def parse_plate_text(self, raw_text: str) -> Optional[Dict[str, Any]]:
        """
        Cleans and normalizes OCR text matching Indian HSRP format.
        Example: 'AP 16 TX 4921' -> normalized plate dict.
        """
        # Uppercase, alphanumeric only
        cleaned = re.sub(r"[^A-Z0-9]", "", raw_text.upper())
        if len(cleaned) < 6:
            return None

        # Look for Indian Plate pattern
        m = INDIAN_PLATE_REGEX.search(cleaned)
        if not m:
            # Fallback heuristic: check if starts with known state code
            for state in INDIAN_STATES:
                if cleaned.startswith(state) and len(cleaned) >= 8:
                    state_code = state
                    rest = cleaned[len(state):]
                    return {
                        "loose": True,  # state prefix only; the rest of the pattern did not match
                        "text": f"{state_code} {rest[:2]} {rest[2:]}".strip(),
                        "raw": cleaned,
                        "state_code": state_code,
                        "state_name": INDIAN_STATES[state_code],
                    }
            return None

        state, dist, series, num = m.groups()
        formatted_plate = f"{state} {dist} {series} {num}"
        clean_key = f"{state}{dist}{series}{num}"

        state_name = INDIAN_STATES.get(state, "Other State")
        district_name = AP_RTO_DISTRICTS.get(dist, f"RTO Zone {dist}") if state == "AP" else f"RTO {dist}"

        watch_info = HOTLIST_PLATES.get(clean_key)

        return {
            "text": formatted_plate,
            "raw": clean_key,
            "state_code": state,
            "state_name": state_name,
            "district_code": dist,
            "district_name": district_name,
            "hotlist": watch_info,
        }

    def _read_candidate(self, cand: np.ndarray, config: str) -> Tuple[Optional[Dict[str, Any]], float]:
        """OCR one candidate crop. Returns (parsed plate or None, OCR confidence 0..1)."""
        proc = self.preprocess_for_ocr(cand)
        data = pytesseract.image_to_data(proc, config=config, output_type=Output.DICT)
        words, confs = [], []
        for txt, c in zip(data.get("text", []), data.get("conf", [])):
            try:
                c = float(c)
            except (TypeError, ValueError):
                continue
            if txt and txt.strip() and c >= 0:
                words.append(txt.strip())
                confs.append(c)
        parsed = self.parse_plate_text("".join(words))
        if not parsed or not confs:
            return None, 0.0
        conf = sum(confs) / len(confs) / 100.0
        return parsed, (conf * 0.5 if parsed.get("loose") else conf)

    def process_vehicle_crop(
        self,
        vehicle_crop: np.ndarray,
        track_id: int,
    ) -> Dict[str, Any]:
        """
        Runs ANPR on a vehicle crop with multi-frame voting accumulation.

        Always returns a dict. When nothing could be read, "readable" is False and the text
        is "NO READ": the caller must show that, never a made-up registration.
        """
        candidates = self.extract_plate_region(vehicle_crop)
        best_plate, best_conf = None, 0.0

        config = (
            "--oem 3 --psm 7 "
            "-c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
        )

        for cand in candidates:
            try:
                parsed, conf = self._read_candidate(cand, config)
            except Exception:
                continue  # OCR unavailable or failed on this crop: counts as no read
            if parsed:
                best_plate, best_conf = parsed, conf
                break

        self._track_frames[track_id] += 1
        if best_plate:
            self._track_votes[track_id].append(best_plate["text"])
            self._track_confidences[track_id].append(best_conf)

        votes_list = self._track_votes[track_id]
        frames = self._track_frames[track_id]
        if not votes_list:
            return {"text": "NO READ", "readable": False, "confidence": 0.0,
                    "votes": 0, "frames": frames, "state": None, "district": None, "hotlist": None}

        most_common_plate, vote_count = Counter(votes_list).most_common(1)[0]
        confs = [c for t, c in zip(votes_list, self._track_confidences[track_id]) if t == most_common_plate]
        # Measured OCR confidence of the winning reads, scaled by how consistently it was read.
        confidence = round((sum(confs) / len(confs)) * (vote_count / len(votes_list)), 2)

        plate_meta = self.parse_plate_text(most_common_plate) or {}
        return {
            "text": most_common_plate,
            "readable": True,
            "confidence": confidence,
            "votes": vote_count,
            "frames": frames,
            "state": plate_meta.get("state_name"),
            "district": plate_meta.get("district_name"),
            "hotlist": plate_meta.get("hotlist"),
        }

    def reset_track(self, track_id: int):
        self._track_votes.pop(track_id, None)
        self._track_confidences.pop(track_id, None)
        self._track_frames.pop(track_id, None)

    def reset(self):
        self._track_votes.clear()
        self._track_confidences.clear()
        self._track_frames.clear()


# Singleton ANPR pipeline
anpr_pipeline = ANPRPipeline()
