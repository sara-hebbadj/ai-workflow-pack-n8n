// Run one Code node from an exported n8n workflow outside n8n, for tests.
//
//   node scripts/run_code_node.js <workflow.json> "<node name>" < context.json
//
// context.json: { "input": [json, ...], "nodes": { "Config": [json, ...], ... }, "staticData": {} }
// Prints { "output": [json, ...], "staticData": {...} }. Only the n8n helpers our scripts use are provided.
const fs = require('fs');

const [workflowPath, nodeName] = process.argv.slice(2);
const workflow = JSON.parse(fs.readFileSync(workflowPath, 'utf8'));
const node = workflow.nodes.find((n) => n.name === nodeName);
if (!node) throw new Error(`node "${nodeName}" not found in ${workflowPath}`);
const context = JSON.parse(fs.readFileSync(0, 'utf8'));

const toItems = (list) => (list || []).map((json) => ({ json }));
const input = toItems(context.input);
const staticData = context.staticData || {};
const $input = { all: () => input, first: () => input[0], last: () => input[input.length - 1] };
const $ = (name) => {
  if (!(name in (context.nodes || {}))) throw new Error(`node "${name}" has not been executed`);
  const items = toItems(context.nodes[name]);
  return { all: () => items, first: () => items[0], item: items[0] };
};
const $getWorkflowStaticData = () => staticData;
const $execution = { id: 'test', resumeUrl: 'http://localhost:5678/webhook-waiting/test?signature=abc' };

const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor;
const run = new AsyncFunction('$input', '$', '$getWorkflowStaticData', '$execution', node.parameters.jsCode);
run($input, $, $getWorkflowStaticData, $execution)
  .then((items) => process.stdout.write(JSON.stringify({ output: items.map((i) => i.json), staticData })))
  .catch((error) => {
    process.stdout.write(JSON.stringify({ error: String(error.message || error) }));
  });
