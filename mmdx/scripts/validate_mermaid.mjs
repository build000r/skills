#!/usr/bin/env node
import { JSDOM } from 'jsdom';

const { window } = new JSDOM('');
globalThis.window = window;
globalThis.document = window.document;

const { default: mermaid } = await import('mermaid');

const chunks = [];

for await (const chunk of process.stdin) {
  chunks.push(chunk);
}

const code = chunks.join('');

try {
  mermaid.initialize({
    startOnLoad: false,
    securityLevel: 'strict'
  });
  const result = await mermaid.parse(code, { suppressErrors: false });
  process.stdout.write(
    `${JSON.stringify({
      ok: true,
      diagramType: result?.diagramType ?? 'unknown'
    })}\n`
  );
} catch (error) {
  const message = error instanceof Error ? error.message : String(error);
  const hash = error && typeof error === 'object' && 'hash' in error ? error.hash : undefined;
  process.stderr.write(`Mermaid preflight failed: ${message}\n`);
  if (hash) {
    process.stderr.write(`${JSON.stringify(hash)}\n`);
  }
  process.exit(1);
}
