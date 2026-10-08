// P1: alert the on-call person immediately (mock: a line in outputs/escalations.csv).
// @include csv.js
const COLUMNS = __CONST:workflow_pack.triage.ESCALATION_COLUMNS__;
const cfg = $('Config').first().json;
const r = $input.first().json;
const record = {
  timestamp: new Date().toISOString(), ticket_id: r.ticket_id, priority: 'P1', team: r.team,
  message: `@on-call P1 ticket ${r.ticket_id} for ${r.team}: ${r.summary}`,
};
return [{ json: { target_path: `${cfg.base_dir}/outputs/escalations.csv`, line: csvRow(COLUMNS, record) } }];
