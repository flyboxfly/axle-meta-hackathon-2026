'use strict';
const el = id => document.getElementById(id);
const tg = (window.Telegram && window.Telegram.WebApp) || null;
const initData = (tg && tg.initData) || '';
if (tg) { try { tg.ready(); tg.expand(); } catch (e) {} }
let current = null, busy = false, pollTimer = null;
const rid = () => (crypto.randomUUID ? crypto.randomUUID().replace(/-/g, '') : [...crypto.getRandomValues(new Uint8Array(16))].map(b => b.toString(16).padStart(2, '0')).join(''));
function showError(message) { const box = el('error'); box.textContent = message || 'Something went wrong.'; box.classList.add('show'); }
function clearError() { el('error').classList.remove('show'); }
function setBusy(value) { busy = value; document.querySelectorAll('button,input,select,textarea').forEach(c => { c.disabled = value; }); }
function showOnly(id) { for (const s of document.querySelectorAll('main > section')) s.hidden = s.id !== id; }
function stepsTo(stage) {
  const order = ['profile', 'photo', 'review', 'confirmed', 'decided'];
  const rank = { profile: 0, photo: 1, review: 2, confirmed: 3, evaluating: 3, decided: 4 };
  const at = rank[stage] === undefined ? 0 : rank[stage];
  document.querySelectorAll('#steps li').forEach((li, i) => {
    const current = i === at && stage !== 'decided';
    li.classList.toggle('done', i < at || (stage === 'decided' && i <= at));
    li.classList.toggle('now', current);
    if (current) li.setAttribute('aria-current', 'step');
    else li.removeAttribute('aria-current');
  });
}
async function api(path, body) {
  const r = await fetch(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ initData, ...body }) });
  const data = await r.json().catch(() => ({}));
  if (!r.ok || data.ok === false) {
    const err = new Error((data && data.error) || ('Request failed (' + r.status + ')'));
    err.status = r.status; err.state = data && data.state;
    throw err;
  }
  return data;
}
function esc(value) { return String(value).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c])); }
function fieldRow(label, field) {
  let shown, cls = '';
  if (!field || field.value === null || field.value === undefined) { shown = 'unknown'; cls = 'unknown'; }
  else if (field.state === 'explicit_zero') { shown = esc(field.value) + ' (explicit zero)'; cls = 'zero'; }
  else if (field.value === 'all_operating_expenses') shown = 'All operating expenses';
  else shown = esc(field.value);
  const src = field && field.source ? '<span class="badge src-' + esc(String(field.source).split(' ')[0]) + '">' + esc(field.source) + '</span>' : '';
  return '<div class="row"><span class="k">' + esc(label) + '</span><span class="v ' + cls + '">' + shown + src + '</span></div>';
}
function profileRows(p) {
  if (!p) return '<p>No profile yet.</p>';
  return fieldRow('Your cost per mile', p.operating_cpm) + fieldRow('Cost basis', p.expense_claim)
    + fieldRow('Your asking rate per mile', p.target_all_mile_rpm) + fieldRow('Lowest total you will accept', p.minimum_job_charge)
    + fieldRow('Truck', p.equipment) + fieldRow('About your work', p.operating_context);
}
function reviewRows(r) {
  let h = '<h2>From the screenshot</h2>' + fieldRow('Posted pay $', r.facts.payout) + fieldRow('Loaded miles', r.facts.loaded_miles)
    + fieldRow('Miles to pickup', r.facts.deadhead_miles) + fieldRow('Weight lbs', r.facts.weight_lbs);
  h += '<h2>Your rates</h2>' + fieldRow('Your asking rate per mile', r.pricing.target_all_mile_rpm) + fieldRow('Your cost per mile', r.pricing.operating_cpm)
    + fieldRow('Cost basis', r.pricing.expense_claim) + fieldRow('Lowest total you will accept', r.pricing.minimum_job_charge);
  h += '<h2>This trip</h2>' + fieldRow('Miles after delivery', r.pricing.reposition_miles)
    + fieldRow('How long it takes', r.trip.duration_note) + fieldRow('Timing works?', r.trip.availability) + fieldRow('Loading or handling needs', r.trip.handling_note);
  h += '<h2>Pay for this check</h2>' + fieldRow('Broker offer $', r.counter_offer) + fieldRow('Pay being checked $', r.evaluated_compensation);
  if (r.counter_note && r.counter_note.value) h += fieldRow('Counter note', r.counter_note);
  if (r.issues && r.issues.length) h += '<div class="notice">Unresolved notes:<br>• ' + r.issues.map(esc).join('<br>• ') + '</div>';
  if (r.mileage_candidates && r.mileage_candidates.length) {
    for (const c of r.mileage_candidates) h += '<div class="notice">Estimated miles from the screenshot note: ' + esc(c.value) + ' mi — not confirmed yet. <button type="button" class="secondary adopt-btn" data-value="' + esc(c.value) + '">Use ' + esc(c.value) + ' mi</button> Using it saves as your value; you will confirm again.</div>';
  } else if (r.mileage_proposals && r.mileage_proposals.length) h += '<div class="notice">Possible pickup-to-delivery interpretation (UNCONFIRMED, from note): ' + r.mileage_proposals.map(esc).join(', ') + ' — confirm explicitly or correct.</div>';
  return h;
}
function money(v) { return v === null || v === undefined ? 'unknown' : '$' + v; }
function resultCard(kind, r) {
  let h = '';
  if (kind === 'opening_bid') {
    if (r.opening_bid !== null) {
      el('decisionStatus').textContent = 'DRAFT — NOT SENT · PRELIMINARY ESTIMATE';
      el('decisionTitle').textContent = 'Suggested asking price: $' + r.opening_bid;
      h = '<p>That covers your estimated operating cost of ' + money(r.estimated_operating_cost)
        + ' across ' + esc(r.total_miles || '?') + ' miles and leaves ' + money(r.estimated_operating_surplus)
        + ' above operating cost.</p>'
        + '<div class="metrics"><div class="metric"><span class="value">' + esc(r.total_miles || '?') + '</span><small>TOTAL MILES</small></div>'
        + '<div class="metric"><span class="value">' + money(r.estimated_operating_cost) + '</span><small>EST. OPERATING COST</small></div>'
        + '<div class="metric"><span class="value">' + money(r.estimated_operating_surplus) + '</span><small>ABOVE OPERATING COST</small></div></div>';
    } else {
      el('decisionStatus').textContent = 'DRAFT — NOT SENT';
      el('decisionTitle').textContent = 'We cannot suggest a price yet';
      h = '<div class="warn">' + esc(r.pricing_issue || 'Some details need review.')
        + '<br>What to do: check the miles, lower your asking rate or cost per mile, save the changes and confirm again.</div>';
    }
  } else if (r.decision === 'ACCEPT') {
    el('decisionStatus').textContent = 'DRAFT — NOT SENT · PRELIMINARY ESTIMATE';
    el('decisionTitle').textContent = 'This offer clears your checks';
    h = '<p>The offer of ' + money(r.compensation) + ' is ' + money(r.estimated_operating_surplus)
      + ' above your estimated operating cost of ' + money(r.estimated_operating_cost)
      + ' across ' + esc(r.total_miles || '?') + ' miles, and clears your lowest total.</p>'
      + fieldRow('Offer $', { value: r.compensation, state: 'known' })
      + fieldRow('Est. operating cost $', { value: r.estimated_operating_cost, state: 'known' })
      + fieldRow('Above operating cost $', { value: r.estimated_operating_surplus, state: 'known' });
  } else if (r.decision === 'NEGOTIATE') {
    el('decisionStatus').textContent = 'DRAFT — NOT SENT · PRELIMINARY ESTIMATE';
    let ask = null;
    if (r.target_revenue !== null && r.minimum_job_charge !== null && r.estimated_operating_cost !== null) {
      const candidate = Math.max(parseFloat(r.target_revenue), parseFloat(r.minimum_job_charge));
      if (candidate > parseFloat(r.estimated_operating_cost)) ask = candidate.toFixed(2);
    }
    if (ask !== null) {
      el('decisionTitle').textContent = 'Suggested asking price: $' + ask;
      h = '<p>The current offer of ' + money(r.compensation) + ' is ' + money(r.revenue_gap_to_target)
        + ' below what your asking rate needs across ' + esc(r.total_miles || '?')
        + ' miles. Your estimated operating cost is ' + money(r.estimated_operating_cost) + '.</p>';
    } else {
      el('decisionTitle').textContent = 'The current terms need work';
      h = '<div class="warn">No suggested price follows from these details. Check the miles and rates, save the changes and confirm again.</div>';
    }
    h += fieldRow('Est. operating cost $', { value: r.estimated_operating_cost, state: 'known' });
    if (r.estimated_operating_surplus !== null && r.estimated_operating_surplus !== undefined)
      h += fieldRow('Above operating cost $', { value: r.estimated_operating_surplus, state: r.estimated_operating_surplus === null ? 'unknown' : 'known' });
  } else if (r.decision === 'DECLINE') {
    el('decisionStatus').textContent = 'DRAFT — NOT SENT';
    el('decisionTitle').textContent = 'This trip does not work';
    h = '<div class="warn">You marked the timing as not workable. What to do: only a timing change, saved as new details and confirmed again, can change this.</div>';
  } else {
    el('decisionStatus').textContent = 'DRAFT — NOT SENT';
    el('decisionTitle').textContent = 'One more detail needed';
    const friendly = (r.missing_information || []).map(m => m === 'schedule_feasibility' ? 'whether the timing works for you' : m).join(', ');
    h = '<div class="warn">Add: ' + esc(friendly || 'the missing details')
      + '. Save the change above and confirm again — no price is suggested until then.</div>'
      + fieldRow('Est. operating cost $', { value: r.estimated_operating_cost, state: r.estimated_operating_cost === null ? 'unknown' : 'known' });
  }
  return h;
}
function brokerDraft(guidance) {
  if (!guidance) return '';
  const marker = 'Broker wording';
  const at = guidance.indexOf(marker);
  if (at < 0) return '';
  const quoted = guidance.slice(at).split('\n').map(l => l.trim()).find(l => l.startsWith('"'));
  return quoted || '';
}
function howWorkedOut(guidance) {
  if (!guidance) return '';
  const at = guidance.indexOf('Broker wording');
  return (at >= 0 ? guidance.slice(0, at) : guidance).trim();
}
function render(state) {
  current = state;
  stepsTo(state.stage);
  stopPoll();
  if (state.stage === 'profile') {
    if (state.staged_profile) { el('profileReview').innerHTML = profileRows(state.staged_profile); showOnly('screen-profile-review'); }
    else showOnly('screen-profile');
  } else if (state.stage === 'photo') {
    el('photoProfile').innerHTML = profileRows(state.profile);
    showOnly('screen-photo');
    poll(4000);
  } else if (state.stage === 'review') {
    el('reviewStatus').textContent = 'STEP 3 · CHECK DETAILS';
    el('reviewBody').innerHTML = reviewRows(state.review);
    el('reviewConfirm').textContent = 'Confirm these details';
    showOnly('screen-review');
  } else if (state.stage === 'confirmed') {
    el('confirmedBody').innerHTML = reviewRows(state.review);
    const uncertain = state.evaluation && state.evaluation.state === 'uncertain';
    el('confirmedEval').innerHTML = state.evaluation ? '<div class="warn">Last try did not finish' + (state.evaluation.failure_category ? ' (' + esc(state.evaluation.failure_category) + ')' : '') + '. Nothing was retried automatically. Change a detail, or use the button below to try once more.</div>' : '';
    el('requestBid').textContent = uncertain ? 'Try once more (one new try)' : 'Get my suggested price';
    showOnly('screen-confirmed');
  } else if (state.stage === 'evaluating') {
    showOnly('screen-evaluating');
    poll(2500);
  } else if (state.stage === 'decided') {
    let body = resultCard(state.evaluation_kind, state.result);
    const draft = brokerDraft(state.guidance);
    if (draft) body += '<h2>Draft message to the broker</h2><div class="warn">NOT SENT — send it yourself only if you choose to.</div><pre class="guidance">' + esc(draft) + '</pre>';
    const detail = howWorkedOut(state.guidance);
    body += '<details><summary>How this was worked out</summary>'
      + (detail ? '<pre class="guidance">' + esc(detail) + '</pre>' : '')
      + '<div class="notice">Preliminary estimate only. It uses your reviewed miles and rates; stops, traffic and market conditions are not included. Nothing is booked or sent.</div></details>';
    el('decisionBody').innerHTML = body;
    showOnly('screen-decided');
  }
}
function stopPoll() { if (pollTimer) { clearTimeout(pollTimer); pollTimer = null; } }
function poll(ms) { stopPoll(); pollTimer = setTimeout(refresh, ms); }
async function refresh() {
  if (busy) return;
  clearError(); setBusy(true);
  try {
    const data = await api('/miniapp/api/state', {});
    render(data.state);
  } catch (e) {
    if (e.status === 403) { stopPoll(); showOnly('screen-consent'); if (e.message) el('consentText').textContent = e.message + ' Then reopen this app.'; }
    else showError(e.message);
  } finally { setBusy(false); }
}
function formFields(form) {
  const out = {};
  for (const [k, v] of new FormData(form)) { const t = (v || '').trim(); if (t) out[k] = t; }
  return out;
}
async function mutate(path, body, keepForm) {
  clearError(); setBusy(true);
  try {
    const data = await api(path, body);
    render(data.state);
    return true;
  } catch (e) {
    if (e.state) render(e.state);
    showError(e.message + (e.status === 409 ? ' Your entries above are preserved.' : ' Your entries above are preserved.'));
    return false;
  } finally { setBusy(false); }
}
el('profileForm').addEventListener('submit', e => { e.preventDefault(); if (!busy) mutate('/miniapp/api/profile', { request_id: rid(), fields: formFields(e.target) }); });
el('profileBack').addEventListener('click', () => showOnly('screen-profile'));
el('profileConfirm').addEventListener('click', () => { if (!busy && current && current.stage_token) mutate('/miniapp/api/profile/confirm', { request_id: rid(), stage_token: current.stage_token }); });
el('photoRefresh').addEventListener('click', refresh);
el('consentRetry').addEventListener('click', () => { showOnly('screen-loading'); refresh(); });
el('correctForm').addEventListener('submit', e => {
  e.preventDefault(); if (busy || !current || !current.review) return;
  const fields = formFields(e.target);
  if (!Object.keys(fields).length) { showError('Enter at least one value.'); return; }
  mutate('/miniapp/api/correct', { request_id: rid(), expected_revision: current.review.revision, fields }).then(ok => { if (ok) e.target.reset(); });
});
el('reviewConfirm').addEventListener('click', () => { if (!busy && current && current.review) mutate('/miniapp/api/confirm', { request_id: rid(), revision: current.review.revision }); });
el('requestBid').addEventListener('click', () => {
  if (busy || !current || !current.review) return;
  const body = { request_id: rid(), revision: current.review.revision };
  if (current.evaluation && current.evaluation.state === 'uncertain') body.retry_uncertain = true;
  mutate('/miniapp/api/evaluate', body);
});
document.addEventListener('click', e => {
  const btn = e.target && e.target.closest ? e.target.closest('.adopt-btn') : null;
  if (!btn || busy || !current || !current.review) return;
  mutate('/miniapp/api/correct', { request_id: rid(), expected_revision: current.review.revision, fields: { loaded_miles: btn.dataset.value } });
});
el('confirmCorrectForm').addEventListener('submit', e => {
  e.preventDefault(); if (busy || !current || !current.review) return;
  const fields = formFields(e.target);
  if (!Object.keys(fields).length) { showError('Enter at least one value.'); return; }
  mutate('/miniapp/api/correct', { request_id: rid(), expected_revision: current.review.revision, fields }).then(ok => { if (ok) e.target.reset(); });
});
el('counterForm').addEventListener('submit', e => {
  e.preventDefault(); if (busy || !current || !current.review) return;
  mutate('/miniapp/api/correct', { request_id: rid(), expected_revision: current.review.revision, fields: formFields(e.target) }).then(ok => { if (ok) e.target.reset(); });
});
el('decidedRefresh').addEventListener('click', refresh);
if (!initData) { showOnly('screen-consent'); el('consentText').textContent = 'No Telegram launch data found. Open this app from the bot button inside Telegram.'; }
else refresh();
