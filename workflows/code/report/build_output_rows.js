// The mock email outbox line (sent, or held for review) plus the shared review queue if needed.
// @include csv.js
const SENT_COLUMNS = __CONST:workflow_pack.common.SENT_COLUMNS__;
const REVIEW_COLUMNS = __CONST:workflow_pack.common.REVIEW_COLUMNS__;
const cfg = $('Config').first().json;
const r = $('Check narrative').first().json;
const now = new Date().toISOString();
const outbox = {
  timestamp: now, workflow: 'weekly_report', item_id: r.week_start, to: 'ops-managers@example.com',
  subject: `Weekly operations report ${r.week_start}`, status: r.status === 'sent' ? 'sent (mock)' : 'held for review',
  detail: `weekly_${r.week_start}.md`,
};
const rows = [{ target_path: `${cfg.base_dir}/outputs/sent_emails.csv`, line: csvRow(SENT_COLUMNS, outbox) }];
if (r.status === 'needs_review') {
  const review = { timestamp: now, workflow: 'weekly_report', item_id: r.week_start, reason: r.reason, details: null };
  rows.push({ target_path: `${cfg.base_dir}/outputs/human_review_queue.csv`, line: csvRow(REVIEW_COLUMNS, review) });
}
const response = { week_start: r.week_start, status: r.status, reason: r.reason, numbers: r.numbers };
return rows.map((row) => ({ json: { ...row, response, from_webhook: r.from_webhook } }));
