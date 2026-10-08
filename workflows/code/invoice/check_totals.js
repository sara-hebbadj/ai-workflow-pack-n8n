// The money checks are done in code, never by the AI:
// total = net + VAT, VAT = net x rate, a known VAT rate, no missing field, confidence high enough,
// and the same supplier + invoice number is never booked twice.
const FIELDS = __CONST:workflow_pack.invoice.FIELDS__;
const KNOWN_VAT_RATES = __CONST:workflow_pack.invoice.KNOWN_VAT_RATES__;
const cfg = $('Config').first().json;
const item = $input.first().json;
const tolerance = Number(cfg.money_tolerance) + 1e-9; // tiny extra margin for floating-point noise
const present = (v) => v !== null && v !== undefined && v !== '';
const normalise = (s) => String(s || '').trim().toLowerCase().replace(/\s+/g, ' ');

function validateFields(f) {
  const issues = FIELDS.filter((name) => !present(f[name])).map((name) => `missing ${name}`);
  const { net_amount: net, vat_amount: vat, total_amount: total, vat_rate: rate, currency } = f;
  if ([net, vat, total].every(present) && Math.abs(net + vat - total) > tolerance) issues.push('total does not equal net + VAT');
  if ([net, vat, rate].every(present) && Math.abs((net * rate) / 100 - vat) > tolerance) issues.push('VAT amount does not equal net x rate');
  if (present(rate) && KNOWN_VAT_RATES[currency] && !KNOWN_VAT_RATES[currency].includes(Number(rate))) issues.push(`unusual VAT rate ${rate}% for ${currency}`);
  return issues;
}

function decide(f, runTag) {
  if (f === null) return { status: 'needs_review', reasons: ['AI output failed the JSON schema check'] };
  const issues = validateFields(f);
  if (f.confidence < Number(cfg.invoice_min_confidence)) issues.push('low confidence');
  const supplier = normalise(f.supplier_name);
  const number = normalise(f.invoice_number);
  const key = supplier && number ? `${runTag}|invoice|${supplier}|${number}` : null;
  const store = $getWorkflowStaticData('global');
  store.booked = store.booked || {};
  if (key && store.booked[key]) return { status: 'duplicate', reasons: ['invoice number already booked for this supplier'] };
  if (issues.length) return { status: 'needs_review', reasons: issues };
  store.booked[key] = new Date().toISOString(); // only booked invoices are remembered
  return { status: 'accepted', reasons: [] };
}

const fields = item.ai ? Object.fromEntries([...FIELDS, 'confidence'].map((k) => [k, item.ai[k]])) : {};
return [{ json: { file_name: item.file_name, ...decide(item.ai, item.run_tag), fields } }];
