// Post every ticket to the team channel (mock: outputs/channel_posts.csv),
// queue it for a person if needed, and log the AI error if there was one.
// @include csv.js
const CHANNEL_COLUMNS = __CONST:workflow_pack.triage.CHANNEL_COLUMNS__;
const REVIEW_COLUMNS = __CONST:workflow_pack.common.REVIEW_COLUMNS__;
const cfg = $('Config').first().json;
const r = $('Apply rules').first().json;
const now = new Date().toISOString();
const rows = [{ target_path: `${cfg.base_dir}/outputs/channel_posts.csv`, line: csvRow(CHANNEL_COLUMNS, { ...r, timestamp: now }) }];
if (r.status === 'needs_review') {
  const review = { timestamp: now, workflow: 'ticket_triage', item_id: r.ticket_id, reason: r.reason, details: { schema_errors: r.schema_errors } };
  rows.push({ target_path: `${cfg.base_dir}/outputs/human_review_queue.csv`, line: csvRow(REVIEW_COLUMNS, review) });
}
if (r.error_line) rows.push({ target_path: `${cfg.base_dir}/logs/errors.csv`, line: r.error_line });
const response = { ticket_id: r.ticket_id, status: r.status, priority: r.priority, team: r.team, sentiment: r.sentiment,
                   summary: r.summary, reason: r.reason, escalated: r.escalate };
return rows.map((row) => ({ json: { ...row, response } }));
