// ============================================================
// Domain Models
// ============================================================

export interface User {
  id: number;
  employee_id: string;
  full_name: string;
  department: string;
  role: string;
  status: 'active' | 'inactive' | 'suspended';
  fingerprints: Fingerprint[];
  created_at: string;
  updated_at: string;
}

export interface Fingerprint {
  id: number;
  user_id: number;
  finger_type: FingerType;
  template_data: string;
  quality_score: number;
  capture_count: number;
  created_at: string;
}

export type FingerType =
  | 'left_thumb'
  | 'left_index'
  | 'left_middle'
  | 'left_ring'
  | 'left_little'
  | 'right_thumb'
  | 'right_index'
  | 'right_middle'
  | 'right_ring'
  | 'right_little';

export interface VerificationLog {
  id: number;
  user_id: number | null;
  user_name: string | null;
  mode: 'verify' | 'identify';
  result: 'accept' | 'reject';
  confidence: number;
  latency_ms: number;
  finger_type: FingerType | null;
  timestamp: string;
}

export interface Model {
  id: number;
  name: string;
  format: 'onnx' | 'trt' | 'pth';
  file_path: string;
  file_size: number;
  is_active: boolean;
  accuracy: number | null;
  avg_latency_ms: number | null;
  created_at: string;
}

export interface Device {
  hostname: string;
  platform: string;
  cpu_usage: number;
  memory_total: number;
  memory_used: number;
  memory_percent: number;
  disk_total: number;
  disk_used: number;
  disk_percent: number;
  gpu_usage: number | null;
  gpu_memory_used: number | null;
  gpu_memory_total: number | null;
  temperature: number | null;
  uptime: number;
}

export interface SystemConfig {
  verification_threshold: number;
  identification_threshold: number;
  max_capture_attempts: number;
  min_quality_score: number;
  sensor_dpi: number;
  sensor_mode: 'auto' | 'manual';
  language: string;
  auto_backup_enabled: boolean;
  backup_interval_hours: number;
  log_retention_days: number;
}

export interface SensorStatus {
  connected: boolean;
  model: string;
  firmware_version: string;
  dpi: number;
  status: 'ready' | 'capturing' | 'error' | 'disconnected';
  last_capture_at: string | null;
}

// ============================================================
// API Request Types
// ============================================================

export interface CreateUserRequest {
  employee_id: string;
  full_name: string;
  department: string;
  role: string;
}

export interface UpdateUserRequest {
  full_name?: string;
  department?: string;
  role?: string;
  status?: 'active' | 'inactive' | 'suspended';
}

export interface VerifyRequest {
  user_id: number;
  finger_type?: FingerType;
}

export interface IdentifyRequest {
  finger_type?: FingerType;
}

export interface EnrollFingerprintRequest {
  user_id: number;
  finger_type: FingerType;
  images: string[]; // base64 encoded images
}

export interface UploadModelRequest {
  file: File;
  name: string;
}

export interface ConvertModelRequest {
  model_id: number;
  target_format: 'trt' | 'onnx';
}

export interface UpdateConfigRequest {
  [key: string]: string | number | boolean;
}

// ============================================================
// API Response Types
// ============================================================

export interface ApiResponse<T> {
  success: boolean;
  data: T | null;
  error: string | null;
}

export interface PaginatedResponse<T> {
  success: boolean;
  data: T[];
  total: number;
  page: number;
  limit: number;
}

export interface VerificationResult {
  result: 'accept' | 'reject';
  confidence: number;
  user: User | null;
  latency_ms: number;
  finger_type: FingerType | null;
}

export interface IdentificationResult {
  result: 'accept' | 'reject';
  confidence: number;
  matched_user: User | null;
  top_matches: Array<{
    user: User;
    confidence: number;
  }>;
  latency_ms: number;
}

export interface StatsResponse {
  total_users: number;
  total_fingerprints: number;
  verifications_today: number;
  acceptance_rate: number;
  avg_latency_ms: number;
  verifications_by_day: Array<{
    date: string;
    total: number;
    accepted: number;
    rejected: number;
  }>;
}

export interface HealthResponse {
  status: 'healthy' | 'degraded' | 'unhealthy';
  sensor: SensorStatus;
  device: Device;
  database: {
    connected: boolean;
    size_mb: number;
  };
  model: {
    loaded: boolean;
    name: string | null;
    format: string | null;
  };
  uptime: number;
}

export interface CaptureResponse {
  image: string; // base64
  quality_score: number;
  width: number;
  height: number;
}

export interface ProfileResult {
  model_name: string;
  total_latency_ms: number;
  stages: Array<{
    name: string;
    latency_ms: number;
  }>;
  throughput_fps: number;
}

// ============================================================
// WebSocket Message Types
// ============================================================

export interface WsMessage {
  type: WsMessageType;
  payload: unknown;
  timestamp: string;
}

export type WsMessageType =
  | 'sensor_status'
  | 'capture_preview'
  | 'verification_result'
  | 'identification_result'
  | 'system_alert'
  | 'enrollment_progress'
  | 'conversion_progress';

export interface WsCapturePreview {
  type: 'capture_preview';
  payload: {
    image: string;
    quality_score: number;
  };
}

export interface WsVerificationResult {
  type: 'verification_result';
  payload: VerificationResult;
}

export interface WsIdentificationResult {
  type: 'identification_result';
  payload: IdentificationResult;
}

export interface WsConversionProgress {
  type: 'conversion_progress';
  payload: {
    model_id: number;
    progress: number;
    status: 'converting' | 'completed' | 'failed';
    message: string;
  };
}

export interface WsSystemAlert {
  type: 'system_alert';
  payload: {
    level: 'info' | 'warning' | 'error';
    message: string;
  };
}
