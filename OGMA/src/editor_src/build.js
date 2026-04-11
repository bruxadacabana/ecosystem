const esbuild = require('esbuild')
const path    = require('path')
const fs      = require('fs')

const isWatch = process.argv.includes('--watch')

const outDir = path.join(__dirname, '..', 'editor', 'web')
fs.mkdirSync(outDir, { recursive: true })

const config = {
  entryPoints: [path.join(__dirname, 'src', 'editor_bundle.js')],
  bundle:      true,
  outfile:     path.join(outDir, 'editor.bundle.js'),
  format:      'iife',
  globalName:  'OgmaEditor',
  minify:      false,
  sourcemap:   false,
  target:      ['chrome114'],  // Electron 33 usa Chromium 130 ≈ Chrome 114+
  define: {
    'process.env.NODE_ENV': '"production"',
  },
}

if (isWatch) {
  esbuild.context(config).then(ctx => {
    ctx.watch()
    console.log('Editor.js watching for changes...')
  })
} else {
  esbuild.build(config)
    .then(() => console.log('✓ Editor.js bundle gerado em', config.outfile))
    .catch(e => { console.error(e); process.exit(1) })
}
