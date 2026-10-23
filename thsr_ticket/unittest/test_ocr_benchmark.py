import json
from unittest.mock import Mock

import pytest

from thsr_ticket.captcha import CaptchaGuess, CaptchaReader
from thsr_ticket.ocr_benchmark import evaluate, load_samples


def test_evaluation_counts_rejections_in_total_accuracy():
    reader = Mock(unavailable=False)
    reader.recognize.side_effect = [CaptchaGuess('ABCD', 0.9), CaptchaGuess('ZZZZ', 0.9), None]
    report = evaluate([(b'1', 'ABCD'), (b'2', 'EFGH'), (b'3', 'JKLM')], reader,
                      clock=Mock(side_effect=[0, 0.01, 1, 1.02, 2, 2.03]))
    assert report['exact_match_rate'] == pytest.approx(1 / 3)
    assert report['coverage'] == pytest.approx(2 / 3)
    assert report['accepted_accuracy'] == 0.5
    assert report['mean_inference_ms'] == pytest.approx(20)
    assert report['correct'] == report['wrong'] == report['abstained'] == 1


def test_no_accepted_predictions():
    reader = Mock(unavailable=False)
    reader.recognize.return_value = None
    report = evaluate([(b'image', 'ABCD')], reader)
    assert report['accepted_accuracy'] is None
    assert report['exact_match_rate'] == report['coverage'] == 0


def test_model_failure_is_not_scored_as_accuracy():
    reader = Mock(unavailable=True)
    with pytest.raises(RuntimeError):
        evaluate([(b'image', 'ABCD')], reader)


def test_manifest_paths_and_labels(tmp_path):
    (tmp_path / 'sample.png').write_bytes(b'image')
    path = tmp_path / 'labels.json'
    path.write_text(json.dumps([{'image': 'sample.png', 'label': 'a7b3'}]), encoding='utf-8')
    assert load_samples(path) == [(b'image', 'A7B3')]
    path.write_text(json.dumps([{'image': 'sample.png', 'label': 'ABCD'}] * 2))
    with pytest.raises(ValueError, match='重複'):
        load_samples(path)


@pytest.mark.parametrize('data', [[], {}, [{'image': 'x', 'label': 'ABC'}],
                                  [{'image': 'x', 'label': 'ABCD', 'extra': 1}]])
def test_invalid_manifest(tmp_path, data):
    path = tmp_path / 'labels.json'
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError):
        load_samples(path)


def test_selected_model_is_loaded_once(monkeypatch):
    loader = Mock()
    monkeypatch.setattr('thsr_ticket.captcha._load_engine', loader)
    reader = CaptchaReader(model='beta')
    assert reader.prepare()
    assert reader.prepare()
    loader.assert_called_once_with('beta')


def test_manifest_cannot_escape_its_folder(tmp_path):
    outside = tmp_path / 'outside.png'
    outside.write_bytes(b'image')
    folder = tmp_path / 'labels'
    folder.mkdir()
    manifest = folder / 'labels.json'
    manifest.write_text(json.dumps([{'image': '../outside.png', 'label': 'ABCD'}]))
    with pytest.raises(ValueError):
        load_samples(manifest)


def test_cancelled_evaluation_does_not_score_remaining_images():
    import threading
    from thsr_ticket.scan_report import ScanCancelled
    cancel = threading.Event()
    cancel.set()
    reader = Mock(unavailable=False)
    with pytest.raises(ScanCancelled):
        evaluate([(b'image', 'ABCD')], reader, cancel=cancel)
    reader.recognize.assert_not_called()
