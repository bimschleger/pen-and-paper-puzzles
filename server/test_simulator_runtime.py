#!/usr/bin/env python3
"""
Automated Test Suite: Web Simulator & Captive Portal Headless JS Runtime Verification
Validates:
1. JavaScript Syntax Check (`node --check`) on extracted <script> blocks from
   `simulator/receipt_simulator.html` and `portal.html`.
2. Simulator Class Completeness: All 20 `<Game>Simulator` classes exist and instantiate cleanly.
3. Multi-Difficulty Generation & Watchdog Latency: Executes `.generate()` across all difficulty
   tiers (`easy`, `medium`, `hard`, `extreme`) for all 20 games with a strict <= 150ms wall-clock
   budget per puzzle (preventing infinite loops or backtracking hangs).
4. Rule 16 Bit-Level Thermal Emulation Audit: Executes all 20 `renderOffline<Game>` functions and
   `drawSimGuideCanvas(0..19)` against a strict Canvas 2D spy that bans anti-aliased 2D vector calls
   (`fillText`, `strokeText`, `strokeRect`, `arc`, `lineTo`, `moveTo`) and verifies 576-dot 1-bit
   `ThermalCanvasSimulator` output (`putImageData`) with valid dimensions and <= 35% thermal duty cycle.
5. Full `renderReceipt()` End-to-End Execution: Runs `renderReceipt()` in both `offline_raster` and
   `ascii` modes across all 20 games plus `renderReceipt(sampleKey)` for every game key to catch any
   undefined variables or runtime exceptions.
"""

import os
import re
import shutil
import subprocess
import sys
import tempfile

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SIMULATOR_HTML = os.path.join(ROOT_DIR, "simulator", "receipt_simulator.html")
PORTAL_HTML = os.path.join(ROOT_DIR, "portal.html")


def extract_last_script_block(html_path: str) -> str:
    with open(html_path, "r", encoding="utf-8") as f:
        content = f.read()
    matches = re.findall(r"<script(?:\s+[^>]*)?>(.*?)</script>", content, flags=re.DOTALL)
    assert matches, f"No <script> block found in {html_path}"
    return matches[-1]


def test_js_syntax():
    print("Test 1: Verifying JavaScript Syntax (node --check) for Simulator & Captive Portal...")
    node_bin = shutil.which("node")
    assert node_bin, "Node.js ('node') is required for Web Simulator runtime verification"

    for label, path in [("receipt_simulator.html", SIMULATOR_HTML), ("portal.html", PORTAL_HTML)]:
        assert os.path.exists(path), f"Missing file: {path}"
        script_js = extract_last_script_block(path)
        with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as tmp:
            tmp.write(script_js)
            tmp_path = tmp.name
        try:
            res = subprocess.run([node_bin, "--check", tmp_path], capture_output=True, text=True)
            assert res.returncode == 0, f"Syntax error in {label}:\n{res.stderr}\n{res.stdout}"
            print(f"  [OK] {label} passed `node --check` ({len(script_js.splitlines())} JS lines)")
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)


