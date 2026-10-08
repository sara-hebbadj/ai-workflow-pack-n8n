// Business rules in code: the AI only labels the email, code decides what happens next.
const TEAM_BY_CATEGORY = __CONST:workflow_pack.enquiry.TEAM_BY_CATEGORY__;
const cfg = $('Config').first().json;
const item = $input.first().json;
const ai = item.ai;

function route(ai, injection, threshold) {
  if (ai === null) return { status: 'needs_review', reason: 'AI output failed the JSON schema check', team: 'Review queue' };
  const team = TEAM_BY_CATEGORY[ai.category];
  const flag = ai.category === 'complaint' && ai.urgency === 'high' ? 'manager_cc' : '';
  if (injection) return { status: 'needs_review', reason: 'possible prompt injection', team, flag };
  if (ai.category === 'spam') return { status: 'archived_spam', reason: 'spam: no reply drafted', team, flag };
  if (ai.confidence < threshold) return { status: 'needs_review', reason: 'low confidence', team, flag };
  return { status: 'to_draft', reason: '', team, flag };
}

return [{ json: { ...item, ...(ai || {}), ...route(ai, item.injection_suspected, Number(cfg.confidence_threshold)) } }];
