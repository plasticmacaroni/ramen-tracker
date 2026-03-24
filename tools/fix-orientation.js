#!/usr/bin/env node
/**
 * Image orientation fixer using Tesseract.js OSD.
 *
 * Two modes:
 *
 * 1. Batch mode — scan directories:
 *    node fix-orientation.js images/ramen webp images/brand png
 *
 * 2. Server mode — read file paths from stdin, one per line:
 *    node fix-orientation.js --server
 *    (then write file paths to stdin, read JSON results from stdout)
 *
 * Output (both modes): JSON per image to stdout:
 *   {"file":"...","rotation":0,"status":"ok"}
 *   {"file":"...","rotation":90,"confidence":4.2,"status":"fixed"}
 *   {"file":"...","status":"skip","reason":"too small"}
 *   {"file":"...","status":"error","reason":"..."}
 */

const fs = require('fs');
const path = require('path');
const readline = require('readline');

const cacheModules = path.join(__dirname, '.cache', 'node_modules');
module.paths.unshift(cacheModules);

const { createWorker, PSM } = require('tesseract.js');

const MIN_DIMENSION = 50;
const MIN_CONFIDENCE = 2.0;

let worker = null;
let sharp = null;

async function init() {
  sharp = require('sharp');
  worker = await createWorker('osd', 0, {
    legacyCore: true,
    legacyLang: true,
  });
  await worker.setParameters({ tessedit_pageseg_mode: PSM.OSD_ONLY });
  process.stderr.write('Tesseract.js OSD worker ready.\n');
}

async function checkFile(file) {
  const result = { file: path.normalize(file) };
  try {
    if (!fs.existsSync(file)) {
      return { ...result, status: 'skip', reason: 'not found' };
    }

    const meta = await sharp(file).metadata();
    if (meta.width < MIN_DIMENSION || meta.height < MIN_DIMENSION) {
      return { ...result, status: 'skip', reason: 'too small' };
    }

    // Tesseract warns "invalid resolution 0 dpi" when WebP/JPEG lack density metadata.
    // Feed OSD a TIFF buffer with explicit DPI (in-memory only; original file unchanged).
    const osdInput = await sharp(file)
      .tiff({ compression: 'lzw', xres: 72, yres: 72, resolutionUnit: 'inch' })
      .toBuffer();

    const ret = await worker.detect(osdInput);
    const d = ret?.data;

    let rotation = 0;
    let confidence = 0;

    if (typeof d === 'string') {
      const om = d.match(/Orientation in degrees:\s*(\d+)/);
      const cm = d.match(/Orientation confidence:\s*([\d.]+)/);
      if (om) rotation = parseInt(om[1]);
      if (cm) confidence = parseFloat(cm[1]);
    } else if (d && typeof d === 'object') {
      rotation = d.orientation_degrees ?? d.rotate ?? 0;
      confidence = d.orientation_confidence ?? 0;
    }

    if (!rotation || rotation === 0 || confidence < MIN_CONFIDENCE) {
      return { ...result, rotation: 0, status: 'ok' };
    }

    const buf = await sharp(file).rotate(rotation).toBuffer();
    fs.writeFileSync(file, buf);

    return {
      ...result,
      rotation,
      confidence: Math.round(confidence * 10) / 10,
      status: 'fixed',
    };
  } catch (err) {
    return { ...result, status: 'error', reason: err.message };
  }
}

function respond(obj) {
  process.stdout.write(JSON.stringify(obj) + '\n');
}

// --- Batch mode ---

function collectFiles(args) {
  const files = [];
  let i = 0;
  while (i < args.length) {
    const dir = args[i];
    i++;
    const exts = [];
    while (i < args.length && !fs.existsSync(args[i])) {
      exts.push(args[i].toLowerCase().replace(/^\./, ''));
      i++;
    }
    if (!fs.existsSync(dir)) {
      process.stderr.write(`Directory not found: ${dir}\n`);
      continue;
    }
    for (const name of fs.readdirSync(dir)) {
      const ext = path.extname(name).slice(1).toLowerCase();
      if (exts.length === 0 || exts.includes(ext)) {
        files.push(path.join(dir, name));
      }
    }
  }
  return files;
}

async function batchMode(args) {
  const files = collectFiles(args);
  if (!files.length) {
    process.stderr.write('No image files found.\n');
    return;
  }
  process.stderr.write(`Checking ${files.length} images...\n`);
  let fixed = 0;
  for (let i = 0; i < files.length; i++) {
    if ((i + 1) % 50 === 0) process.stderr.write(`  ...${i + 1}/${files.length}\n`);
    const r = await checkFile(files[i]);
    respond(r);
    if (r.status === 'fixed') fixed++;
  }
  process.stderr.write(`Done: ${fixed} fixed out of ${files.length} checked.\n`);
}

// --- Server mode ---

async function serverMode() {
  const rl = readline.createInterface({ input: process.stdin });
  for await (const line of rl) {
    const file = line.trim();
    if (!file) continue;
    const r = await checkFile(file);
    respond(r);
  }
}

// --- Entry ---

async function main() {
  const args = process.argv.slice(2);
  await init();

  if (args[0] === '--server') {
    await serverMode();
  } else if (args.length > 0) {
    await batchMode(args);
  } else {
    process.stderr.write('Usage:\n  node fix-orientation.js --server\n  node fix-orientation.js <dir> [ext...]\n');
    process.exit(1);
  }

  await worker.terminate();
}

main().catch(err => {
  process.stderr.write(`Fatal: ${err.message}\n`);
  process.exit(1);
});
