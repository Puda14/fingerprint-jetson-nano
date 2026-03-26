import type {
  ApiResponse,
  PaginatedResponse,
  User,
  CreateUserRequest,
  UpdateUserRequest,
  VerificationResult,
  IdentificationResult,
  VerifyRequest,
  EnrollFingerprintRequest,
  Fingerprint,
  Model,
  ProfileResult,
  VerificationLog,
  StatsResponse,
  HealthResponse,
  SensorStatus,
  SystemConfig,
  UpdateConfigRequest,
  CaptureResponse,
  WsMessage,
} from '../types';

const API_BASE = '/api/v1';

// ============================================================
// HTTP Helpers
// ============================================================

class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

async function request<T>(
  endpoint: string,
  options: RequestInit = {},
): Promise<T> {
  const url = `${API_BASE}${endpoint}`;
  const config: RequestInit = {
    headers: {
      'Content-Type': 'application/json',
      ...options.headers,
    },
    ...options,
  };

  const response = await fetch(url, config);

  if (!response.ok) {
    const body = await response.json().catch(() => ({ error: response.statusText }));
    throw new ApiError(response.status, body.error || body.detail || 'Request failed');
  }

  return response.json();
}

async function uploadFile<T>(
  endpoint: string,
  formData: FormData,
): Promise<T> {
  const url = `${API_BASE}${endpoint}`;
  const response = await fetch(url, {
    method: 'POST',
    body: formData,
  });

  if (!response.ok) {
    const body = await response.json().catch(() => ({ error: response.statusText }));
    throw new ApiError(response.status, body.error || body.detail || 'Upload failed');
  }

  return response.json();
}

// ============================================================
// Users API
// ============================================================

export const usersApi = {
  list: (params?: {
    page?: number;
    limit?: number;
    search?: string;
    department?: string;
    role?: string;
    status?: string;
  }): Promise<PaginatedResponse<User>> => {
    const searchParams = new URLSearchParams();
    if (params?.page) searchParams.set('page', String(params.page));
    if (params?.limit) searchParams.set('limit', String(params.limit));
    if (params?.search) searchParams.set('search', params.search);
    if (params?.department) searchParams.set('department', params.department);
    if (params?.role) searchParams.set('role', params.role);
    if (params?.status) searchParams.set('status', params.status);
    const qs = searchParams.toString();
    return request(`/users${qs ? `?${qs}` : ''}`);
  },

  get: (id: number): Promise<ApiResponse<User>> =>
    request(`/users/${id}`),

  create: (data: CreateUserRequest): Promise<ApiResponse<User>> =>
    request('/users', { method: 'POST', body: JSON.stringify(data) }),

  update: (id: number, data: UpdateUserRequest): Promise<ApiResponse<User>> =>
    request(`/users/${id}`, { method: 'PUT', body: JSON.stringify(data) }),

  delete: (id: number): Promise<ApiResponse<null>> =>
    request(`/users/${id}`, { method: 'DELETE' }),
};

// ============================================================
// Fingerprint / Enrollment API
// ============================================================

export const fingerprintApi = {
  enroll: (data: EnrollFingerprintRequest): Promise<ApiResponse<Fingerprint>> =>
    request('/fingerprints/enroll', { method: 'POST', body: JSON.stringify(data) }),

  capture: (): Promise<ApiResponse<CaptureResponse>> =>
    request('/fingerprints/capture', { method: 'POST' }),

  delete: (fingerprintId: number): Promise<ApiResponse<null>> =>
    request(`/fingerprints/${fingerprintId}`, { method: 'DELETE' }),
};

// ============================================================
// Verification API
// ============================================================

export const verificationApi = {
  verify: (data: VerifyRequest): Promise<ApiResponse<VerificationResult>> =>
    request('/verify', { method: 'POST', body: JSON.stringify(data) }),

  identify: (): Promise<ApiResponse<IdentificationResult>> =>
    request('/identify', { method: 'POST' }),
};

// ============================================================
// Models API
// ============================================================

