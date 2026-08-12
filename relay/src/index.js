export default {
  async fetch(request, env, ctx) {
    // Only accept POST requests to /intake
    if (request.method !== 'POST') {
      return new Response('Method not allowed', { status: 405 });
    }

    const url = new URL(request.url);
    if (url.pathname !== '/intake') {
      return new Response('Not found', { status: 404 });
    }

    // Basic Auth Check using a shared secret
    const authHeader = request.headers.get('Authorization');
    // If APP_SECRET is not set in the environment, reject all requests for safety.
    if (!env.APP_SECRET || !authHeader || authHeader !== `Bearer ${env.APP_SECRET}`) {
      return new Response('Unauthorized', { status: 401 });
    }

    let payload;
    try {
      payload = await request.json();
    } catch (e) {
      return new Response('Bad request: invalid JSON', { status: 400 });
    }

    if (!payload.events || !Array.isArray(payload.events)) {
      return new Response('Bad request: missing or invalid events array', { status: 400 });
    }

    // Write to the telemetry-intake branch in ml_pipeline/telemetry_drop/
    const repoOwner = env.REPO_OWNER || "laljith-gamer";
    const repoName = env.REPO_NAME || "NurseAssist_AI";
    const branchName = "telemetry-intake";
    const timestamp = Date.now();
    
    // Generate a slightly random string to avoid collisions if multiple requests hit at the same ms
    const nonce = Math.random().toString(36).substring(2, 8);
    const filename = `ml_pipeline/telemetry_drop/telemetry_${timestamp}_${nonce}.json`;

    const githubUrl = `https://api.github.com/repos/${repoOwner}/${repoName}/contents/${filename}`;
    
    // btoa is available in Cloudflare Workers globally
    const fileContentBase64 = btoa(JSON.stringify(payload.events, null, 2));
    
    const githubBody = {
      message: `Drop telemetry events (batch of ${payload.events.length})`,
      content: fileContentBase64,
      branch: branchName
    };

    const ghResponse = await fetch(githubUrl, {
      method: 'PUT',
      headers: {
        'Authorization': `token ${env.GITHUB_TOKEN}`,
        'Accept': 'application/vnd.github.v3+json',
        'User-Agent': 'NurseAssist-Telemetry-Relay-Worker'
      },
      body: JSON.stringify(githubBody)
    });

    if (!ghResponse.ok) {
      const errorText = await ghResponse.text();
      return new Response(`GitHub API error: ${errorText}`, { status: 502 });
    }

    return new Response('Accepted', { status: 202 });
  },
};
