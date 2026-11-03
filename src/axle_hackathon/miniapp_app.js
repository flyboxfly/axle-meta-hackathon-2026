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
    li.classList.toggle('done', i < at || (stage === 'decided' && i <= at));
    li.classList.toggle('now', i === at && stage !== 'decided');
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
  else shown = esc(field.value);
  const src = field && field.source ? '<span class="badge src-' + esc(String(field.source).split(' ')[0]) + '">' + esc(field.source) + '</span>' : '';
  return '<div class="row"><span class="k">' + esc(label) + '</span><span class="v ' + cls + '">' + shown + src + '</span></div>';
}
function profileRows(p) {
  if (!p) return '<p>No profile yet.</p>';
  return fieldRow('Operating CPM', p.operating_cpm) + fieldRow('Expense basis', p.expense_claim)
    + fieldRow('Target all-mile RPM', p.target_all_mile_rpm) + fieldRow('Minimum job charge', p.minimum_job_charge)
    + fieldRow('Equipment', p.equipment) + fieldRow('Operating context', p.operating_context);
}
function reviewRows(r) {
  let h = '<h2>Screenshot facts</h2>' + fieldRow('Posted payout $', r.facts.payout) + fieldRow('Loaded miles', r.facts.loaded_miles)
    + fieldRow('Deadhead miles', r.facts.deadhead_miles) + fieldRow('Weight lbs', r.facts.weight_lbs);
  h += '<h2>Session pricing</h2>' + fieldRow('Target all-mile RPM', r.pricing.target_all_mile_rpm) + fieldRow('Operating CPM', r.pricing.operating_cpm)
    + fieldRow('Expense basis', r.pricing.expense_claim) + fieldRow('Minimum job charge', r.pricing.minimum_job_charge)
    + fieldRow('Reposition miles', r.pricing.reposition_miles);
  h += '<h2>Trip context</h2>' + fieldRow('Duration', r.trip.duration_note) + fieldRow('Availability', r.trip.availability) + fieldRow('Handling', r.trip.handling_note);
  h += '<h2>Compensation</h2>' + fieldRow('Owner counteroffer $', r.counter_offer) + fieldRow('Evaluated compensation $', r.evaluated_compensation);
  if (r.counter_note && r.counter_note.value) h += fieldRow('Counter note', r.counter_note);
  if (r.issues && r.issues.length) h += '<div class="notice">Unresolved notes:<br>• ' + r.issues.map(esc).join('<br>• ') + '</div>';
  if (r.mileage_proposals && r.mileage_proposals.length) h += '<div class="notice">Possible pickup-to-delivery interpretation (UNCONFIRMED, from note): ' + r.mileage_proposals.map(esc).join(', ') + ' — confirm explicitly or correct.</div>';
  return h;
}
function money(v) { return v === null || v === undefined ? 'unknown' : '$' + v; }
function resultCard(kind, r) {
  let h = '';
  if (kind === 'opening_bid') {
    el('decisionStatus').textContent = r.opening_bid !== null ? 'PRELIMINARY OPENING' : 'PRICING REVIEW';
    el('decisionTitle').textContent = r.opening_bid !== null ? 'Opening bid: $' + r.opening_bid : 'Review needed before pricing';
    h = '<div class="metrics"><div class="metric"><span class="value">' + esc(r.total_miles || '?') + '</span><small>TOTAL MILES</small></div>'
      + '<div class="metric"><span class="value">' + money(r.estimated_operating_cost) + '</span><small>EST. OPERATING COST</small></div>'
      + '<div class="metric"><span class="value">' + money(r.target_revenue) + '</span><small>TARGET REVENUE</small></div></div>';
    if (r.opening_bid !== null) h += fieldRow('Opening bid $', { value: r.opening_bid, state: 'known' }) + fieldRow('Est. operating surplus $', { value: r.estimated_operating_surplus, state: 'known' });
    else h += '<div class="warn">Missing: ' + esc((r.missing || []).join(', ') || 'review required') + (r.pricing_issue ? '<br>' + esc(r.pricing_issue) : '') + '</div>';
  } else {
    const titles = { ACCEPT: 'The supplied checks pass.', NEGOTIATE: 'The current terms need work.', DECLINE: 'This schedule does not work.', NEED_MORE_INFORMATION: 'Add facts before deciding.' };
    el('decisionStatus').textContent = r.decision.replace(/_/g, ' ');
    el('decisionTitle').textContent = titles[r.decision] || r.decision;
    h = '<div class="metrics"><div class="metric"><span class="value">' + money(r.compensation) + '</span><small>COMPENSATION</small></div>'
      + '<div class="metric"><span class="value">' + esc(r.total_miles || '?') + '</span><small>TOTAL MILES</small></div>'
      + '<div class="metric"><span class="value">' + (r.revenue_gap_to_target === null ? '—' : '$' + r.revenue_gap_to_target) + '</span><small>GAP TO TARGET</small></div></div>';
    h += fieldRow('Compensation source', { value: r.compensation_source, state: 'known' }) + fieldRow('Est. operating cost $', { value: r.estimated_operating_cost, state: r.estimated_operating_cost === null ? 'unknown' : 'known' })
      + fieldRow('Target revenue $', { value: r.target_revenue, state: r.target_revenue === null ? 'unknown' : 'known' });
    if (r.estimated_operating_surplus !== null && r.estimated_operating_surplus !== undefined) h += fieldRow('Est. operating surplus $', { value: r.estimated_operating_surplus, state: 'known' });
    if (r.missing_information && r.missing_information.length) h += '<div class="warn">Missing: ' + r.missing_information.map(esc).join(', ') + '</div>';
    h += '<div class="notice">Limits: stops, hours-of-service, routing and market conditions are not modeled; equipment match and schedule are carrier-supplied, not verified. A decision here is never a booking.</div>';
  }
  return h;
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
    el('reviewStatus').textContent = 'STEP 3 · REVIEW REVISION ' + state.review.revision;
    el('reviewBody').innerHTML = reviewRows(state.review);
    el('reviewConfirm').textContent = 'Confirm exact revision ' + state.review.revision;
    showOnly('screen-review');
  } else if (state.stage === 'confirmed') {
    el('confirmedBody').innerHTML = reviewRows(state.review);
    el('confirmedEval').innerHTML = state.evaluation ? '<div class="warn">Last evaluation: ' + esc(state.evaluation.state) + '. No automatic retry; requesting again queues one new budgeted attempt.</div>' : '';
    showOnly('screen-confirmed');
  } else if (state.stage === 'evaluating') {
    showOnly('screen-evaluating');
    poll(2500);
  } else if (state.stage === 'decided') {
    el('decisionBody').innerHTML = '<div class="notice">' + esc(state.result.notice || 'DRAFT — NOT SENT.') + '</div>' + resultCard(state.evaluation_kind, state.result)
      + (state.guidance ? '<h2>Negotiation guidance</h2><pre class="guidance">' + esc(state.guidance) + '</pre>' : '');
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
el('requestBid').addEventListener('click', () => { if (!busy && current && current.review) mutate('/miniapp/api/evaluate', { request_id: rid(), revision: current.review.revision }); });
el('counterForm').addEventListener('submit', e => {
  e.preventDefault(); if (busy || !current || !current.review) return;
  mutate('/miniapp/api/correct', { request_id: rid(), expected_revision: current.review.revision, fields: formFields(e.target) }).then(ok => { if (ok) e.target.reset(); });
});
el('decidedRefresh').addEventListener('click', refresh);
if (!initData) { showOnly('screen-consent'); el('consentText').textContent = 'No Telegram launch data found. Open this app from the bot button inside Telegram.'; }
else refresh();
