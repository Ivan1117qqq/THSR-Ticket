"""Local manual labelling and model comparison; no website or booking actions."""
import hashlib
import json
import re
import math
import os
from pathlib import Path

from PySide6.QtCore import Property, Slot, QUrl, Signal
from PySide6.QtWidgets import QFileDialog
from thsr_ticket.backup import safe_path, sources
from thsr_ticket.captcha import CaptchaReader
from thsr_ticket.desktop.jobs import LocalJob
from thsr_ticket.ocr_benchmark import load_samples, evaluate
from thsr_ticket.run_records import atomic_json, timestamp
from thsr_ticket.scan_report import check_cancel
from thsr_ticket.version import VERSION
from thsr_ticket.storage_errors import StorageError


class OcrLab(LocalJob):
    sampleChanged = Signal()

    def __init__(self, context, parent=None):
        super().__init__(context, parent)
        self.changed.connect(self.sampleChanged.emit)
        self._folder = None
        self._images, self._labels = [], {}
        self._index = 0
        self._report = {}
        self._message = '選擇本機圖片資料夾人工標註，再比較兩套模型。不連線、不送出訂位。'

    @Property('QVariantMap', notify=sampleChanged)
    def sample(self):
        if not self._images:
            return {}
        path = self._images[self._index]
        return {'url': QUrl.fromLocalFile(str(path)).toString(), 'name': path.name,
                'label': self._labels.get(path.name, ''), 'index': self._index + 1,
                'count': len(self._images), 'labelled': len(self._labels)}

    @Slot()
    def chooseFolder(self):
        if self.context()['running']:
            return
        value = QFileDialog.getExistingDirectory(None, '選擇人工標註圖片資料夾')
        if not value:
            return
        folder = Path(value)

        def scan():
            safe_path(folder)
            paths = []
            for path in folder.iterdir():
                check_cancel(self._cancel)
                if path.suffix.lower() in ('.png', '.jpg', '.jpeg', '.bmp'):
                    safe_path(path)
                    if not path.is_file() or path.stat().st_size > 5 * 1024 * 1024 or len(paths) >= 5000:
                        raise ValueError('圖片超出限制。')
                    paths.append(path)
            labels = {}
            manifest = safe_path(folder / 'labels.json')
            if manifest.exists():
                load_samples(manifest, self._cancel)
                entries = json.loads(manifest.read_text(encoding='utf-8-sig'))
                # This editor manages top-level files only; do not rewrite another manifest layout.
                if any(Path(item['image']).name != item['image'] for item in entries):
                    raise ValueError('此標註檔使用子資料夾，請直接載入評估，避免改寫。')
                labels = {item['image']: item['label'].upper() for item in entries}
                if set(labels) - {path.name for path in paths}:
                    raise ValueError('標註檔與圖片不一致。')
            return {'folder': folder, 'paths': sorted(paths), 'labels': labels}
        self.launch('folder', scan)

    @Slot(str)
    def saveLabel(self, text):
        if self.context()['running'] or not self._images:
            return
        label = text.strip().upper()
        if not re.fullmatch('[A-Z0-9]{4}', label):
            self._message = '請人工核對圖片，輸入四碼英數字；不要用 OCR 猜測作為正確答案。'
            self.changed.emit()
            return
        path, folder = self._images[self._index], self._folder
        labels = {**self._labels, path.name: label}

        def save():
            # Reject edits made by another program since the folder was loaded.
            manifest = safe_path(folder / 'labels.json')
            old = json.loads(manifest.read_text(encoding='utf-8-sig')) if manifest.exists() else []
            if {item['image']: item['label'].upper() for item in old} != self._labels:
                raise ValueError('標註已被其他程式修改，請重新選擇資料夾。')
            atomic_json(manifest, [{'image': key, 'label': value} for key, value in sorted(labels.items())])
            return {'labels': labels}
        self.launch('label', save, cancellable=False)

    @Slot(int)
    def step(self, delta):
        if not self.busy and self._images and delta in (-1, 1):
            self._index = (self._index + delta) % len(self._images)
            self.changed.emit()

    @Slot(float)
    def evaluateFile(self, min_score=0.5):
        if self.context()['running']:
            return
        if not math.isfinite(min_score) or not 0 <= min_score <= 1:
            self._message = '評估分數門檻須介於 0 與 1。'
            self.changed.emit()
            return
        path, _ = QFileDialog.getOpenFileName(None, '選擇人工標註 JSON', str(self._folder or ''), 'JSON (*.json)')
        if not path:
            return

        def run():
            samples = load_samples(path, self._cancel)
            digest = hashlib.sha256()
            for image, label in samples:
                digest.update(hashlib.sha256(image).digest() + label.encode('ascii'))
            models = {}
            for model in ('standard', 'beta'):
                check_cancel(self._cancel)
                reader = CaptchaReader(model=model, min_score=min_score)
                models[model] = evaluate(samples, reader, cancel=self._cancel)
                del reader
            return {'app_version': VERSION, 'created_at': timestamp(), 'dataset_sha256': digest.hexdigest(),
                    'min_score': min_score, 'models': models, 'samples': len(samples),
                    'scope': 'local manually labelled samples; no live accuracy claim'}
        self._report = {}
        self.launch('evaluate', run)

    @Slot()
    def exportReport(self):
        if self.context()['running'] or not self._report:
            return
        path, _ = QFileDialog.getSaveFileName(
            None, '另存 OCR 評估摘要', 'evaluation.ocr-report.json', 'OCR 評估摘要 (*.ocr-report.json)')
        if path:
            report = dict(self._report)
            config = self.context()['config']

            def export():
                target = safe_path(path).resolve()
                if (not target.name.endswith('.ocr-report.json') or
                        any(target == root.resolve() or target.is_relative_to(root.resolve())
                            for root in sources(config).values())):
                    raise StorageError('ocr_report_destination')
                created = False
                try:
                    with target.open('x', encoding='utf-8') as handle:
                        created = True
                        json.dump(report, handle, ensure_ascii=False, allow_nan=False, indent=2)
                        handle.flush()
                        os.fsync(handle.fileno())
                except BaseException:
                    if created:
                        target.unlink(missing_ok=True)
                    raise
                return report
            self.launch('export', export, cancellable=False)

    def completed(self, action, value):
        if action == 'folder':
            self._report = {}
            self._folder, self._images, self._labels = value['folder'], value['paths'], value['labels']
            self._index = 0
            self._message = '圖片已載入；請逐張人工核對後保存標註。' if self._images else '此資料夾沒有支援的圖片。'
        elif action == 'label':
            self._report = {}
            self._labels = value['labels']
            self._message = '人工標註已保存，可切換下一張。'
        elif action == 'evaluate':
            self._result = self._report = value
            self._message = '兩套模型評估完成；結果僅代表這批人工標註資料，不會自動改變訂票模型。'
        else:
            self._result = self._report
            self._message = '評估摘要已匯出，不包含圖片、檔名或逐張標籤。'

    def error_message(self, error):
        if isinstance(error, StorageError):
            return super().error_message(error)
        if isinstance(error, FileExistsError):
            return '檔案已存在，請選擇新的 .ocr-report.json 檔名；既有檔案未覆寫。'
        if isinstance(error, (ValueError, UnicodeError, KeyError, TypeError)):
            return '圖片或標註格式不符，或標註已被修改。請確認四碼英數字、檔案範圍及大小，再重新載入。'
        if isinstance(error, RuntimeError):
            return 'OCR 模型載入或推論失敗；請檢查環境，這次結果不列入準確率。'
        return super().error_message(error)
