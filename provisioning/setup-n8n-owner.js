// Claims instance ownership so n8n never shows its first-run wizard. There is no CLI command
// for this, so it goes through the same unauthenticated route the setup screen itself posts to.
// Re-running is safe: n8n answers 400 "Instance owner already setup" and that counts as success.

const url = process.env.N8N_URL || 'http://n8n:5678';
const owner = {
  email: process.env.N8N_OWNER_EMAIL,
  firstName: process.env.N8N_OWNER_FIRST_NAME,
  lastName: process.env.N8N_OWNER_LAST_NAME,
  password: process.env.N8N_OWNER_PASSWORD,
};

const log = (message) => console.log(`[provision] ${message}`);
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

// /healthz answers well before the REST layer is mounted, so poll a real REST route instead.
async function waitForN8n() {
  for (let attempt = 0; attempt < 90; attempt++) {
    try {
      const response = await fetch(`${url}/rest/settings`);
      if (response.ok) return;
    } catch {}
    await sleep(2000);
  }
  throw new Error(`n8n REST API did not become reachable at ${url}`);
}

async function main() {
  const missing = Object.entries(owner)
    .filter(([, value]) => !value)
    .map(([key]) => key);
  if (missing.length > 0) {
    throw new Error(`missing owner settings: ${missing.join(', ')}`);
  }

  await waitForN8n();

  const response = await fetch(`${url}/rest/owner/setup`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(owner),
  });
  const body = await response.text();

  if (response.ok) {
    log(`owner account created for ${owner.email}`);
    return;
  }
  if (response.status === 400 && body.includes('already setup')) {
    log('owner account already exists, nothing to do');
    return;
  }
  throw new Error(`owner setup failed with HTTP ${response.status}: ${body}`);
}

main().catch((error) => {
  console.error(`[provision] ${error.message}`);
  process.exit(1);
});
