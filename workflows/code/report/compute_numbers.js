// Every number in the report is computed here, in code. The AI never does arithmetic.
// Rounding uses integer maths so the result is identical to the Python reference.
const PRIORITIES = __CONST:workflow_pack.report.PRIORITIES__;
const TEAMS = __CONST:workflow_pack.report.TEAMS__;
const CATEGORIES = __CONST:workflow_pack.report.CATEGORIES__;
const SLA_MINUTES = __CONST:workflow_pack.report.SLA_MINUTES__;
const cfg = $('Config').first().json;
const week = $('Seen before?').first().json;
const tickets = $('Parse tickets CSV').all().map((i) => i.json);
const enquiries = $('Parse enquiries CSV').all().map((i) => i.json);

const addDays = (iso, n) => new Date(Date.parse(`${iso}T00:00:00Z`) + n * 86400000).toISOString().slice(0, 10);
const pct = (part, whole) => (whole === 0 ? 0 : Math.floor((2000 * part + whole) / (2 * whole)) / 10);
const avg1 = (total, count) => (count === 0 ? 0 : Math.floor((20 * total + count) / (2 * count)) / 10);
const changePct = (cur, prev) => (prev === 0 ? null : (cur < prev ? -1 : 1) * pct(Math.abs(cur - prev), prev));
// Timestamps are stored in Dubai local time (+04:00), so the first 10 characters are the local date.
const inWeek = (ts, start, end) => start <= String(ts).slice(0, 10) && String(ts).slice(0, 10) <= end;
const countBy = (rows, field, keys) => Object.fromEntries(keys.map((k) => [k, rows.filter((r) => r[field] === k).length]));

const start = week.week_start;
const end = addDays(start, 6);
const current = tickets.filter((t) => inWeek(t.created_at, start, end));
const previousCount = tickets.filter((t) => inWeek(t.created_at, addDays(start, -7), addDays(start, -1))).length;
const weekEnquiries = enquiries.filter((e) => inWeek(e.received_at, start, end));
const minutes = current.map((t) => Number(t.first_response_minutes));
const numbers = {
  week_start: start,
  week_end: end,
  tickets_total: current.length,
  tickets_prev_week: previousCount,
  tickets_change_pct: changePct(current.length, previousCount),
  tickets_by_priority: countBy(current, 'priority', PRIORITIES),
  tickets_by_team: countBy(current, 'team', TEAMS),
  negative_sentiment_pct: pct(current.filter((t) => t.sentiment === 'negative').length, current.length),
  avg_first_response_minutes: avg1(minutes.reduce((a, b) => a + b, 0), minutes.length),
  sla_breaches: current.filter((t) => Number(t.first_response_minutes) > SLA_MINUTES[t.priority]).length,
  enquiries_total: weekEnquiries.length,
  enquiries_by_category: countBy(weekEnquiries, 'category', CATEGORIES),
  spam_pct: pct(weekEnquiries.filter((e) => e.category === 'spam').length, weekEnquiries.length),
};
return [{
  json: {
    ...week,
    numbers,
    step: 'ai_narrative',
    llm_request: {
      model: cfg.model_main,
      temperature: 0,
      response_format: { type: 'json_object' },
      messages: [{ role: 'system', content: cfg.prompt_narrative }, { role: 'user', content: JSON.stringify(numbers) }],
    },
  },
}];
