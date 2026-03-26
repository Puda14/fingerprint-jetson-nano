import { useState, useEffect, useCallback, useRef } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import toast from 'react-hot-toast';
import {
  Save,
  RotateCcw,
  Download,
  Upload,
  Cpu,
  Thermometer,
  HardDrive,
  MemoryStick,
} from 'lucide-react';
import { configApi, healthApi } from '../services/api';
import LoadingSpinner from '../components/LoadingSpinner';
import type { SystemConfig } from '../types';

// ============================================================
// Slider component
// ============================================================

function ThresholdSlider({
  label,
  value,
  min,
  max,
  step,
  onChange,
  unit = '',
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  step: number;
  onChange: (val: number) => void;
  unit?: string;
}) {
  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <label className="text-sm font-medium text-dark">{label}</label>
        <span className="text-sm font-bold text-primary tabular-nums">
          {value}{unit}
        </span>
      </div>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="w-full h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer accent-primary"
      />
      <div className="flex justify-between text-xs text-dark-lighter">
        <span>{min}{unit}</span>
        <span>{max}{unit}</span>
      </div>
    </div>
  );
}

// ============================================================
// Main Component
// ============================================================

function SettingsPage() {
  const queryClient = useQueryClient();
  const restoreInputRef = useRef<HTMLInputElement>(null);

  const [localConfig, setLocalConfig] = useState<SystemConfig | null>(null);
  const [hasChanges, setHasChanges] = useState(false);

  // Queries
  const { data: configRes, isLoading: configLoading } = useQuery({
    queryKey: ['config'],
    queryFn: configApi.get,
  });

  const { data: healthRes } = useQuery({
    queryKey: ['health'],
    queryFn: healthApi.get,
    refetchInterval: 10_000,
  });

  const device = healthRes?.data?.device;

  // Initialize local config from server
  useEffect(() => {
    if (configRes?.data && !localConfig) {
      setLocalConfig(configRes.data);
    }
  }, [configRes, localConfig]);

  // Mutations
  const updateMutation = useMutation({
    mutationFn: configApi.update,
    onSuccess: () => {
      toast.success('Settings saved');
      setHasChanges(false);
      queryClient.invalidateQueries({ queryKey: ['config'] });
    },
    onError: (err: Error) => toast.error(err.message),
  });

  const backupMutation = useMutation({
    mutationFn: configApi.backup,
    onSuccess: (res) => {
      toast.success(`Backup created: ${res.data?.path ?? 'success'}`);
    },
    onError: (err: Error) => toast.error(err.message),
  });

  const restoreMutation = useMutation({
    mutationFn: configApi.restore,
    onSuccess: () => {
      toast.success('Configuration restored');
      queryClient.invalidateQueries({ queryKey: ['config'] });
      setLocalConfig(null); // Force re-fetch
    },
    onError: (err: Error) => toast.error(err.message),
  });

  const updateField = useCallback(
    <K extends keyof SystemConfig>(field: K, value: SystemConfig[K]) => {
      setLocalConfig((prev) => (prev ? { ...prev, [field]: value } : prev));
      setHasChanges(true);
    },
    [],
  );

  const handleSave = useCallback(() => {
    if (!localConfig) return;
    updateMutation.mutate(localConfig as unknown as Record<string, string | number | boolean>);
  }, [localConfig, updateMutation]);

  const handleReset = useCallback(() => {
    if (configRes?.data) {
      setLocalConfig(configRes.data);
      setHasChanges(false);
    }
  }, [configRes]);

  const handleRestoreFile = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (file) restoreMutation.mutate(file);
    },
    [restoreMutation],
  );

  if (configLoading || !localConfig) {
    return <LoadingSpinner size="lg" className="mt-20" />;
  }

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      {/* Save bar */}
      {hasChanges && (
        <div className="card bg-primary/5 border-primary/20 flex items-center justify-between">
          <p className="text-sm font-medium text-primary">You have unsaved changes</p>
          <div className="flex items-center gap-2">
            <button onClick={handleReset} className="btn-outline text-sm py-1.5">
              <RotateCcw size={16} />
              Reset
            </button>
            <button
              onClick={handleSave}
              disabled={updateMutation.isPending}
              className="btn-primary text-sm py-1.5"
            >
              {updateMutation.isPending ? <LoadingSpinner size="sm" /> : <Save size={16} />}
              Save
            </button>
          </div>
        </div>
      )}

      {/* Thresholds */}
      <div className="card space-y-5">
        <h3 className="text-base font-semibold text-dark">Thresholds</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <ThresholdSlider
            label="Verification Threshold"
            value={localConfig.verification_threshold}
            min={0}
            max={1}
            step={0.01}
            onChange={(v) => updateField('verification_threshold', v)}
          />
          <ThresholdSlider
            label="Identification Threshold"
            value={localConfig.identification_threshold}
            min={0}
            max={1}
            step={0.01}
            onChange={(v) => updateField('identification_threshold', v)}
          />
          <ThresholdSlider
            label="Min Quality Score"
            value={localConfig.min_quality_score}
            min={0}
            max={100}
            step={5}
            onChange={(v) => updateField('min_quality_score', v)}
            unit="%"
          />
          <ThresholdSlider
            label="Max Capture Attempts"
            value={localConfig.max_capture_attempts}
            min={1}
            max={10}
            step={1}
            onChange={(v) => updateField('max_capture_attempts', v)}
          />
        </div>
      </div>

      {/* Sensor settings */}
      <div className="card space-y-4">
        <h3 className="text-base font-semibold text-dark">Sensor</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-medium text-dark-lighter mb-1">
              Sensor DPI
            </label>
            <input
              type="number"
              value={localConfig.sensor_dpi}
              onChange={(e) => updateField('sensor_dpi', Number(e.target.value))}
              className="input-field"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-dark-lighter mb-1">
              Sensor Mode
            </label>
            <select
              value={localConfig.sensor_mode}
              onChange={(e) => updateField('sensor_mode', e.target.value as 'auto' | 'manual')}
              className="select-field"
            >
              <option value="auto">Auto</option>
              <option value="manual">Manual</option>
            </select>
          </div>
        </div>
      </div>

      {/* System settings */}
      <div className="card space-y-4">
        <h3 className="text-base font-semibold text-dark">System</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-medium text-dark-lighter mb-1">
              Language
            </label>
            <select
              value={localConfig.language}
              onChange={(e) => updateField('language', e.target.value)}
              className="select-field"
            >
              <option value="en">English</option>
              <option value="vi">Vietnamese</option>
              <option value="ja">Japanese</option>
              <option value="ko">Korean</option>
              <option value="zh">Chinese</option>
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium text-dark-lighter mb-1">
              Log Retention (days)
            </label>
            <input
              type="number"
              value={localConfig.log_retention_days}
              onChange={(e) => updateField('log_retention_days', Number(e.target.value))}
              className="input-field"
              min={1}
              max={365}
            />
          </div>
          <div className="flex items-center gap-3 col-span-full">
            <label className="relative inline-flex items-center cursor-pointer">
              <input
                type="checkbox"
                checked={localConfig.auto_backup_enabled}
                onChange={(e) => updateField('auto_backup_enabled', e.target.checked)}
                className="sr-only peer"
              />
              <div className="w-11 h-6 bg-gray-200 peer-focus:outline-none peer-focus:ring-2 peer-focus:ring-primary/40 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:start-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-primary" />
            </label>
            <span className="text-sm font-medium text-dark">Auto Backup</span>
            {localConfig.auto_backup_enabled && (
              <span className="text-xs text-dark-lighter ml-2">
                Every {localConfig.backup_interval_hours}h
              </span>
            )}
          </div>
          {localConfig.auto_backup_enabled && (
            <div>
              <label className="block text-sm font-medium text-dark-lighter mb-1">
                Backup Interval (hours)
              </label>
              <input
                type="number"
                value={localConfig.backup_interval_hours}
                onChange={(e) => updateField('backup_interval_hours', Number(e.target.value))}
                className="input-field"
                min={1}
                max={168}
              />
            </div>
          )}
        </div>
      </div>

      {/* Device info */}
      {device && (
        <div className="card space-y-4">
          <h3 className="text-base font-semibold text-dark">Device Info</h3>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <DeviceInfoCard
              icon={Cpu}
              label="CPU Usage"
              value={`${device.cpu_usage?.toFixed(1) ?? '--'}%`}
              color={device.cpu_usage > 80 ? 'danger' : device.cpu_usage > 50 ? 'warning' : 'success'}
            />
            <DeviceInfoCard
              icon={MemoryStick}
              label="Memory"
              value={`${device.memory_percent?.toFixed(1) ?? '--'}%`}
              color={device.memory_percent > 80 ? 'danger' : device.memory_percent > 50 ? 'warning' : 'success'}
            />
            <DeviceInfoCard
              icon={HardDrive}
              label="Disk"
              value={`${device.disk_percent?.toFixed(1) ?? '--'}%`}
              color={device.disk_percent > 80 ? 'danger' : device.disk_percent > 50 ? 'warning' : 'success'}
            />
            <DeviceInfoCard
              icon={Thermometer}
              label="Temperature"
              value={device.temperature ? `${device.temperature.toFixed(0)}C` : 'N/A'}
              color={
                device.temperature
                  ? device.temperature > 70 ? 'danger' : device.temperature > 50 ? 'warning' : 'success'
                  : 'primary'
              }
            />
          </div>
          <div className="grid grid-cols-2 gap-4 text-sm text-dark-lighter">
            <div>
              <span className="text-xs">Hostname:</span>
              <p className="font-medium text-dark">{device.hostname}</p>
            </div>
            <div>
              <span className="text-xs">Platform:</span>
              <p className="font-medium text-dark">{device.platform}</p>
            </div>
          </div>
        </div>
      )}

      {/* Database / Backup Restore */}
      <div className="card space-y-4">
        <h3 className="text-base font-semibold text-dark">Database</h3>
        <div className="flex flex-wrap gap-3">
          <button
            onClick={() => backupMutation.mutate()}
            disabled={backupMutation.isPending}
            className="btn-primary"
          >
            {backupMutation.isPending ? <LoadingSpinner size="sm" /> : <Download size={18} />}
            Backup Now
          </button>
          <button
            onClick={() => restoreInputRef.current?.click()}
            disabled={restoreMutation.isPending}
            className="btn-outline"
          >
            {restoreMutation.isPending ? <LoadingSpinner size="sm" /> : <Upload size={18} />}
            Restore
          </button>
          <input
            ref={restoreInputRef}
            type="file"
            accept=".json,.db,.sqlite,.bak"
            onChange={handleRestoreFile}
            className="hidden"
          />
        </div>
      </div>
    </div>
  );
}

function DeviceInfoCard({
  icon: Icon,
  label,
  value,
  color,
}: {
  icon: typeof Cpu;
  label: string;
  value: string;
  color: 'primary' | 'success' | 'warning' | 'danger';
}) {
  const colorMap = {
    primary: 'text-primary bg-primary/10',
    success: 'text-success bg-success/10',
    warning: 'text-warning bg-warning/10',
    danger: 'text-danger bg-danger/10',
  };

  return (
    <div className="flex items-center gap-3 p-3 bg-gray-50 rounded-lg">
      <div className={`p-2 rounded-lg ${colorMap[color]}`}>
        <Icon size={18} />
      </div>
      <div>
        <p className="text-xs text-dark-lighter">{label}</p>
        <p className="font-bold text-dark">{value}</p>
      </div>
    </div>
  );
}

export default SettingsPage;
