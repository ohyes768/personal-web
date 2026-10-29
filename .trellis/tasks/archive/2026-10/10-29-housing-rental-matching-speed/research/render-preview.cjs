// Isolated layout fixture using the real component and stylesheet; no production API.
const fs = require('node:fs');
const path = require('node:path');
const { createRequire } = require('node:module');
const root = path.resolve(__dirname, '../../../..');
const app = path.join(root, 'apps/housing-map');
const req = createRequire(path.join(app, 'package.json'));
const ts = req('typescript');
const React = req('react');
for (const ext of ['.ts', '.tsx']) require.extensions[ext] = (module, filename) => module._compile(ts.transpileModule(fs.readFileSync(filename, 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX }
}).outputText, filename);
const { CollectionControls } = req('./src/components/community/DirectoryFlowWorkspace.tsx');
const css = fs.readFileSync(path.join(app, 'src/app/globals.css'), 'utf8').replace('@import "tailwindcss";', '');
const variants = {
  idle: { running: false, phase: 'cancelled', mode: 'incremental', incremental_count: 58,
    processed: 35, total: 93, association: { checked: 35, matched: 22, pending: 10, missing: 3, deferred: 58 } },
  running: { running: true, phase: 'running', mode: 'incremental', incremental_count: 58,
    processed: 35, total: 93, current_community_name: '测试花园', current_step: 'homepage',
    diagnostics: { requests: 4, cache_hits: 2 } },
  empty: { running: false, phase: 'done', mode: 'incremental', incremental_count: 0 }
};
for (const [name, job] of Object.entries(variants)) {
  const html = req('react-dom/server').renderToStaticMarkup(React.createElement(CollectionControls, {
    active: true, busy: false, open: true, jobs: { rentalMatch: job }, errors: {}, action() {}
  }));
  fs.writeFileSync(path.join(__dirname, `preview-${name}.html`), `<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>来源匹配隔离布局验证</title><style>${css}</style><body>${html}<script>document.querySelector('dialog').showModal();document.querySelector('section').scrollIntoView({block:'center'});</script></body></html>`);
}