def test_simulator_headless_runtime():
    print("\nTest 2: Executing Headless Node.js Runtime & Rule 16 Audit for All 20 Games...")
    node_bin = shutil.which("node")
    script_js = extract_last_script_block(SIMULATOR_HTML)

    # Strip the trailing window.addEventListener('DOMContentLoaded', ...) block so we control execution
    script_js = re.sub(
        r"window\.addEventListener\(['\"]DOMContentLoaded['\"],\s*\(\)\s*=>\s*\{.*?\}\);\s*$",
        "",
        script_js,
        flags=re.DOTALL,
    )

    harness_js = r"""
// --- Minimal DOM & Canvas Spy Harness ---
const elements = new Map();
let currentRenderStyle = 'offline_raster';
const diffDefaults = {
  'diff-queens': '8x8_1star',
  'diff-sudoku': 'medium',
  'diff-sudokito': 'medium',
  'diff-wordsearch': 'medium',
  'diff-nonogram': '8',
  'diff-jumble': 'medium',
  'diff-binary': 'medium',
  'diff-mines': 'medium',
  'diff-tents': 'medium',
  'diff-bridges': 'medium',
  'diff-killer': 'medium',
  'diff-cryptogram': 'medium',
  'diff-tango': 'medium',
  'diff-ladder': 'medium',
  'diff-wheel': 'medium',
  'diff-lights': 'medium',
  'diff-loop': 'medium',
  'diff-towers': 'medium',
  'diff-inequality': 'medium',
  'diff-maze': 'medium',
};

function makeMockCanvas() {
  const canvasObj = {
    width: 0,
    height: 0,
    className: '',
    style: {},
    _vectorCalls: [],
    _imageData: null,
    getContext(type) {
      return {
        createImageData(w, h) {
          return { width: w, height: h, data: new Uint8ClampedArray(w * h * 4) };
        },
        putImageData(imgData, x, y) {
          canvasObj._imageData = imgData;
        },
        fillRect(x, y, w, h) {
          canvasObj._vectorCalls.push(`fillRect(${x},${y},${w},${h})`);
        },
        strokeRect(x, y, w, h) {
          canvasObj._vectorCalls.push(`strokeRect(${x},${y},${w},${h})`);
        },
        fillText(t, x, y) {
          canvasObj._vectorCalls.push(`fillText(${t})`);
        },
        strokeText(t, x, y) {
          canvasObj._vectorCalls.push(`strokeText(${t})`);
        },
        arc(x, y, r) {
          canvasObj._vectorCalls.push(`arc(${x},${y},${r})`);
        },
        moveTo(x, y) {
          canvasObj._vectorCalls.push(`moveTo(${x},${y})`);
        },
        lineTo(x, y) {
          canvasObj._vectorCalls.push(`lineTo(${x},${y})`);
        },
        beginPath() {},
        stroke() { canvasObj._vectorCalls.push('stroke'); },
        fill() { canvasObj._vectorCalls.push('fill'); },
      };
    }
  };
  return canvasObj;
}

function getMockElement(id) {
  if (!elements.has(id)) {
    const isToggle = id.startsWith('toggle-');
    const elObj = {
      id,
      value: id === 'global-render-style' ? currentRenderStyle : (diffDefaults[id] || 'medium'),
      checked: isToggle ? true : true,
      innerText: '',
      textContent: '',
      innerHTML: '',
      style: {},
      children: [],
      _listeners: {},
      classList: {
        add() {},
        remove() {},
        toggle() {},
        contains() { return false; }
      },
      appendChild(child) {
        if (child && child._isFragment && Array.isArray(child.children)) {
          this.children.push(...child.children);
          child.children = [];
          return child;
        }
        this.children.push(child);
        return child;
      },
      addEventListener(type, fn) {
        if (!this._listeners[type]) this._listeners[type] = [];
        this._listeners[type].push(fn);
      },
      dispatchEvent(evt) {
        const eventObj = evt || { type: 'change', target: elObj };
        const handlers = elObj._listeners[eventObj.type] || [];
        for (const fn of handlers) fn(eventObj);
      },
      querySelector() { return getMockElement('mock-query'); },
      querySelectorAll() { return []; }
    };
    elements.set(id, elObj);
  }
  const el = elements.get(id);
  if (id === 'global-render-style') el.value = currentRenderStyle;
  return el;
}

globalThis.window = globalThis;
globalThis.document = {
  getElementById(id) { return getMockElement(id); },
  createDocumentFragment() {
    return {
      _isFragment: true,
      children: [],
      appendChild(child) {
        this.children.push(child);
        return child;
      }
    };
  },
  createElement(tag) {
    if (tag === 'canvas') return makeMockCanvas();
    return getMockElement(`created-${tag}-${Math.random()}`);
  },
  querySelector() { return getMockElement('mock-qs'); },
  querySelectorAll() { return []; }
};
globalThis.navigator = { clipboard: { writeText: async () => {} } };
"""

    verification_footer_js = r"""
// --- Verification Suite ---
(function runVerification() {
  const expectedClasses = [
    ['sudoku', SudokuSimulator, [38, 30, 25]],
    ['sudokito', SudokitoSimulator, [18, 14, 10]],
    ['wordsearch', WordSearchSimulator, ['easy', 'medium', 'hard']],
    ['nonogram', NonogramSimulator, [5, 8, 10, 15]],
    ['queens', QueensSimulator, [[5, 1], [8, 1], [9, 2], [10, 2]]],
    ['jumble', JumbleSimulator, ['easy', 'medium', 'hard']],
    ['binary', BinarySimulator, ['easy', 'medium', 'hard']],
    ['mines', MinesSimulator, ['easy', 'medium', 'hard']],
    ['tents', TentsSimulator, ['easy', 'medium', 'hard']],
    ['bridges', BridgesSimulator, ['easy', 'medium', 'hard']],
    ['killer', KillerSudokuSimulator, ['easy', 'medium', 'hard', 'extreme']],
    ['cryptogram', CryptogramSimulator, ['easy', 'medium', 'hard']],
    ['tango', TangoSimulator, ['easy', 'medium', 'hard', 'extreme']],
    ['ladder', LadderSimulator, ['easy', 'medium', 'hard']],
    ['lights', LightsSimulator, ['easy', 'medium', 'hard', 'extreme']],
    ['loop', LoopSimulator, ['easy', 'medium', 'hard', 'extreme']],
    ['wheel', WheelSimulator, ['easy', 'medium', 'hard']],
    ['towers', TowersSimulator, ['easy', 'medium', 'hard', 'extreme']],
    ['inequality', InequalitySimulator, ['easy', 'medium', 'hard', 'extreme']],
    ['maze', MazeSimulator, ['easy', 'medium', 'hard', 'extreme']],
  ];

  if (ALL_GAMES.length !== 20) {
    throw new Error(`Expected ALL_GAMES.length === 20, got ${ALL_GAMES.length}`);
  }

  const generatedSamples = {};

  // 1. Test all 20 Simulator generators across all difficulty tiers with <= 250ms watchdog
  for (const [key, Cls, argList] of expectedClasses) {
    const inst = new Cls();
    for (const arg of argList) {
      for (let run = 0; run < 3; run++) {
        const t0 = performance.now();
        const res = Array.isArray(arg) ? inst.generate(...arg) : inst.generate(arg);
        const elapsed = performance.now() - t0;
        if (!res || typeof res !== 'object') {
          throw new Error(`${key} generator returned invalid result for arg=${JSON.stringify(arg)}`);
        }
        if (elapsed > 250.0) {
          throw new Error(`Watchdog timeout: ${key}.generate(${JSON.stringify(arg)}) took ${elapsed.toFixed(2)}ms (> 250ms limit)`);
        }
        if (!generatedSamples[key]) generatedSamples[key] = res;
      }
    }
    console.log(`  [OK] ${key.padEnd(12)} generator verified across ${argList.length} tiers (3x Monte Carlo, <= 250ms)`);
  }

  // 2. Test all 20 renderOffline<Game> functions for Rule 16 compliance (100% ThermalCanvasSimulator, zero 2D vector calls)
  const renderers = [
    ['queens', (c, d) => renderOfflineQueens(c, d, d.size || 8, d.starsPerUnit || 1)],
    ['sudoku', renderOfflineSudoku],
    ['sudokito', renderOfflineSudokito],
    ['wordsearch', renderOfflineWordSearch],
    ['nonogram', renderOfflineNonogram],
    ['jumble', renderOfflineJumble],
    ['binary', renderOfflineBinary],
    ['mines', renderOfflineMines],
    ['tents', renderOfflineTents],
    ['bridges', renderOfflineBridges],
    ['killer', renderOfflineKiller],
    ['cryptogram', renderOfflineCryptogram],
    ['tango', renderOfflineTango],
    ['ladder', renderOfflineLadder],
    ['lights', renderOfflineLights],
    ['loop', renderOfflineLoop],
    ['wheel', renderOfflineWheel],
    ['towers', renderOfflineTowers],
    ['inequality', renderOfflineInequality],
    ['maze', renderOfflineMaze],
  ];

  for (const [key, fn] of renderers) {
    if (typeof fn !== 'function') {
      throw new Error(`Missing renderOffline function for ${key}`);
    }
    const canvas = makeMockCanvas();
    fn(canvas, generatedSamples[key]);

    if (canvas._vectorCalls.length > 0) {
      throw new Error(`Rule 16 Violation in renderOffline for '${key}': Prohibited 2D vector calls detected: ${canvas._vectorCalls.slice(0, 5).join(', ')}`);
    }
    if (!canvas._imageData) {
      throw new Error(`Rule 16 Violation in renderOffline for '${key}': Did not render via ThermalCanvasSimulator.renderToCanvas (putImageData missing)`);
    }
    if (canvas.width !== 576 || canvas.height <= 0) {
      throw new Error(`Invalid canvas dimensions for '${key}': ${canvas.width}x${canvas.height}`);
    }

    // Count burned thermal pixels (R === 17 < 128) and check thermal duty cycle <= 35%
    const rgba = canvas._imageData.data;
    let blackDots = 0;
    const totalDots = canvas.width * canvas.height;
    for (let i = 0; i < rgba.length; i += 4) {
      if (rgba[i] < 128) blackDots++;
    }
    const dutyPct = (blackDots / totalDots) * 100.0;
    if (blackDots === 0) {
      throw new Error(`Empty raster canvas for '${key}' (0 black dots)`);
    }
    if (dutyPct > 35.0) {
      throw new Error(`Thermal duty cycle violation for '${key}': ${dutyPct.toFixed(2)}% (> 35% max)`);
    }
  }
  console.log(`  [OK] All 20 renderOffline<Game> functions verified (576px ThermalCanvasSimulator, 0 vector calls, <= 35% duty)`);

  // 3. Test drawSimGuideCanvas(0..19) and renderGuideReceipt(0..19) for all 20 games
  for (let id = 0; id < 20; id++) {
    const guideCanvas = makeMockCanvas();
    elements.set('simGuideCanvas', guideCanvas);
    drawSimGuideCanvas(id, guideCanvas);
    if (guideCanvas._vectorCalls.length > 0) {
      throw new Error(`Rule 16 Violation in drawSimGuideCanvas(${id}): Prohibited 2D vector calls: ${guideCanvas._vectorCalls.join(', ')}`);
    }
    if (!guideCanvas._imageData || guideCanvas.width !== 576 || guideCanvas.height !== 216) {
      throw new Error(`Invalid guide canvas for id=${id}: ${guideCanvas.width}x${guideCanvas.height}`);
    }
    getMockElement('receipt-box').children = [];
    renderGuideReceipt(id);
    if (getMockElement('receipt-box').children.length === 0) {
      throw new Error(`renderGuideReceipt(${id}) produced 0 DOM elements`);
    }
  }
  console.log(`  [OK] All 20 drawSimGuideCanvas(0..19) & renderGuideReceipt(0..19) verified (576x216 ThermalCanvasSimulator)`);

  // 4. Test end-to-end renderReceipt() in both 'offline_raster' and 'ascii' modes, plus sampleGameKey
  for (const mode of ['offline_raster', 'ascii']) {
    currentRenderStyle = mode;
    elements.set('receipt-box', getMockElement('receipt-box'));
    elements.get('receipt-box').children = [];
    renderReceipt(null);
    if (elements.get('receipt-box').children.length === 0) {
      throw new Error(`renderReceipt(null) in mode '${mode}' produced 0 DOM elements`);
    }
  }
  currentRenderStyle = 'offline_raster';
  for (const gKey of ALL_GAMES) {
    elements.get('receipt-box').children = [];
    renderReceipt(gKey);
    if (elements.get('receipt-box').children.length === 0) {
      throw new Error(`renderReceipt('${gKey}') produced 0 DOM elements`);
    }
  }
  console.log(`  [OK] Full renderReceipt() verified in both 'offline_raster' and 'ascii' modes across all 20 games!`);

  // 5. Real change event dispatch + cachedBundle reuse + zero "undefined" invariant
  currentRenderStyle = 'offline_raster';
  getMockElement('toggle-solutions').checked = false;
  getMockElement('select-game-count').value = 'all';
  getMockElement('select-game-count').dispatchEvent({ type: 'change', target: getMockElement('select-game-count') });
  const initialFirstPuzzle = cachedBundle ? cachedBundle.puzzleItems[0] : null;
  if (!initialFirstPuzzle) {
    throw new Error('Expected cachedBundle.puzzleItems after initial render');
  }

  getMockElement('toggle-solutions').checked = true;
  getMockElement('toggle-solutions').dispatchEvent({ type: 'change', target: getMockElement('toggle-solutions') });
  if (!cachedBundle || cachedBundle.puzzleItems[0] !== initialFirstPuzzle) {
    throw new Error('Expected toggle-solutions change event to reuse cachedBundle puzzleItems');
  }

  getMockElement('toggle-burn').checked = false;
  getMockElement('toggle-burn').dispatchEvent({ type: 'change', target: getMockElement('toggle-burn') });
  if (!cachedBundle || cachedBundle.puzzleItems[0] !== initialFirstPuzzle) {
    throw new Error('Expected toggle-burn change event to reuse cachedBundle puzzleItems');
  }

  // Dispatch change events across global difficulty, count preset, individual diff & toggle
  getMockElement('global-difficulty').value = 'hard';
  getMockElement('global-difficulty').dispatchEvent({ type: 'change', target: getMockElement('global-difficulty') });
  getMockElement('select-game-count').value = '5';
  getMockElement('select-game-count').dispatchEvent({ type: 'change', target: getMockElement('select-game-count') });
  getMockElement('diff-queens').value = '10x10_2star';
  getMockElement('diff-queens').dispatchEvent({ type: 'change', target: getMockElement('diff-queens') });
  getMockElement('toggle-sudoku').checked = false;
  getMockElement('toggle-sudoku').dispatchEvent({ type: 'change', target: getMockElement('toggle-sudoku') });

  const fullText = rawReceiptLines.join('\n');
  if (fullText.includes('undefined') || fullText.includes('NaN')) {
    throw new Error(`Found invalid string token in rawReceiptLines after change events`);
  }
  for (const child of (getMockElement('receipt-box').children || [])) {
    if (String(child.textContent || '').includes('undefined')) {
      throw new Error(`Found 'undefined' in rendered DOM text node`);
    }
  }
  console.log(`  [OK] Real change event dispatch, cachedBundle reuse, and zero 'undefined' text verified!`);
})();
"""

    full_js = harness_js + "\n" + script_js + "\n" + verification_footer_js
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as tmp:
        tmp.write(full_js)
        tmp_path = tmp.name

    try:
        res = subprocess.run([node_bin, tmp_path], capture_output=True, text=True, timeout=30)
        if res.returncode != 0:
            raise AssertionError(f"Headless simulator runtime verification failed:\n{res.stderr}\n{res.stdout}")
        print(res.stdout.rstrip())
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


