// Error branch: write one row to logs/errors.csv, forget the idempotency key so the input
// can be retried later, and answer the webhook caller with status "error".
// @include csv.js
const COLUMNS = __ERROR_COLUMNS__;
const cfg = $('Config').first().json;
const item = $input.first().json;
const error = item.error || 'unknown error';
const message = typeof error === 'string' ? error : error.description || error.message || JSON.stringify(error);
let itemId = 'unknown';
try {
  itemId = __ID_FALLBACK__ || itemId; // straight from the trigger, in case the input check failed
} catch (noTrigger) {
  // started by the schedule, or no such field
}
try {
  const checked = $('__KEY_NODE__').first().json;
  itemId = checked.__ID_FIELD__ || itemId;
  const key = checked.dedupe_key || checked.dedupe_text;
  const store = $getWorkflowStaticData('global');
  if (key && store.seen) delete store.seen[key];
} catch (notExecuted) {
  // the input check itself failed, so no key was stored yet
}
const record = {
  timestamp: new Date().toISOString(),
  workflow: '__WORKFLOW__',
  item_id: itemId,
  step: item.step || 'check_input',
  error_type: typeof error === 'string' ? 'Error' : error.name || 'Error',
  message: String(message).slice(0, 500),
};
return [{
  json: {
    target_path: `${cfg.base_dir}/logs/errors.csv`,
    line: csvRow(COLUMNS, record),
    response: { status: 'error', item_id: itemId, step: record.step, reason: record.message },
  },
}];
