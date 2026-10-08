// Build the extraction request from the text of the file (PDF or .txt branch).
const cfg = $('Config').first().json;
const seen = $('Seen before?').first().json;
const text = String($input.first().json.text || '');
return [{
  json: {
    file_name: seen.file_name,
    run_tag: seen.run_tag,
    dedupe_key: seen.dedupe_key,
    has_text: text.trim().length > 0,
    step: 'ai_extract',
    llm_request: {
      model: cfg.model_cheap,
      temperature: 0,
      response_format: { type: 'json_object' },
      messages: [{ role: 'system', content: cfg.prompt_extract }, { role: 'user', content: JSON.stringify({ file_name: seen.file_name, text }) }],
    },
  },
}];
