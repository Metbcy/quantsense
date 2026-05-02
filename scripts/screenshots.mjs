// Capture redesign screenshots via Playwright.
// Usage: node scripts/screenshots.mjs
import { chromium } from 'playwright';
import fs from 'node:fs';
import path from 'node:path';

const BASE = process.env.BASE_URL || 'http://127.0.0.1:3210';
const API = process.env.API_BASE || 'http://127.0.0.1:8765';
const USER = 'demo';
const PASS = 'DemoPass123!';
const OUT = path.resolve('docs/screenshots');
fs.mkdirSync(OUT, { recursive: true });

const SHOTS = [
  { name: '01-login', path: '/login', auth: false },
  { name: '02-dashboard', path: '/dashboard', auth: true },
  { name: '03-backtest', path: '/backtest', auth: true, prep: 'backtest' },
  { name: '04-charts', path: '/charts', auth: true, wait: 2500 },
  { name: '05-compare', path: '/compare', auth: true, prep: 'compare' },
  { name: '06-sentiment', path: '/sentiment', auth: true },
  { name: '07-settings', path: '/settings', auth: true },
];

async function login(page) {
  // Get a real JWT from the backend, then inject into localStorage under the
  // key the app uses (qs_token). Skipping the React form avoids hydration
  // races with controlled inputs in headless browsers.
  const resp = await fetch(`${API}/api/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username: USER, password: PASS }),
  });
  if (!resp.ok) throw new Error(`Login failed: ${resp.status} ${await resp.text()}`);
  const { access_token } = await resp.json();
  // Set the token BEFORE navigating to dashboard so AuthProvider sees it.
  await page.goto(`${BASE}/login`, { waitUntil: 'domcontentloaded' });
  await page.evaluate((t) => { localStorage.setItem('qs_token', t); }, access_token);
}

async function ensureUser() {
  // Idempotent: registration may already exist
  await fetch(`${API}/api/auth/register`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username: USER, password: PASS, email: 'demo@demo.local' }),
  }).catch(() => {});
}

async function prepBacktest(token) {
  await fetch(`${API}/api/backtest/run`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
    body: JSON.stringify({
      ticker: 'AAPL', strategy: 'momentum',
      start_date: '2024-01-01', end_date: '2024-12-31',
      initial_capital: 10000, params: {},
    }),
  }).catch(() => {});
}

(async () => {
  await ensureUser();
  // Get a token for backtest prep via direct API
  const lr = await fetch(`${API}/api/auth/login`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username: USER, password: PASS }),
  });
  const { access_token: token } = await lr.json();
  await prepBacktest(token);

  const browser = await chromium.launch();
  for (const theme of ['light', 'dark']) {
    const ctx = await browser.newContext({
      viewport: { width: 1440, height: 900 },
      colorScheme: theme,
    });
    // Force theme on every page in the context
    await ctx.addInitScript((t) => {
      try { localStorage.setItem('theme', t); } catch {}
      const apply = () => {
        document.documentElement.classList.toggle('dark', t === 'dark');
        document.documentElement.classList.toggle('light', t === 'light');
        document.documentElement.style.colorScheme = t;
      };
      apply();
      new MutationObserver(apply).observe(document.documentElement, { attributes: true, attributeFilter: ['class'] });
    }, theme);

    // One persistent page; log in via the form once
    const page = await ctx.newPage();
    await login(page);

    for (const shot of SHOTS) {
      try {
        await page.goto(`${BASE}${shot.path}`, { waitUntil: 'networkidle', timeout: 20000 });
      } catch (e) {
        console.warn(`nav timeout ${shot.path}: ${e.message}`);
      }
      await page.waitForTimeout(shot.wait || 1500);
      const file = path.join(OUT, `${shot.name}-${theme}.png`);
      await page.screenshot({ path: file, fullPage: true });
      console.log('  wrote', file);
    }
    await ctx.close();
  }
  await browser.close();
  console.log('done');
})();