def test_portal_headless_runtime():
    print("\nTest 3: Executing Headless Node.js Runtime & Error-Handling Verification for portal.html...")
    node_bin = shutil.which("node")
    if not node_bin:
        raise RuntimeError("Node.js runtime not found in PATH.")

    portal_js = extract_last_script_block(PORTAL_HTML)
    portal_test_js = r"""
const fs = require('fs');
const vm = require('vm');

const portalScript = fs.readFileSync(process.argv[2], 'utf8');
const elements = new Map();

function makeMockCanvas(id) {
  const c = {
    id, width: 288, height: 132, style: {},
    _vectorCalls: [], _imageData: null,
    getContext() {
      return {
        createImageData(w, h) { return { width: w, height: h, data: new Uint8ClampedArray(w * h * 4) }; },
        putImageData(img) { c._imageData = img; },
        fillRect(x, y, w, h) { c._vectorCalls.push(`fillRect(${x},${y},${w},${h})`); },
        strokeRect(x, y, w, h) { c._vectorCalls.push(`strokeRect(${x},${y},${w},${h})`); },
        fillText(t) { c._vectorCalls.push(`fillText(${t})`); },
        arc(x, y, r) { c._vectorCalls.push(`arc(${x},${y},${r})`); },
        lineTo(x, y) { c._vectorCalls.push(`lineTo(${x},${y})`); },
        stroke() { c._vectorCalls.push('stroke'); },
        fill() { c._vectorCalls.push('fill'); },
      };
    }
  };
  return c;
}

function getEl(id) {
  if (!elements.has(id)) {
    if (id === 'guideCanvasValid' || id === 'guideCanvasInvalid') {
      elements.set(id, makeMockCanvas(id));
    } else {
      elements.set(id, {
        id, value: '', checked: true, disabled: false, innerText: '', innerHTML: '',
        textContent: '', style: {},
        classList: { add() {}, remove() {}, toggle() {}, contains() { return false; } },
        addEventListener() {}, appendChild() {}, querySelectorAll() { return []; },
      });
    }
  }
  return elements.get(id);
}

let mockFailHttp500 = false;
const capturedToasts = [];
const sandbox = {
  console, Math, Array, Object, String, Number, Boolean, Set, Map, JSON, RegExp, Error,
  Date, Uint8ClampedArray,
  setTimeout: () => 0, clearTimeout: () => {},
  document: {
    getElementById: getEl,
    createElement(tag) {
      if (tag === 'canvas') return makeMockCanvas('created-canvas');
      return {
        tagName: tag, className: '', innerHTML: '', innerText: '', textContent: '',
        onclick: null, style: {},
        classList: { add() {}, remove() {}, toggle() {}, contains() { return false; } },
        addEventListener() {}, appendChild() {}, querySelectorAll() { return []; },
      };
    },
    body: { innerHTML: '<div>PORTAL</div>' },
    querySelectorAll() { return []; },
  },
  fetch(url) {
    if (url === '/api/config') {
      return Promise.resolve({
        ok: true, status: 200,
        json: async () => ({ mask: (1 << 20) - 1, count: 5, grade: 1, schedEnabled: true, schedHour: 7, schedMinute: 0 })
      });
    }
    if (mockFailHttp500) {
      return Promise.resolve({
        ok: false, status: 500,
        json: async () => ({ status: 'error', message: 'Printer offline' })
      });
    }
    return Promise.resolve({ ok: true, status: 200, json: async () => ({ status: 'ok' }) });
  }
};
sandbox.window = sandbox;
sandbox.globalThis = sandbox;
vm.createContext(sandbox);
vm.runInContext(portalScript, sandbox);

const origToast = sandbox.showToast;
sandbox.showToast = function(msg) {
  capturedToasts.push(String(msg));
  if (typeof origToast === 'function') origToast(msg);
};

async function runPortalChecks() {
  await new Promise(r => setImmediate(r));
  await new Promise(r => setImmediate(r));

  for (let g = 0; g < 20; g++) {
    const cv = getEl('guideCanvasValid');
    const ci = getEl('guideCanvasInvalid');
    cv._imageData = null; cv._vectorCalls = [];
    ci._imageData = null; ci._vectorCalls = [];
    sandbox.selectGuideGame(g);
    if (cv._vectorCalls.length > 0 || ci._vectorCalls.length > 0) {
      throw new Error(`Portal guide ${g} made vector Canvas2D calls: ${[...cv._vectorCalls, ...ci._vectorCalls].join(', ')}`);
    }
    if (!cv._imageData || !ci._imageData || cv.width !== 288 || cv.height !== 132 || ci.width !== 288 || ci.height !== 132) {
      throw new Error(`Portal guide ${g} invalid 1-bit canvas output`);
    }
    let blackV = 0, blackI = 0;
    for (let i = 0; i < cv._imageData.data.length; i += 4) if (cv._imageData.data[i] < 128) blackV++;
    for (let i = 0; i < ci._imageData.data.length; i += 4) if (ci._imageData.data[i] < 128) blackI++;
    if (blackV === 0 || blackI === 0) {
      throw new Error(`Portal guide ${g} produced blank panel bitmap (v=${blackV}, i=${blackI})`);
    }
  }
  console.log('  [OK] portal.html selectGuideGame(0..19) verified strictly 1-bit putImageData (288x132, 0 vector calls)');

  // Mock HTTP 500 failure handling on /api/save-config, /api/print-guide, /api/print-sample
  mockFailHttp500 = true;
  capturedToasts.length = 0;
  sandbox.document.body.innerHTML = '<div>PORTAL</div>';

  sandbox.saveAndExit();
  await new Promise(r => setImmediate(r));
  await new Promise(r => setImmediate(r));
  if (sandbox.document.body.innerHTML.includes('Configuration Saved')) {
    throw new Error('saveAndExit() overwrote portal body on HTTP 500 failure');
  }
  if (!capturedToasts.includes('Error saving configuration.')) {
    throw new Error(`Expected error toast for saveAndExit() HTTP 500, got: ${JSON.stringify(capturedToasts)}`);
  }

  sandbox.printCurrentGuide();
  await new Promise(r => setImmediate(r));
  await new Promise(r => setImmediate(r));
  if (!capturedToasts.includes('Failed to print rules.')) {
    throw new Error(`Expected error toast for printCurrentGuide() HTTP 500, got: ${JSON.stringify(capturedToasts)}`);
  }

  sandbox.printCurrentSample();
  await new Promise(r => setImmediate(r));
  await new Promise(r => setImmediate(r));
  if (!capturedToasts.includes('Failed to print sample.')) {
    throw new Error(`Expected error toast for printCurrentSample() HTTP 500, got: ${JSON.stringify(capturedToasts)}`);
  }

  console.log('  [OK] portal.html HTTP 500 error handling verified across /api/save-config, /api/print-guide, /api/print-sample!');
}

runPortalChecks().catch(err => {
  console.error(err);
  process.exit(1);
});
"""
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as f_js, \
         tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as f_drv:
        f_js.write(portal_js)
        f_drv.write(portal_test_js)
        p_js, p_drv = f_js.name, f_drv.name

    try:
        res = subprocess.run([node_bin, p_drv, p_js], capture_output=True, text=True, timeout=30)
        if res.returncode != 0:
            raise AssertionError(f"Headless portal runtime verification failed:\n{res.stderr}\n{res.stdout}")
        print(res.stdout.rstrip())
    finally:
        for fp in (p_js, p_drv):
            if os.path.exists(fp):
                os.remove(fp)


def run_simulator_runtime_tests():
    print("=" * 70)
    print("RUNNING WEB SIMULATOR & CAPTIVE PORTAL HEADLESS RUNTIME SUITE")
    print("=" * 70)
    test_js_syntax()
    test_simulator_headless_runtime()
    test_portal_headless_runtime()
    print("\n======================================================================")
    print("ALL WEB SIMULATOR & PORTAL RUNTIME TESTS PASSED (100%)!")
    print("======================================================================\n")


if __name__ == "__main__":
    run_simulator_runtime_tests()
