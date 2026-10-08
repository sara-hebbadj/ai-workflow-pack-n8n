// The AI never types a number. It writes placeholders such as {tickets_total} or {tickets_by_priority.P1};
// code fills them in from the computed numbers. If the AI typed a digit itself (other than the labels
// P1-P4) or used an unknown placeholder, the numbers still go out but the narrative is held for review.
const item = $input.first().json;
const numbers = item.numbers;
const PLACEHOLDER = /\{([a-z_]+(?:\.[A-Za-z0-9]+)?)\}/g;
const WITHHELD = __CONST:workflow_pack.report.WITHHELD__;

function lookup(path) {
  let value = numbers;
  for (const part of path.split('.')) {
    if (value === null || typeof value !== 'object' || !(part in value)) throw new Error(path);
    value = value[part];
  }
  if (value !== null && typeof value === 'object') throw new Error(path);
  return value;
}
// Python prints floats with one decimal and integers as they are; the JSON keeps that difference
// only through Number.isInteger, so the integer-valued metrics are listed explicitly.
const FLOAT_KEYS = ['tickets_change_pct', 'negative_sentiment_pct', 'avg_first_response_minutes', 'spam_pct'];
function formatValue(path, value) {
  if (value === null) return 'n/a';
  return FLOAT_KEYS.includes(path) ? Number(value).toFixed(1) : String(value);
}
// {tickets_change_pct} is signed: "fell by {tickets_change_pct}%" would print "fell by -22.4%".
const CHANGE_DOWN = new RegExp(__CONST:workflow_pack.report.CHANGE_DOWN_PATTERN__, 'i');
const CHANGE_UP = new RegExp(__CONST:workflow_pack.report.CHANGE_UP_PATTERN__, 'i');
function changeWordingProblems(text) {
  const change = numbers.tickets_change_pct;
  if (CHANGE_DOWN.test(text)) return ["a 'fell/down' word is placed before the signed {tickets_change_pct}"];
  if ((change === null || change === undefined || change < 0) && CHANGE_UP.test(text)) {
    return ["a 'rose/up' word is placed before {tickets_change_pct}, which is not an increase"];
  }
  return [];
}
function checkNarrative(text) {
  const problems = [];
  for (const match of text.matchAll(PLACEHOLDER)) {
    try { lookup(match[1]); } catch (unknown) { problems.push(`unknown placeholder {${match[1]}}`); }
  }
  const typed = text.replace(PLACEHOLDER, ' ').replace(/\bP[1-4]\b/g, ' ').match(/[0-9]+/g) || [];
  if (typed.length) problems.push(`AI typed numbers itself: ${typed.join(', ')}`);
  problems.push(...changeWordingProblems(text));
  if (problems.length) return { text, problems };
  return { text: text.replace(PLACEHOLDER, (m, path) => formatValue(path, lookup(path))), problems };
}

let problems = item.ai === null ? ['AI output failed the JSON schema check'] : [];
let headline = 'Weekly numbers (narrative held for review)';
let narrative = WITHHELD;
if (item.ai !== null) {
  const h = checkNarrative(item.ai.headline);
  const n = checkNarrative(item.ai.narrative);
  problems = [...h.problems, ...n.problems];
  if (!problems.length) { headline = h.text; narrative = n.text; }
}
const ok = problems.length === 0;
return [{ json: { ...item, status: ok ? 'sent' : 'needs_review', reason: problems.join('; '), headline, narrative } }];