export const modelsApi = {
  list: (): Promise<ApiResponse<Model[]>> =>
    request('/models'),

  get: (id: number): Promise<ApiResponse<Model>> =>
    request(`/models/${id}`),

  upload: (file: File, name: string): Promise<ApiResponse<Model>> => {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('name', name);
    return uploadFile('/models/upload', formData);
  },

  activate: (id: number): Promise<ApiResponse<Model>> =>
    request(`/models/${id}/activate`, { method: 'POST' }),

  convert: (id: number, targetFormat: string): Promise<ApiResponse<Model>> =>
    request(`/models/${id}/convert`, {
      method: 'POST',
      body: JSON.stringify({ target_format: targetFormat }),
    }),

  profile: (id: number): Promise<ApiResponse<ProfileResult>> =>
    request(`/models/${id}/profile`, { method: 'POST' }),

  delete: (id: number): Promise<ApiResponse<null>> =>
    request(`/models/${id}`, { method: 'DELETE' }),
};

// ============================================================
// Logs API
// ============================================================

export const logsApi = {
  list: (params?: {
    page?: number;
    limit?: number;
    user_id?: number;
    result?: string;
    start_date?: string;
    end_date?: string;
  }): Promise<PaginatedResponse<VerificationLog>> => {
    const searchParams = new URLSearchParams();
    if (params?.page) searchParams.set('page', String(params.page));
    if (params?.limit) searchParams.set('limit', String(params.limit));
    if (params?.user_id) searchParams.set('user_id', String(params.user_id));
    if (params?.result) searchParams.set('result', params.result);
    if (params?.start_date) searchParams.set('start_date', params.start_date);
    if (params?.end_date) searchParams.set('end_date', params.end_date);
    const qs = searchParams.toString();
    return request(`/logs${qs ? `?${qs}` : ''}`);
  },
};

// ============================================================
// Stats API
// ============================================================

export const statsApi = {
  get: (): Promise<ApiResponse<StatsResponse>> =>
    request('/stats'),
};

// ============================================================
// Health API
// ============================================================

export const healthApi = {
  get: (): Promise<ApiResponse<HealthResponse>> =>
    request('/health'),
};

// ============================================================
// Sensor API
// ============================================================

export const sensorApi = {
  status: (): Promise<ApiResponse<SensorStatus>> =>
    request('/sensor/status'),

  reset: (): Promise<ApiResponse<null>> =>
    request('/sensor/reset', { method: 'POST' }),
};

// ============================================================
// Config API
// ============================================================

export const configApi = {
  get: (): Promise<ApiResponse<SystemConfig>> =>
    request('/config'),

  update: (data: UpdateConfigRequest): Promise<ApiResponse<SystemConfig>> =>
    request('/config', { method: 'PUT', body: JSON.stringify(data) }),

  backup: (): Promise<ApiResponse<{ path: string }>> =>
    request('/config/backup', { method: 'POST' }),

  restore: (file: File): Promise<ApiResponse<null>> => {
    const formData = new FormData();
    formData.append('file', file);
    return uploadFile('/config/restore', formData);
  },
};

// ============================================================
// WebSocket Helpers
// ============================================================

export function createWebSocket(
  path: string,
  onMessage: (msg: WsMessage) => void,
  onError?: (error: Event) => void,
  onClose?: () => void,
): WebSocket {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const wsUrl = `${protocol}//${window.location.host}/ws${path}`;
  const ws = new WebSocket(wsUrl);

  ws.onmessage = (event) => {
    try {
      const message: WsMessage = JSON.parse(event.data);
      onMessage(message);
    } catch {
      console.error('Failed to parse WebSocket message:', event.data);
    }
  };

  ws.onerror = (event) => {
    console.error('WebSocket error:', event);
    onError?.(event);
  };

  ws.onclose = () => {
    onClose?.();
  };

  return ws;
}

export function createVerificationStream(
  onMessage: (msg: WsMessage) => void,
  onError?: (error: Event) => void,
  onClose?: () => void,
): WebSocket {
  return createWebSocket('/verification', onMessage, onError, onClose);
}

export function createSensorStream(
  onMessage: (msg: WsMessage) => void,
  onError?: (error: Event) => void,
  onClose?: () => void,
): WebSocket {
  return createWebSocket('/sensor', onMessage, onError, onClose);
}
