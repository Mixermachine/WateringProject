/**
 * Minimal Home Assistant REST client for the e2e harness.
 *
 * Everything here talks to the *running* instance: onboarding, token exchange,
 * config entry creation, the options flow, service calls and state reads. No
 * internals of the integration are imported.
 */

export const BASE_URL = process.env["HA_URL"] ?? "http://localhost:8123";
export const CLIENT_ID = `${BASE_URL}/`;
export const USERNAME = "e2e";
export const PASSWORD = "e2e-password-123";

export interface Tokens {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
}

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly body: string,
    readonly path: string,
  ) {
    super(`${path} -> ${status}: ${body}`);
  }
}

async function request<T>(
  path: string,
  options: { method?: string; token?: string; body?: unknown } = {},
): Promise<T> {
  const headers: Record<string, string> = { "content-type": "application/json" };
  if (options.token !== undefined) {
    headers["authorization"] = `Bearer ${options.token}`;
  }
  const response = await fetch(`${BASE_URL}${path}`, {
    method: options.method ?? "GET",
    headers,
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
  });
  const text = await response.text();
  if (!response.ok) {
    throw new ApiError(response.status, text, path);
  }
  return (text ? JSON.parse(text) : undefined) as T;
}

/** Home Assistant's auth endpoints take form data, not JSON. */
async function formRequest<T>(path: string, body: Record<string, string>): Promise<T> {
  const response = await fetch(`${BASE_URL}${path}`, {
    method: "POST",
    headers: { "content-type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams(body).toString(),
  });
  const text = await response.text();
  if (!response.ok) {
    throw new ApiError(response.status, text, path);
  }
  return (text ? JSON.parse(text) : undefined) as T;
}

export async function waitForHomeAssistant(timeoutMs = 240_000): Promise<void> {
  // `/auth/providers` is unauthenticated and only answers once auth is up.
  // Never probe `/api/*` here: repeated 401s get the runner IP banned.
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    try {
      const response = await fetch(`${BASE_URL}/auth/providers`);
      if (response.status === 200) {
        return;
      }
    } catch {
      // Not listening yet.
    }
    await sleep(2_000);
  }
  throw new Error("Home Assistant did not become reachable");
}

export function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/** Run onboarding if needed and return a long-lived access token. */
export async function ensureOnboarded(): Promise<Tokens> {
  const authCode = await createOwner();
  const tokens = authCode !== null ? await exchangeCode(authCode) : await login();
  // Idempotent: the wizard blocks the UI and a reused instance may still have
  // steps open even though a token exists.
  await finishOnboarding(tokens.access_token);
  return tokens;
}

async function createOwner(): Promise<string | null> {
  try {
    const result = await request<{ auth_code: string }>("/api/onboarding/users", {
      method: "POST",
      body: {
        client_id: CLIENT_ID,
        name: "E2E",
        username: USERNAME,
        password: PASSWORD,
        language: "en",
      },
    });
    return result.auth_code;
  } catch (error) {
    if (error instanceof ApiError && (error.status === 403 || error.status === 404)) {
      return null; // Already onboarded (403 while running, 404 once finished).
    }
    throw error;
  }
}

async function exchangeCode(authCode: string): Promise<Tokens> {
  const tokens = await formRequest<Tokens>("/auth/token", {
    grant_type: "authorization_code",
    code: authCode,
    client_id: CLIENT_ID,
  });
  return tokens;
}

async function finishOnboarding(token: string): Promise<void> {
  // The wizard blocks the Lovelace UI until every step is marked done. Each step
  // endpoint expects the same client id that created the owner.
  let steps: Array<{ step: string; done: boolean }>;
  try {
    steps = await request<Array<{ step: string; done: boolean }>>("/api/onboarding", {
      token,
    });
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) {
      return; // Onboarding finished: the endpoint is gone.
    }
    throw error;
  }
  for (const step of steps) {
    if (step.done) {
      continue;
    }
    const body: Record<string, string> = { client_id: CLIENT_ID };
    if (step.step === "integration") {
      body["redirect_uri"] = CLIENT_ID;
    }
    await request(`/api/onboarding/${step.step}`, { method: "POST", token, body });
  }
}

async function login(): Promise<Tokens> {
  const flow = await request<{ flow_id: string }>("/auth/login_flow", {
    method: "POST",
    body: { client_id: CLIENT_ID, handler: ["homeassistant", null], redirect_uri: CLIENT_ID },
  });
  const step = await request<{ result?: string; errors?: unknown }>(
    `/auth/login_flow/${flow.flow_id}`,
    {
      method: "POST",
      body: { client_id: CLIENT_ID, username: USERNAME, password: PASSWORD },
    },
  );
  if (step.result === undefined || step.errors) {
    throw new Error(`login failed: ${JSON.stringify(step.errors ?? step)}`);
  }
  return formRequest<Tokens>("/auth/token", {
    grant_type: "authorization_code",
    code: step.result,
    client_id: CLIENT_ID,
  });
}

interface FlowResult {
  flow_id: string;
  type: string;
  errors?: Record<string, string> | null;
  step_id?: string;
  data_schema?: unknown;
}

async function finishFlow<T>(
  path: string,
  flowId: string,
  token: string,
  data: unknown,
): Promise<T> {
  const result = await request<FlowResult & { result?: T }>(`${path}/${flowId}`, {
    method: "POST",
    token,
    body: data,
  });
  if (result.type === "create_entry") {
    return result.result as T;
  }
  if (result.type === "abort" || result.type === "create_entry") {
    throw new Error(`flow aborted: ${JSON.stringify(result)}`);
  }
  throw new Error(`flow did not finish: ${JSON.stringify(result)}`);
}

