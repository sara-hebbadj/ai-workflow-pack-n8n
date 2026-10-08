// Build the OpenAI-compatible request. The email goes in the user message as JSON data.
const cfg = $('Config').first().json;
const item = $input.first().json;
const email = item.email;
const user = JSON.stringify({
  message_id: email.message_id || '', from_name: email.from_name || '', from_email: email.from_email || '',
  subject: email.subject || '', body: email.body || '',
});
return [{
  json: {
    ...item,
    step: 'ai_classify',
    llm_request: {
      model: cfg.model_cheap,
      temperature: 0,
      response_format: { type: 'json_object' },
      messages: [{ role: 'system', content: cfg.prompt_classify }, { role: 'user', content: user }],
    },
  },
}];
