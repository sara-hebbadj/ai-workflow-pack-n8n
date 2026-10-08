// Runs when a person opens the approval link (?decision=approve or ?decision=reject).
// Sending is mocked: the "sent" email is one line in outputs/sent_emails.csv.
// @include csv.js
const SENT_COLUMNS = __CONST:workflow_pack.common.SENT_COLUMNS__;
const cfg = $('Config').first().json;
const item = $('Check draft').first().json;
const query = $input.first().json.query || {};
const approved = query.decision === 'approve';
const record = {
  timestamp: new Date().toISOString(),
  workflow: 'enquiry_intake',
  item_id: item.message_id,
  to: item.email.from_email,
  subject: item.draft_subject,
  status: approved ? 'sent (mock)' : 'rejected - not sent',
  detail: `decided by ${query.approver || 'unknown'}`,
};
return [{ json: { target_path: `${cfg.base_dir}/outputs/sent_emails.csv`, line: csvRow(SENT_COLUMNS, record) } }];
