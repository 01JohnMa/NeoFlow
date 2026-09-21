from pathlib import Path

def replace(path, old, new):
    file = Path(path)
    text = file.read_text()
    assert text.count(old) == 1, (path, old[:80], text.count(old))
    file.write_text(text.replace(old, new))

# The fixture is outside Tailwind's production src scan; size the scroll host explicitly.
replace('web/e2e/extract-editor.tsx',
        '<aside className="w-60 shrink-0 border-r border-border-default p-6">',
        '<aside style={{ width: 240 }} className="shrink-0 border-r border-border-default p-6">')
replace('web/e2e/extract-editor.tsx',
        '<header className="h-16 border-b border-border-default px-6 py-5">',
        '<header style={{ height: 64 }} className="border-b border-border-default px-6 py-5">')
replace('web/e2e/extract-editor.tsx',
        '<main id="editor-scroll" className="h-[calc(100vh-4rem)] overflow-auto p-6">',
        '<main id="editor-scroll" style={{ height: "calc(100vh - 64px)", overflow: "auto" }} className="p-6">')
replace('web/e2e/extract-editor.cjs',
        "const { chromium } = require('playwright')",
        "const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright')")
replace('web/e2e/extract-editor.cjs',
        "'save bar remains in scroll viewport'",
        "`save bar remains in scroll viewport: ${JSON.stringify(box)}`")
replace('docs/extract-inline-editor.md',
        'npm install --no-save --package-lock=false playwright@1.56.1\nnpx playwright install chromium',
        'npm install --prefix /tmp/neoflow-editor-browser --no-save --package-lock=false playwright@1.56.1\n/tmp/neoflow-editor-browser/node_modules/.bin/playwright install chromium')
replace('docs/extract-inline-editor.md',
        'node e2e/extract-editor.cjs',
        'PLAYWRIGHT_MODULE=/tmp/neoflow-editor-browser/node_modules/playwright node e2e/extract-editor.cjs')
