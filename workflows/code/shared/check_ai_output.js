// JSON-schema check of the model's reply. Invalid output is never used: it goes to human review.
// @include schema.js
const SCHEMA = __SCHEMA__;
const { llm_request, ...context } = $('__REQUEST_NODE__').first().json;
const content = $input.first().json.choices?.[0]?.message?.content || '';
const ai = parseJsonObject(content);
const errors = schemaErrors(ai, SCHEMA);
return [{ json: { ...context, ai: errors.length ? null : ai, schema_errors: errors } }];
