import assert from 'assert';
import worker from './src/index.js';

async function runTests() {
  const env = {
    APP_SECRET: 'secret',
    GITHUB_TOKEN: 'gh_token',
    REPO_OWNER: 'test-owner',
    REPO_NAME: 'test-repo'
  };

  // Helper to construct a request
  const makeRequest = (method, path, headers = {}, body = null) => {
    return new Request(`http://localhost${path}`, {
      method,
      headers,
      body: body ? JSON.stringify(body) : null
    });
  };

  // Mock global fetch for GitHub API
  globalThis.fetch = async (url, options) => {
    if (url.includes('api.github.com')) {
      return new Response('{"commit": {}}', { status: 201 }); // Mock GitHub success
    }
    return new Response('Not found', { status: 404 });
  };
  
  // Mock btoa
  globalThis.btoa = (str) => Buffer.from(str).toString('base64');

  console.log('Running Relay Worker tests...');

  // 1. Test method not allowed
  const req1 = makeRequest('GET', '/intake');
  const res1 = await worker.fetch(req1, env, {});
  assert.strictEqual(res1.status, 405, 'Should return 405 for GET');

  // 2. Test not found path
  const req2 = makeRequest('POST', '/unknown');
  const res2 = await worker.fetch(req2, env, {});
  assert.strictEqual(res2.status, 404, 'Should return 404 for unknown path');

  // 3. Test unauthorized (no header)
  const req3 = makeRequest('POST', '/intake');
  const res3 = await worker.fetch(req3, env, {});
  assert.strictEqual(res3.status, 401, 'Should return 401 with no auth header');

  // 4. Test unauthorized (wrong secret)
  const req4 = makeRequest('POST', '/intake', { 'Authorization': 'Bearer wrong' });
  const res4 = await worker.fetch(req4, env, {});
  assert.strictEqual(res4.status, 401, 'Should return 401 with wrong auth header');

  // 5. Test bad payload
  const req5 = makeRequest('POST', '/intake', { 'Authorization': 'Bearer secret' }, { invalid: 'payload' });
  const res5 = await worker.fetch(req5, env, {});
  assert.strictEqual(res5.status, 400, 'Should return 400 for payload missing events array');

  // 6. Test valid payload
  const req6 = makeRequest('POST', '/intake', { 'Authorization': 'Bearer secret' }, { events: [{id: 1}] });
  const res6 = await worker.fetch(req6, env, {});
  assert.strictEqual(res6.status, 202, 'Should return 202 for valid payload');

  console.log('All relay tests passed!');
}

runTests().catch(err => {
  console.error('Test failed:', err);
  process.exit(1);
});
