"""Optional local OCR. Scores are model outputs, not measured THSR accuracy."""
import math
import re
from dataclasses import dataclass
from typing import Any, Callable, Optional


@dataclass(frozen=True)
class CaptchaGuess:
    text: str
    score: float


def decode_prediction(result: dict) -> Optional[CaptchaGuess]:
    """Decode ddddocr 1.6.1's CTC output, ignoring blank-frame confidence."""
    charset = result['charset']
    rows = result['probabilities']
    if not rows:
        return None
    # The model uses either (time, 1, classes) or (1, time, classes).
    if len(rows) == 1 and isinstance(rows[0][0], list):
        rows = rows[0]
    elif isinstance(rows[0][0], list):
        rows = [row[0] for row in rows]
    chars, scores = [], []
    previous = None
    for row in rows:
        if len(row) != len(charset) or not all(math.isfinite(p) and 0 <= p <= 1 for p in row):
            return None
        # THSR uses uppercase codes; merge case variants before choosing a character.
        grouped = {}
        for char, probability in zip(charset, row):
            key = char.upper() if re.fullmatch(r'[a-z]', char) else char
            grouped[key] = grouped.get(key, 0.0) + probability
        char = max(grouped, key=grouped.__getitem__)
        if char:
            if char != previous:
                chars.append(char)
                scores.append(grouped[char])
            else:
                scores[-1] = max(scores[-1], grouped[char])
        previous = char
    text = ''.join(chars)
    if not re.fullmatch(r'[A-Za-z0-9]{4}', text):
        return None
    return CaptchaGuess(text.upper(), min(scores))


def _load_engine(model: str = 'standard') -> Any:
    from ddddocr import DdddOcr  # Optional dependency; manual mode never imports it.
    return DdddOcr(show_ad=False, beta=model == 'beta')


class CaptchaReader:
    def __init__(self, min_score: float = 0.5, engine_factory: Optional[Callable] = None,
                 model: str = 'standard') -> None:
        if not 0 <= min_score <= 1:
            raise ValueError('OCR 分數門檻必須介於 0 與 1。')
        if model not in ('standard', 'beta'):
            raise ValueError('OCR 模型必須為 standard 或 beta。')
        self.min_score = min_score
        self.engine_factory = engine_factory if engine_factory is not None else lambda: _load_engine(model)
        self.engine = None
        self.unavailable = False

    def prepare(self) -> bool:
        """Load once before a scheduled run; no image or website request required."""
        if self.unavailable:
            return False
        try:
            if self.engine is None:
                self.engine = self.engine_factory()
            return True
        except Exception:
            self.unavailable = True
            return False

    def recognize(self, image: bytes) -> Optional[CaptchaGuess]:
        if not self.prepare():
            return None
        try:
            guess = decode_prediction(self.engine.classification(image, probability=True))
            return guess if guess and guess.score >= self.min_score else None
        except Exception:  # Optional native runtime failures must preserve manual entry.
            self.unavailable = True
            return None
