// One output item per line to append: the team sheet row, plus the shared review queue if needed.
// @include csv.js
const SHEET_COLUMNS = __CONST:workflow_pack.enquiry.SHEET_COLUMNS__;
const REVIEW_COLUMNS = __CONST:workflow_pack.common.REVIEW_COLUMNS__;
const cfg = $('Config').first().json;
const item = $input.first().json;
const now = new Date().toISOString();
const resumeUrl = item.status === 'pending_approval' ? $execution.resumeUrl : '';
const record = { ...item, timestamp: now, resume_url: resumeUrl };
const response = {
  message_id: item.message_id, status: item.status, reason: item.reason, category: item.category || null,
  team: item.team, flag: item.flag || '', name: item.name ?? null, company: item.company ?? null, need: item.need || '',
  urgency: item.urgency || null, language: item.language || null, confidence: item.confidence ?? null,
  draft_subject: item.draft_subject || '',
  approve_url: resumeUrl ? `${resumeUrl}${resumeUrl.includes('?') ? '&' : '?'}decision=approve` : '',
};
const rows = [{ target_path: `${cfg.base_dir}/outputs/enquiry_sheet.csv`, line: csvRow(SHEET_COLUMNS, record) }];
if (item.status === 'needs_review') {
  const review = { timestamp: now, workflow: 'enquiry_intake', item_id: item.message_id, reason: item.reason,
                   details: item.schema_errors?.length ? { schema_errors: item.schema_errors } : { category: item.category } };
  rows.push({ target_path: `${cfg.base_dir}/outputs/human_review_queue.csv`, line: csvRow(REVIEW_COLUMNS, review) });
}
return rows.map((row) => ({ json: { ...row, response, status: item.status } }));
