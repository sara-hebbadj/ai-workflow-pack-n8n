// Second AI call: draft a reply. It is only a draft; a person approves it before anything is sent.
const cfg = $('Config').first().json;
const item = $input.first().json;
const email = item.email;
const user = JSON.stringify({
  category: item.category,
  email: {
    message_id: email.message_id || '', from_name: email.from_name || '', from_email: email.from_email || '',
    subject: email.subject || '', body: email.body || '',
  },
});
return [{
  json: {
    ...item,
    step: 'ai_draft',
    llm_request: {
      model: cfg.model_main,
      temperature: 0,
      response_format: { type: 'json_object' },
      messages: [{ role: 'system', content: cfg.prompt_draft }, { role: 'user', content: user }],
    },
  },
}];
