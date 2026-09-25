"""Compare local OCR models on manually labelled images; never access the website."""
import argparse
import json
import re
import time
from pathlib import Path

from thsr_ticket.captcha import CaptchaReader


def load_samples(manifest):
    manifest = Path(manifest)
    entries = json.loads(manifest.read_text(encoding='utf-8-sig'))
    if not isinstance(entries, list) or not entries:
        raise ValueError('標註檔必須是非空 JSON 陣列。')
    samples = []
    seen = set()
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != {'image', 'label'}:
            raise ValueError('每筆標註只能包含 image 與 label。')
        label = entry['label']
        if not isinstance(label, str) or not re.fullmatch(r'[A-Za-z0-9]{4}', label):
            raise ValueError('label 必須是人工核對的四碼英數字。')
        if not isinstance(entry['image'], str) or not entry['image']:
            raise ValueError('image 必須是圖片路徑。')
        path = (manifest.parent / entry['image']).resolve()
        if path in seen:
            raise ValueError('標註檔包含重複的圖片路徑。')
        seen.add(path)
        samples.append((path.read_bytes(), label.upper()))
    return samples


def evaluate(samples, reader, clock=time.perf_counter):
    if not reader.prepare():
        raise RuntimeError('OCR 模型載入失敗，無法評估。')
    correct = wrong = abstained = 0
    elapsed = 0.0
    for image, label in samples:
        start = clock()
        guess = reader.recognize(image)
        elapsed += clock() - start
        if reader.unavailable:
            raise RuntimeError('OCR 推論失敗，停止評估，避免把故障當成辨識率。')
        if guess is None:
            abstained += 1
        elif guess.text == label:
            correct += 1
        else:
            wrong += 1
    total = len(samples)
    if not total:
        raise ValueError('至少需要一張標註圖片。')
    accepted = correct + wrong
    return {
        'samples': total, 'correct': correct, 'wrong': wrong, 'abstained': abstained,
        'exact_match_rate': correct / total,
        'coverage': accepted / total,
        'accepted_accuracy': correct / accepted if accepted else None,
        'mean_inference_ms': elapsed * 1000 / total,
    }


def main():
    parser = argparse.ArgumentParser(description='離線比較 standard 與 beta OCR，不連線或訂位')
    parser.add_argument('manifest', type=Path, help='人工標註 JSON 檔')
    parser.add_argument('--min-score', type=float, default=0.5)
    args = parser.parse_args()
    try:
        samples = load_samples(args.manifest)
        reports = {}
        for model in ('standard', 'beta'):
            reader = CaptchaReader(model=model, min_score=args.min_score)
            reports[model] = evaluate(samples, reader)
            del reader
        print(json.dumps({'min_score': args.min_score, 'models': reports}, indent=2, allow_nan=False))
    except (ValueError, OSError, RuntimeError) as exc:
        print(f'評估失敗：{exc}')
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
