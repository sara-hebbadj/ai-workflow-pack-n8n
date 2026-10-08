// Validate the incoming email. Throwing an error sends the item down the error branch.
const email = $('Webhook: new enquiry').first().json.body || {};
if (!String(email.body || '').trim()) throw new Error('missing email body');
if (!String(email.from_email || '').includes('@')) throw new Error('missing or invalid from_email');

// Deterministic tripwire for prompt injection (same patterns as the Python reference).
const INJECTION_PATTERNS = __CONST:workflow_pack.enquiry.INJECTION_PATTERNS__;
const text = `${email.subject || ''}\n${email.body}`;
const runTag = email.run_tag || '';
const keySource = email.message_id || `${email.from_email}|${email.subject || ''}|${email.body}`;
return [{
  json: {
    message_id: String(email.message_id || 'unknown'),
    email,
    injection_suspected: INJECTION_PATTERNS.some((pattern) => new RegExp(pattern, 'i').test(text)),
    dedupe_text: `${runTag}|${keySource}`,
  },
}];
