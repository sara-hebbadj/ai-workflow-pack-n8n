// CSV helpers: one line per record, quoted only when needed (same rule as Python's csv module).
function csvCell(value) {
  if (value === null || value === undefined) return '';
  const text = typeof value === 'object' ? JSON.stringify(value) : String(value);
  return /[",\n\r]/.test(text) ? '"' + text.replace(/"/g, '""') + '"' : text;
}
function csvRow(columns, record) {
  return columns.map((column) => csvCell(record[column])).join(',') + '\n';
}
