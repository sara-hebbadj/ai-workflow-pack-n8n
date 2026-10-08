// Invoice register row (every file) + the shared human-check queue for anything doubtful.
// Reached from "Check totals & VAT", or directly when no text was found in the file.
// @include csv.js
const REGISTER_COLUMNS = __CONST:workflow_pack.invoice.REGISTER_COLUMNS__;
const REVIEW_COLUMNS = __CONST:workflow_pack.common.REVIEW_COLUMNS__;
const cfg = $('Config').first().json;
const incoming = $input.first().json;
const r = incoming.status ? incoming : { file_name: incoming.file_name, status: 'needs_review', reasons: ['no text found (scanned image? needs OCR)'], fields: {} };
const now = new Date().toISOString();
const reasons = r.reasons.join('; ');
const rows = [{ target_path: `${cfg.base_dir}/outputs/invoice_register.csv`, line: csvRow(REGISTER_COLUMNS, { ...r.fields, ...r, timestamp: now, reasons }) }];
if (r.status === 'needs_review') {
  const review = { timestamp: now, workflow: 'invoice_extraction', item_id: r.file_name, reason: reasons, details: r.fields };
  rows.push({ target_path: `${cfg.base_dir}/outputs/human_review_queue.csv`, line: csvRow(REVIEW_COLUMNS, review) });
}
const response = { file_name: r.file_name, status: r.status, reasons: r.reasons, fields: r.fields };
return rows.map((row) => ({ json: { ...row, response } }));
