// Parse the model's reply and check it against a JSON Schema (the subset our schemas use).
function parseJsonObject(text) {
  if (!text) return null;
  const start = text.indexOf('{');
  const end = text.lastIndexOf('}');
  if (start === -1 || end <= start) return null;
  try {
    const value = JSON.parse(text.slice(start, end + 1));
    return value && typeof value === 'object' && !Array.isArray(value) ? value : null;
  } catch (error) {
    return null;
  }
}
function isType(value, type) {
  if (type === 'null') return value === null;
  if (type === 'number') return typeof value === 'number' && Number.isFinite(value);
  if (type === 'integer') return Number.isInteger(value);
  if (type === 'object') return value !== null && typeof value === 'object' && !Array.isArray(value);
  if (type === 'array') return Array.isArray(value);
  return typeof value === type;
}
function schemaErrors(value, schema, path = '$') {
  if (value === null && path === '$') return ['output is not a JSON object'];
  const types = [].concat(schema.type || []);
  if (types.length && !types.some((type) => isType(value, type))) return [`${path}: expected ${types.join(' or ')}`];
  const errors = [];
  if (schema.enum && !schema.enum.includes(value)) errors.push(`${path}: must be one of ${JSON.stringify(schema.enum)}`);
  if (typeof value === 'number') {
    if (schema.minimum !== undefined && value < schema.minimum) errors.push(`${path}: below ${schema.minimum}`);
    if (schema.maximum !== undefined && value > schema.maximum) errors.push(`${path}: above ${schema.maximum}`);
  }
  if (typeof value === 'string') {
    if (schema.maxLength !== undefined && value.length > schema.maxLength) errors.push(`${path}: longer than ${schema.maxLength}`);
    if (schema.pattern && !new RegExp(schema.pattern).test(value)) errors.push(`${path}: does not match ${schema.pattern}`);
  }
  if (isType(value, 'object')) {
    const properties = schema.properties || {};
    for (const key of schema.required || []) if (!(key in value)) errors.push(`${path}.${key}: missing`);
    for (const [key, sub] of Object.entries(properties)) if (key in value) errors.push(...schemaErrors(value[key], sub, `${path}.${key}`));
    if (schema.additionalProperties === false) {
      for (const key of Object.keys(value)) if (!(key in properties)) errors.push(`${path}.${key}: not allowed`);
    }
  }
  return errors;
}
