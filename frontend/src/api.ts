export interface HealthResponse {
  status: string;
  service: string;
  version: string;
  falkordb: string;
  falkordb_host?: string;
  falkordb_port?: number;
}

export interface SmokeResponse {
  success: boolean;
  tenant: string;
  created: any[];
  verified: Array<{ caller: string; callee: string; protocol: string }>;
  message: string;
}

export async function checkHealth(): Promise<HealthResponse> {
  const res = await fetch('/health');
  if (!res.ok) {
    throw new Error(`Health check failed: ${res.statusText}`);
  }
  return res.json();
}

export async function runSmokeTest(tenant: string = 'smoke'): Promise<SmokeResponse> {
  const res = await fetch(`/api/smoke?tenant=${encodeURIComponent(tenant)}`);
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || 'Smoke test failed');
  }
  return res.json();
}
