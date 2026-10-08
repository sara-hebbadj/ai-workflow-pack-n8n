// Validate the uploaded file (multipart field "file"). Throwing sends it to the error branch.
const upload = $('Webhook: invoice file').first();
const file = (upload.binary || {}).file;
if (!file) throw new Error('no file uploaded (send it as the multipart field "file")');
const fileName = file.fileName || 'unknown';
const extension = (fileName.split('.').pop() || '').toLowerCase();
if (!['pdf', 'txt'].includes(extension)) throw new Error(`unsupported file type .${extension}`);
const runTag = (upload.json.body || {}).run_tag || '';
// step tells the error branch what failed if text extraction breaks (e.g. a corrupt PDF)
return [{ json: { file_name: fileName, is_pdf: extension === 'pdf', run_tag: runTag, step: 'extract_text' }, binary: upload.binary }];
