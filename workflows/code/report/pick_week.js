// Which week to report on: the webhook can name one; the Monday schedule reports on last week.
const body = $input.first().json.body; // undefined when the schedule started the run
let weekStart = body ? body.week_start : null;
if (!weekStart) {
  const dubaiNow = new Date(Date.now() + 4 * 3600 * 1000); // Dubai is UTC+4 all year (no daylight saving)
  const daysSinceMonday = (dubaiNow.getUTCDay() + 6) % 7;
  const thisMonday = Date.UTC(dubaiNow.getUTCFullYear(), dubaiNow.getUTCMonth(), dubaiNow.getUTCDate() - daysSinceMonday);
  weekStart = new Date(thisMonday - 7 * 86400000).toISOString().slice(0, 10);
}
if (!/^\d{4}-\d{2}-\d{2}$/.test(String(weekStart))) throw new Error(`week_start ${weekStart} is not YYYY-MM-DD`);
if (new Date(`${weekStart}T00:00:00Z`).getUTCDay() !== 1) throw new Error(`week_start ${weekStart} is not a Monday`);
return [{ json: { week_start: weekStart, from_webhook: Boolean(body), step: 'read_data', dedupe_text: `${(body && body.run_tag) || ''}|${weekStart}` } }];
