'use strict';
/*
 * Build do VitaSchedule.
 *
 *   npm run setup      (uma vez, na raiz do projeto; instala o Tailwind 3.4.17 fixado em package-lock.json)
 *   npm run build      (na raiz ou dentro de build/; rode sempre que editar o HTML: classes do Tailwind OU o <script> inline)
 *
 * O que faz, em ordem:
 *   1. Compila o Tailwind lendo as classes do HTML (sem o <style> embutido) e embute o CSS no próprio HTML.
 *   2. Calcula o SHA-256 do <script> inline e do <style> embutido.
 *   3. Grava esses hashes na Content-Security-Policy (script-src e style-src), sem 'unsafe-inline'.
 *   4. Confere a sintaxe do script da aplicação.
 *
 * Uso alternativo: node build.js "C:\caminho\outro-arquivo.html"
 */
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const crypto = require('crypto');
const { execFileSync } = require('child_process');

const HTML = path.resolve(process.argv[2] || path.join(__dirname, '..', 'index.html'));
const TMP = path.join(__dirname, '.tmp');
const CLI = path.join(__dirname, 'node_modules', 'tailwindcss', 'lib', 'cli.js');

const STYLE_RE = /^([ \t]*)<style>([\s\S]*?)<\/style>/m; // só tag no início da linha (ignora "<style>" em comentários)
const SCRIPT_RE = /^[ \t]*<script>([\s\S]*?)<\/script>/gm; // só tags no início da linha (ignora "<script>" em comentários)
const CSP_RE = /(<meta http-equiv="Content-Security-Policy" content=")([^"]*)(">)/;

// O parser HTML normaliza CRLF -> LF antes de calcular hashes de CSP; fazemos o mesmo.
const lf = (s) => s.replace(/\r\n/g, '\n');
const sha256 = (s) => 'sha256-' + crypto.createHash('sha256').update(s, 'utf8').digest('base64');
const fail = (msg) => { console.error('ERRO: ' + msg); process.exit(1); };

if (!fs.existsSync(HTML)) fail('HTML não encontrado: ' + HTML);
if (!fs.existsSync(CLI)) fail('Tailwind não instalado. Rode "npm run setup" na raiz do projeto (ou "npm ci --ignore-scripts" dentro de build/).');

let html = lf(fs.readFileSync(HTML, 'utf8'));
if (!STYLE_RE.test(html)) fail('Bloco <style> não encontrado no HTML.');
if (!CSP_RE.test(html)) fail('Meta Content-Security-Policy não encontrada no HTML.');

// 1) Compila o Tailwind
fs.rmSync(TMP, { recursive: true, force: true });
fs.mkdirSync(TMP);
fs.writeFileSync(path.join(TMP, 'source.html'), html.replace(STYLE_RE, '$1<style></style>'), 'utf8');
execFileSync(process.execPath, [CLI, '-c', 'tailwind.config.js', '-i', 'input.css', '-o', path.join('.tmp', 'out.css'), '--minify'],
  { cwd: __dirname, stdio: 'inherit' });
const css = fs.readFileSync(path.join(TMP, 'out.css'), 'utf8').trim();
if (!css.includes('.bg-brand-600')) fail('CSS gerado não contém as classes esperadas (o scanner não leu o HTML?).');
if (/<\/style/i.test(css)) fail('CSS gerado contém "</style" (inseguro para embutir).');

html = html.replace(STYLE_RE, (_, indent) => `${indent}<style>\n${css}\n${indent}</style>`);

// 2) Hashes
const scripts = [...html.matchAll(SCRIPT_RE)].map((m) => m[1]);
if (scripts.length !== 1) fail(`Esperava exatamente 1 <script> inline (a aplicação); encontrei ${scripts.length}.`);
const scriptHash = sha256(scripts[0]);
const styleHash = sha256(html.match(STYLE_RE)[2]); // texto exato entre <style> e </style>

// 3) CSP
html = html.replace(CSP_RE, (_, open, policy, close) => {
  let p = policy;
  if (!/script-src[^;]*;/.test(p) || !/style-src[^;]*;/.test(p)) fail('Diretivas script-src/style-src não encontradas na CSP.');
  p = p.replace(/script-src[^;]*;/, () => `script-src '${scriptHash}';`);
  p = p.replace(/style-src[^;]*;/, () => `style-src '${styleHash}' https://cdnjs.cloudflare.com https://fonts.googleapis.com;`);
  return open + p + close;
});

// 4) Sintaxe do script da aplicação
try { new vm.Script(scripts[0], { filename: 'app-inline.js' }); }
catch (e) { fail('Erro de sintaxe no script da aplicação: ' + e.message); }

fs.writeFileSync(HTML, html, 'utf8');
fs.rmSync(TMP, { recursive: true, force: true });

console.log('\nOK  ' + HTML);
console.log('    CSS embutido : ' + (css.length / 1024).toFixed(1) + ' KB');
console.log('    script-src   : ' + scriptHash);
console.log('    style-src    : ' + styleHash);
