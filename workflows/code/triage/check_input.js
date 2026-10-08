// Validate the ticket and run the safety net (keywords that always mean P1).
const ticket = $('Webhook: new ticket').first().json.body || {};
if (!ticket.ticket_id) throw new Error('missing ticket_id');
if (!String(ticket.body || '').trim()) throw new Error('missing ticket body');

const SAFETY_PATTERNS = __CONST:workflow_pack.triage.SAFETY_PATTERNS__;
const text = `${ticket.subject || ''}\n${ticket.body}`;
let safetyKeyword = '';
for (const pattern of SAFETY_PATTERNS) {
  const match = text.match(new RegExp(pattern, 'i'));
  if (match) { safetyKeyword = match[0]; break; }
}
return [{
  json: { ticket_id: String(ticket.ticket_id), ticket, safety_keyword: safetyKeyword, dedupe_text: `${ticket.run_tag || ''}|${ticket.ticket_id}` },
}];
