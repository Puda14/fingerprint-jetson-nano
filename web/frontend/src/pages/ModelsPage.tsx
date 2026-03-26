import { useState, useCallback, useRef } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import toast from 'react-hot-toast';
import {
  Upload,
  Trash2,
  Zap,
  BarChart3,
  CheckCircle,
  FileCode,
  HardDrive,
} from 'lucide-react';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from 'recharts';
import { modelsApi } from '../services/api';
import StatusBadge from '../components/StatusBadge';
import ConfirmDialog from '../components/ConfirmDialog';
import LoadingSpinner from '../components/LoadingSpinner';
import type { Model, ProfileResult } from '../types';

const FORMAT_COLORS: Record<string, string> = {
  onnx: '#1B4F72',
  trt: '#27AE60',
  pth: '#F39C12',
};

const STAGE_COLORS = ['#1B4F72', '#2471A3', '#27AE60', '#F39C12', '#E74C3C', '#8E44AD'];

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function ModelsPage() {
  const queryClient = useQueryClient();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [uploadName, setUploadName] = useState('');
  const [dragOver, setDragOver] = useState(false);
  const [deleteModel, setDeleteModel] = useState<Model | null>(null);
  const [profileResult, setProfileResult] = useState<ProfileResult | null>(null);
  const [convertingId, setConvertingId] = useState<number | null>(null);

  // Queries
  const { data: modelsRes, isLoading } = useQuery({
    queryKey: ['models'],
    queryFn: modelsApi.list,
    refetchInterval: 10_000,
  });

  const models = modelsRes?.data ?? [];

  // Mutations
  const uploadMutation = useMutation({
    mutationFn: ({ file, name }: { file: File; name: string }) =>
      modelsApi.upload(file, name),
    onSuccess: () => {
      toast.success('Model uploaded successfully');
      queryClient.invalidateQueries({ queryKey: ['models'] });
      setUploadName('');
    },
    onError: (err: Error) => toast.error(err.message),
  });

  const activateMutation = useMutation({
    mutationFn: (id: number) => modelsApi.activate(id),
    onSuccess: () => {
      toast.success('Model activated');
      queryClient.invalidateQueries({ queryKey: ['models'] });
    },
    onError: (err: Error) => toast.error(err.message),
  });

  const convertMutation = useMutation({
    mutationFn: ({ id, format }: { id: number; format: string }) =>
      modelsApi.convert(id, format),
    onSuccess: () => {
      toast.success('Conversion started');
      setConvertingId(null);
      queryClient.invalidateQueries({ queryKey: ['models'] });
    },
    onError: (err: Error) => {
      toast.error(err.message);
      setConvertingId(null);
    },
  });

  const profileMutation = useMutation({
    mutationFn: (id: number) => modelsApi.profile(id),
    onSuccess: (res) => {
      if (res.data) setProfileResult(res.data);
    },
    onError: (err: Error) => toast.error(err.message),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: number) => modelsApi.delete(id),
    onSuccess: () => {
      toast.success('Model deleted');
      queryClient.invalidateQueries({ queryKey: ['models'] });
      setDeleteModel(null);
    },
    onError: (err: Error) => toast.error(err.message),
  });

  const handleFileDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setDragOver(false);
      const file = e.dataTransfer.files?.[0];
      if (file) {
        const name = uploadName || file.name.replace(/\.[^.]+$/, '');
        uploadMutation.mutate({ file, name });
      }
    },
    [uploadName, uploadMutation],
  );

  const handleFileSelect = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (file) {
        const name = uploadName || file.name.replace(/\.[^.]+$/, '');
        uploadMutation.mutate({ file, name });
      }
    },
    [uploadName, uploadMutation],
  );

  if (isLoading) {
    return <LoadingSpinner size="lg" className="mt-20" />;
  }

  return (
    <div className="space-y-6">
      {/* Upload area */}
      <div className="card space-y-4">
        <h3 className="text-base font-semibold text-dark">Upload Model</h3>
        <div className="flex items-end gap-3">
          <div className="flex-1">
            <label className="block text-sm font-medium text-dark-lighter mb-1">
              Model Name (optional)
            </label>
            <input
              type="text"
              value={uploadName}
              onChange={(e) => setUploadName(e.target.value)}
              placeholder="e.g. fingerprint-matcher-v2"
              className="input-field"
            />
          </div>
        </div>

        <div
          onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
          onDragLeave={() => setDragOver(false)}
          onDrop={handleFileDrop}
          className={`border-2 border-dashed rounded-xl p-8 text-center cursor-pointer transition-colors ${
            dragOver
              ? 'border-primary bg-primary/5'
              : 'border-gray-300 hover:border-primary/50'
          }`}
          onClick={() => fileInputRef.current?.click()}
        >
          <input
            ref={fileInputRef}
            type="file"
            accept=".onnx,.trt,.pth,.pt,.engine"
            onChange={handleFileSelect}
            className="hidden"
          />
          {uploadMutation.isPending ? (
            <div className="flex flex-col items-center gap-2">
              <LoadingSpinner />
              <p className="text-sm text-dark-lighter">Uploading...</p>
            </div>
          ) : (
            <>
              <Upload size={32} className="mx-auto text-dark-lighter mb-2" />
              <p className="text-sm font-medium text-dark">
                Drop model file here or click to browse
              </p>
              <p className="text-xs text-dark-lighter mt-1">
                Supported: .onnx, .trt, .pth, .pt, .engine
              </p>
            </>
          )}
        </div>
      </div>

      {/* Models list */}
      <div className="card">
        <h3 className="text-base font-semibold text-dark mb-4">Models</h3>
        {models.length === 0 ? (
          <p className="text-center text-dark-lighter py-8">No models uploaded yet</p>
        ) : (
          <div className="space-y-3">
            {models.map((model: Model) => (
              <div
                key={model.id}
                className={`flex items-center gap-4 p-4 rounded-xl border transition-colors ${
                  model.is_active
                    ? 'border-success/30 bg-success/5'
                    : 'border-gray-100 bg-gray-50/50'
                }`}
              >
                {/* Icon */}
                <div
                  className="p-3 rounded-lg"
                  style={{ backgroundColor: `${FORMAT_COLORS[model.format] ?? '#5D6D7E'}15` }}
                >
                  <FileCode
                    size={24}
                    style={{ color: FORMAT_COLORS[model.format] ?? '#5D6D7E' }}
                  />
                </div>

                {/* Info */}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <h4 className="font-semibold text-dark truncate">{model.name}</h4>
                    {model.is_active && (
                      <StatusBadge status="active" label="Active" />
                    )}
                  </div>
                  <div className="flex items-center gap-4 mt-1 text-xs text-dark-lighter">
                    <span className="uppercase font-semibold" style={{ color: FORMAT_COLORS[model.format] }}>
                      {model.format}
                    </span>
                    <span className="flex items-center gap-1">
                      <HardDrive size={12} />
                      {formatFileSize(model.file_size)}
                    </span>
                    {model.avg_latency_ms && (
                      <span>{model.avg_latency_ms.toFixed(1)}ms avg</span>
                    )}
                  </div>
                </div>

                {/* Actions */}
                <div className="flex items-center gap-1 shrink-0">
                  {!model.is_active && (
                    <button
                      onClick={() => activateMutation.mutate(model.id)}
                      className="p-2 hover:bg-gray-100 rounded-lg transition-colors"
                      title="Activate"
                    >
                      <CheckCircle size={18} className="text-success" />
                    </button>
                  )}
                  {model.format !== 'trt' && (
                    <button
                      onClick={() => {
                        setConvertingId(model.id);
                        convertMutation.mutate({ id: model.id, format: 'trt' });
                      }}
                      className="p-2 hover:bg-gray-100 rounded-lg transition-colors"
                      title="Convert to TensorRT"
                      disabled={convertingId === model.id}
                    >
                      {convertingId === model.id ? (
                        <LoadingSpinner size="sm" />
                      ) : (
                        <Zap size={18} className="text-warning" />
                      )}
                    </button>
                  )}
                  <button
                    onClick={() => profileMutation.mutate(model.id)}
                    className="p-2 hover:bg-gray-100 rounded-lg transition-colors"
                    title="Profile"
                    disabled={profileMutation.isPending}
                  >
                    <BarChart3 size={18} className="text-primary" />
                  </button>
                  <button
                    onClick={() => setDeleteModel(model)}
                    className="p-2 hover:bg-gray-100 rounded-lg transition-colors"
                    title="Delete"
                  >
                    <Trash2 size={18} className="text-danger" />
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Profile Result */}
      {profileResult && (
        <div className="card">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-base font-semibold text-dark">
              Profile: {profileResult.model_name}
            </h3>
            <div className="flex items-center gap-4 text-sm text-dark-lighter">
              <span>Total: <span className="font-semibold text-dark">{profileResult.total_latency_ms.toFixed(1)}ms</span></span>
              <span>Throughput: <span className="font-semibold text-dark">{profileResult.throughput_fps.toFixed(1)} FPS</span></span>
            </div>
          </div>
          <ResponsiveContainer width="100%" height={250}>
            <BarChart data={profileResult.stages} layout="vertical">
              <CartesianGrid strokeDasharray="3 3" stroke="#ECF0F1" />
              <XAxis type="number" tick={{ fontSize: 12 }} unit="ms" />
              <YAxis
                type="category"
                dataKey="name"
                tick={{ fontSize: 12 }}
                width={120}
              />
              <Tooltip
                formatter={(value: number) => `${value.toFixed(2)}ms`}
                contentStyle={{ borderRadius: '8px', border: '1px solid #ECF0F1' }}
              />
              <Bar dataKey="latency_ms" radius={[0, 4, 4, 0]}>
                {profileResult.stages.map((_, index) => (
                  <Cell
                    key={`cell-${index}`}
                    fill={STAGE_COLORS[index % STAGE_COLORS.length]}
                  />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Delete Confirmation */}
      <ConfirmDialog
        isOpen={!!deleteModel}
        title="Delete Model"
        message={`Are you sure you want to delete "${deleteModel?.name}"? This cannot be undone.`}
        confirmLabel="Delete"
        onConfirm={() => deleteModel && deleteMutation.mutate(deleteModel.id)}
        onCancel={() => setDeleteModel(null)}
      />
    </div>
  );
}

export default ModelsPage;