/** Create a config entry for a handler that needs no input. */
export async function createEntry(
  token: string,
  handler: string,
): Promise<{ entry_id: string }> {
  const flow = await request<FlowResult>("/api/config/config_entries/flow", {
    method: "POST",
    token,
    body: { handler },
  });
  if (!flow.flow_id) {
    throw new Error(`no flow for ${handler}: ${JSON.stringify(flow)}`);
  }
  const created = await finishFlow<{ entry_id: string }>(
    "/api/config/config_entries/flow",
    flow.flow_id,
    token,
    {},
  );
  return { entry_id: created.entry_id ?? (created as unknown as string) };
}

export async function listEntries(
  token: string,
): Promise<Array<{ entry_id: string; domain: string; state: string; options: Record<string, unknown> }>> {
  return request("/api/config/config_entries/entry", { token });
}

export async function setOptions(
  token: string,
  entryId: string,
  options: Record<string, unknown>,
): Promise<void> {
  // Options flows are created with the *entry id* as handler.
  const flow = await request<FlowResult>("/api/config/config_entries/options/flow", {
    method: "POST",
    token,
    body: { handler: entryId },
  });
  const schema = flow.data_schema as Array<{ name?: string; required?: boolean }> | undefined;
  const payload: Record<string, unknown> = {};
  for (const field of schema ?? []) {
    if (field.name !== undefined && field.required === true) {
      payload[field.name] = defaultFor(field.name);
    }
  }
  await finishFlow(
    "/api/config/config_entries/options/flow",
    flow.flow_id,
    token,
    { ...payload, ...options },
  );
}

function defaultFor(name: string): unknown {
  switch (name) {
    case "moisture_default":
      return 70;
    case "battery_suspect_days":
      return 30;
    case "notify_repeat_hours":
      return 24;
    case "notify_enabled":
      return false;
    default:
      return "";
  }
}

export async function callService(
  token: string,
  domain: string,
  service: string,
  data: Record<string, unknown> = {},
): Promise<void> {
  await request(`/api/services/${domain}/${service}`, { method: "POST", token, body: data });
}

export async function getState<T = unknown>(
  token: string,
  entityId: string,
): Promise<{ state: string; attributes: Record<string, T> } | null> {
  try {
    return await request(`/api/states/${entityId}`, { token });
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) {
      return null;
    }
    throw error;
  }
}

export async function waitForState(
  token: string,
  entityId: string,
  predicate: (state: string) => boolean,
  timeoutMs = 30_000,
): Promise<string> {
  const deadline = Date.now() + timeoutMs;
  let last: string | null = null;
  while (Date.now() < deadline) {
    const state = await getState(token, entityId);
    last = state?.state ?? null;
    if (last !== null && predicate(last)) {
      return last;
    }
    await sleep(500);
  }
  throw new Error(`${entityId} did not reach the expected state (last: ${last})`);
}

export async function findDeviceId(token: string, name: string): Promise<string> {
  const devices = await wsCommand<Array<{ id: string; name: string | null }>>(
    token,
    "config/device_registry/list",
  );
  const device = devices.find((item) => item.name === name);
  if (device === undefined) {
    throw new Error(`device ${name} not found`);
  }
  return device.id;
}

/** Run one websocket command (some registry APIs have no REST endpoint). */
export async function wsCommand<T>(
  token: string,
  type: string,
  payload: Record<string, unknown> = {},
): Promise<T> {
  const url = `${BASE_URL.replace(/^http/, "ws")}/api/websocket`;
  return new Promise<T>((resolve, reject) => {
    const socket = new WebSocket(url);
    const timer = setTimeout(() => {
      socket.close();
      reject(new Error(`websocket timeout for ${type}`));
    }, 20_000);

    socket.addEventListener("message", (event) => {
      const message = JSON.parse(String(event.data)) as {
        type: string;
        id?: number;
        success?: boolean;
        result?: unknown;
        error?: unknown;
      };
      if (message.type === "auth_required") {
        socket.send(JSON.stringify({ type: "auth", access_token: token }));
        return;
      }
      if (message.type === "auth_invalid") {
        clearTimeout(timer);
        socket.close();
        reject(new Error("websocket auth failed"));
        return;
      }
      if (message.type === "auth_ok") {
        socket.send(JSON.stringify({ id: 1, ...payload, type }));
        return;
      }
      if (message.id === 1) {
        clearTimeout(timer);
        socket.close();
        if (message.success === true) {
          resolve(message.result as T);
        } else {
          reject(new Error(`websocket ${type} failed: ${JSON.stringify(message.error)}`));
        }
      }
    });
    socket.addEventListener("error", () => {
      clearTimeout(timer);
      reject(new Error(`websocket error for ${type}`));
    });
  });
}

/** Browser-side bootstrap: seed the token Home Assistant expects in localStorage. */
export async function browserTokens(tokens: Tokens): Promise<string> {
  const payload = {
    access_token: tokens.access_token,
    token_type: tokens.token_type,
    refresh_token: tokens.refresh_token,
    expires_in: tokens.expires_in,
    expires: Date.now() + (tokens.expires_in - 60) * 1000,
    hassUrl: BASE_URL,
    clientId: CLIENT_ID,
  };
  return `localStorage.setItem("hassTokens", ${JSON.stringify(JSON.stringify(payload))});`;
}
