// Idempotency: the same input twice must not create two records.
// Keys live in this workflow's static data (n8n saves it after production runs, not manual test runs).
const item = $input.first().json;
const key = item.dedupe_key || item.dedupe_text;
const store = $getWorkflowStaticData('global');
store.seen = store.seen || {};
const duplicate = Boolean(store.seen[key]);
if (!duplicate) store.seen[key] = new Date().toISOString();
const json = { ...item, dedupe_key: key, is_duplicate: duplicate };
const binary = __BINARY_SOURCE__; // invoices carry the uploaded file along
return [binary ? { json, binary } : { json }];
