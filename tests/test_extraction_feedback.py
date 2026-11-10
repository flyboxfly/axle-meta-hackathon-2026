"""Fictional extraction failures, with no provider or Telegram calls."""
import json
import pytest
from axle_hackathon.opening_intake import ScreenshotDraft
from axle_hackathon.pilot_execution import ExtractionResponseError
from axle_hackathon.pilot_runtime import OpeningWorker
from test_h15_opening_workflow import store, session, delegator, draft_text, submit_shot


@pytest.mark.parametrize('field,value,category', [
    ('issues', ['private'] * 7, 'extraction_issues_count'),
    ('issues', ['private' * 41], 'extraction_issue_limit'),
    ('evidence', {'payout': 'private' * 34}, 'extraction_evidence_limit'),
])
def test_precise_limit_categories(field, value, category):
    data = json.loads(draft_text())
    data[field] = value
    with pytest.raises(ExtractionResponseError) as exc:
        ScreenshotDraft.validated_text(json.dumps(data))
    assert exc.value.failure_category == category


def test_total_response_limit():
    with pytest.raises(ExtractionResponseError) as exc:
        ScreenshotDraft.validated_text('x' * 12001)
    assert exc.value.failure_category == 'extraction_response_limit'


@pytest.mark.parametrize('delivery_ok', [True, False])
def test_failed_extraction_notifies_once_and_keeps_budget_and_cause(store, delivery_ok):
    access = session(store)
    calls, sent = [], []
    data = json.loads(draft_text())
    data['issues'] = ['private' * 41]
    inner = delegator(store, calls, image_text=json.dumps(data))

    def send(chat, text):
        sent.append(text)
        return delivery_ok

    worker = OpeningWorker(store, inner, send, global_limit=4, carrier_limit=4)
    submit_shot(store, access.token)
    assert worker.tick() == 'uncertain'
    assert worker.tick() == 'idle'
    assert len(calls) == len(sent) == 1
    assert 'Pause this test' in sent[0]
    assert 'private' not in sent[0]
    assert store._db.execute('SELECT SUM(attempts) FROM pilot_budget').fetchone() == (1,)
    assert store._db.execute('SELECT category FROM pilot_failure_categories').fetchone() == (
        'extraction_issue_limit',)
    assert store._db.execute('SELECT status FROM pilot_updates').fetchone() == ('uncertain',)


def test_failure_notice_requires_current_consent(store):
    access = session(store)
    sent = []

    class WithdrawnExtraction:
        def screenshot(self, *args, **kwargs):
            store.forget(1, 1)
            raise ExtractionResponseError('extraction_issue_limit', 'fixed limit failure')

    worker = OpeningWorker(store, WithdrawnExtraction(),
                           lambda *args: sent.append(args) or True,
                           global_limit=4, carrier_limit=4)
    submit_shot(store, access.token)
    assert worker.tick() == 'uncertain'
    assert sent == []


def test_requested_schema_matches_local_limits():
    from axle_hackathon.opening_intake import (
        build_extraction_request, MAX_ISSUES, MAX_ISSUE_CHARS, MAX_EVIDENCE_CHARS)
    request = build_extraction_request(b'fictional-image', 'image/png')
    fields = request['text']['format']['schema']['properties']
    assert fields['issues']['maxItems'] == MAX_ISSUES
    assert fields['issues']['items']['maxLength'] == MAX_ISSUE_CHARS
    assert all(field['maxLength'] == MAX_EVIDENCE_CHARS
               for field in fields['evidence']['properties'].values())
    data = json.loads(draft_text())
    data['issues'] = ['x' * MAX_ISSUE_CHARS] * MAX_ISSUES
    assert len(ScreenshotDraft.validated_text(json.dumps(data)).issues) == MAX_ISSUES


def test_extra_evidence_key_remains_schema_failure():
    data = json.loads(draft_text())
    data['evidence'] = dict.fromkeys(['payout', 'loaded_miles', 'deadhead_miles',
                                     'weight_lbs', 'extra'], '')
    with pytest.raises(ExtractionResponseError) as exc:
        ScreenshotDraft.validated_text(json.dumps(data))
    assert exc.value.failure_category == 'extraction_schema'
