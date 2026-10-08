// Global safety net: n8n runs this workflow when any other workflow fails in a way its own
// error branch did not catch (for example a bug in a Code node).
// @include csv.js
const COLUMNS = __CONST:workflow_pack.common.ERROR_COLUMNS__;
const cfg = $('Config').first().json;
const e = $input.first().json;
const record = {
  timestamp: new Date().toISOString(),
  workflow: (e.workflow && e.workflow.name) || 'unknown',
  item_id: `execution ${(e.execution && e.execution.id) || '?'}`,
  step: (e.execution && e.execution.lastNodeExecuted) || 'unknown',
  error_type: (e.execution && e.execution.error && e.execution.error.name) || 'UnhandledError',
  message: String((e.execution && e.execution.error && e.execution.error.message) || 'unknown').slice(0, 500),
};
return [{ json: { target_path: `${cfg.base_dir}/logs/errors.csv`, line: csvRow(COLUMNS, record) } }];
