// Code decides the final priority and whether to escalate.
// This node is reached two ways: normally (after the schema check) or, when the AI call failed,
// through "Safety case?" so that a safety ticket is escalated even while the model is down.
// @include csv.js
const ERROR_COLUMNS = __CONST:workflow_pack.common.ERROR_COLUMNS__;
const cfg = $('Config').first().json;
const checked = $('Check input').first().json;
const incoming = $input.first().json;
const aiFailed = Boolean(incoming.error);
const ai = aiFailed ? null : incoming.ai;
const subject = checked.ticket.subject || '';

function applyRules(ai, safetyKeyword, threshold) {
  const fields = ai ? { priority: ai.priority, team: ai.team, sentiment: ai.sentiment, summary: ai.summary } : null;
  if (safetyKeyword) {
    return { status: 'escalated', priority: 'P1', team: ai ? ai.team : 'Product', sentiment: ai ? ai.sentiment : 'negative',
             summary: ai ? ai.summary : subject, reason: `safety net matched '${safetyKeyword}'`, escalate: true };
  }
  if (ai === null) {
    return { status: 'needs_review', priority: '', team: 'Triage queue', sentiment: '', summary: subject,
             reason: 'AI output failed the JSON schema check', escalate: false };
  }
  if (ai.priority === 'P1') return { ...fields, status: 'escalated', reason: 'AI set P1', escalate: true };
  if (ai.confidence < threshold) return { ...fields, status: 'needs_review', reason: 'low confidence', escalate: false };
  return { ...fields, status: 'routed', reason: '', escalate: false };
}

const result = { ticket_id: checked.ticket_id, ...applyRules(ai, checked.safety_keyword, Number(cfg.confidence_threshold)) };
let errorLine = '';
if (aiFailed) {
  // Log the failure and forget the key so the ticket can be re-run once the model is back.
  const error = incoming.error;
  const record = { timestamp: new Date().toISOString(), workflow: 'ticket_triage', item_id: checked.ticket_id, step: 'ai_triage',
                   error_type: error.name || 'Error', message: String(error.description || error.message || error).slice(0, 500) };
  errorLine = csvRow(ERROR_COLUMNS, record);
  const store = $getWorkflowStaticData('global');
  if (store.seen) delete store.seen[checked.dedupe_text];
}
return [{ json: { ...result, schema_errors: incoming.schema_errors || [], error_line: errorLine } }];
