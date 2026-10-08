// Render the "email" as Markdown and HTML: numbers table from code + narrative from the AI.
const cfg = $('Config').first().json;
const r = $input.first().json;
const n = r.numbers;
const one = (v) => Number(v).toFixed(1);
const rows = [
  ['Tickets this week', String(n.tickets_total)],
  ['Tickets last week', String(n.tickets_prev_week)],
  ['Change vs last week (%)', n.tickets_change_pct === null ? 'n/a' : one(n.tickets_change_pct)],
  ...Object.entries(n.tickets_by_priority).map(([p, c]) => [`${p} tickets`, String(c)]),
  ['SLA breaches (first response)', String(n.sla_breaches)],
  ['Negative sentiment (%)', one(n.negative_sentiment_pct)],
  ['Average first response (minutes)', one(n.avg_first_response_minutes)],
  ['Enquiries this week', String(n.enquiries_total)],
  ['Spam enquiries (%)', one(n.spam_pct)],
];
const escape = (s) => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#x27;');
const title = `Weekly operations report: ${n.week_start} to ${n.week_end}`;
const markdown = [
  `# ${title}`, '', `**${r.headline}**`, '', '| Metric | Value |', '|---|---|', ...rows.map(([k, v]) => `| ${k} | ${v} |`),
  '', '## Narrative (AI-written, numbers checked by code)', '', r.narrative.trim(), '',
].join('\n');
const bullets = r.narrative.split('\n').filter((l) => l.trim()).map((l) => `<li>${escape(l.replace(/^[-* ]+/, '').trim())}</li>`).join('');
const html = `<h1>${title}</h1><p><strong>${escape(r.headline)}</strong></p><table>${rows.map(([k, v]) => `<tr><td>${escape(k)}</td><td>${escape(v)}</td></tr>`).join('')}</table><ul>${bullets}</ul>`;
const dir = `${cfg.base_dir}/outputs/reports`;
return [
  { json: { ...r, target_path: `${dir}/weekly_${n.week_start}.md`, content: markdown } },
  { json: { ...r, target_path: `${dir}/weekly_${n.week_start}.html`, content: html } },
];
