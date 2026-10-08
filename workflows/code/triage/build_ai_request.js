// Build the OpenAI-compatible request. The ticket goes in the user message as JSON data.
const cfg = $('Config').first().json;
const item = $input.first().json;
const t = item.ticket;
const user = JSON.stringify({ ticket_id: t.ticket_id, channel: t.channel || '', customer_tier: t.customer_tier || '', subject: t.subject || '', body: t.body });
return [{
  json: {
    ...item,
    step: 'ai_triage',
    llm_request: {
      model: cfg.model_cheap,
      temperature: 0,
      response_format: { type: 'json_object' },
      messages: [{ role: 'system', content: cfg.prompt_triage }, { role: 'user', content: user }],
    },
  },
}];
