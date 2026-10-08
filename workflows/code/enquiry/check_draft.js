// JSON-schema check of the draft. A broken draft goes to human review instead of the approval queue.
// @include schema.js
const SCHEMA = __SCHEMA:enquiry_draft__;
const { llm_request, ...item } = $('Build draft request').first().json;
const draft = parseJsonObject($input.first().json.choices?.[0]?.message?.content || '');
if (schemaErrors(draft, SCHEMA).length) {
  return [{ json: { ...item, status: 'needs_review', reason: 'draft reply failed the JSON schema check' } }];
}
return [{ json: { ...item, status: 'pending_approval', draft_subject: draft.reply_subject, draft_body: draft.reply_body } }];
