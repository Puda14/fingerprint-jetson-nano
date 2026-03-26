import { useState, useEffect, useCallback, useRef } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  ScanLine,
  Play,
  Square,
  User,
  ShieldCheck,
  ShieldX,
  Search,
} from 'lucide-react';
import { usersApi, createVerificationStream } from '../services/api';
import FingerprintCanvas from '../components/FingerprintCanvas';
import LoadingSpinner from '../components/LoadingSpinner';
import type { VerificationResult, IdentificationResult, WsMessage } from '../types';

type Mode = 'verify' | 'identify';

function VerificationPage() {
  const [mode, setMode] = useState<Mode>('identify');
  const [selectedUserId, setSelectedUserId] = useState<number | null>(null);
  const [isRunning, setIsRunning] = useState(false);
  const [previewImage, setPreviewImage] = useState<string | null>(null);
  const [quality, setQuality] = useState<number | null>(null);
  const [result, setResult] = useState<VerificationResult | IdentificationResult | null>(null);
  const [showResult, setShowResult] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);

  const { data: usersRes } = useQuery({
    queryKey: ['users', 'all'],
    queryFn: () => usersApi.list({ limit: 1000 }),
  });

  const users = usersRes?.data ?? [];

  const handleMessage = useCallback((msg: WsMessage) => {
    switch (msg.type) {
      case 'capture_preview': {
        const payload = msg.payload as { image: string; quality_score: number };
        setPreviewImage(payload.image);
        setQuality(payload.quality_score);
        break;
      }
      case 'verification_result': {
        const vr = msg.payload as VerificationResult;
        setResult(vr);
        setShowResult(true);
        break;
      }
      case 'identification_result': {
        const ir = msg.payload as IdentificationResult;
        setResult(ir);
        setShowResult(true);
        break;
      }
    }
  }, []);

  const startVerification = useCallback(() => {
    setShowResult(false);
    setResult(null);
    setIsRunning(true);

    const ws = createVerificationStream(
      handleMessage,
      () => setIsRunning(false),
      () => setIsRunning(false),
    );

    ws.onopen = () => {
      ws.send(JSON.stringify({
        action: 'start',
        mode,
        user_id: mode === 'verify' ? selectedUserId : undefined,
      }));
    };

    wsRef.current = ws;
  }, [mode, selectedUserId, handleMessage]);

  const stopVerification = useCallback(() => {
    if (wsRef.current) {
      wsRef.current.send(JSON.stringify({ action: 'stop' }));
      wsRef.current.close();
      wsRef.current = null;
    }
    setIsRunning(false);
  }, []);

  useEffect(() => {
    return () => {
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, []);

  const isAccepted = result?.result === 'accept';
  const matchedUser = result
    ? 'matched_user' in result
      ? (result as IdentificationResult).matched_user
      : (result as VerificationResult).user
    : null;
  const confidence = result?.confidence ?? 0;

  return (
    <div className="space-y-6 max-w-4xl mx-auto">
      {/* Mode toggle */}
      <div className="card">
        <div className="flex flex-col sm:flex-row items-start sm:items-center gap-4">
          <span className="text-sm font-semibold text-dark-lighter">Mode:</span>
          <div className="flex bg-gray-100 rounded-lg p-1">
            <button
              onClick={() => { setMode('verify'); setShowResult(false); }}
              className={`px-4 py-2 rounded-md text-sm font-medium transition-colors min-h-touch ${
                mode === 'verify'
                  ? 'bg-primary text-white shadow-sm'
                  : 'text-dark-lighter hover:text-dark'
              }`}
            >
              <ScanLine size={16} className="inline mr-2" />
              1:1 Verify
            </button>
            <button
              onClick={() => { setMode('identify'); setShowResult(false); }}
              className={`px-4 py-2 rounded-md text-sm font-medium transition-colors min-h-touch ${
                mode === 'identify'
                  ? 'bg-primary text-white shadow-sm'
                  : 'text-dark-lighter hover:text-dark'
              }`}
            >
              <Search size={16} className="inline mr-2" />
              1:N Identify
            </button>
          </div>

          {mode === 'verify' && (
            <div className="flex-1 w-full sm:w-auto">
              <select
                value={selectedUserId ?? ''}
                onChange={(e) => setSelectedUserId(e.target.value ? Number(e.target.value) : null)}
                className="select-field"
              >
                <option value="">Select user...</option>
                {users.map((u) => (
                  <option key={u.id} value={u.id}>
                    {u.full_name} ({u.employee_id})
                  </option>
                ))}
              </select>
            </div>
          )}
        </div>
      </div>

      {/* Main verification area */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Fingerprint preview */}
        <div className="card flex flex-col items-center gap-4">
          <h3 className="text-base font-semibold text-dark self-start">
            Fingerprint Preview
          </h3>
          <FingerprintCanvas
            imageData={previewImage}
            width={192}
            height={192}
            qualityScore={quality}
            className="my-2"
          />

          {/* Start / Stop button */}
          <button
            onClick={isRunning ? stopVerification : startVerification}
            disabled={mode === 'verify' && !selectedUserId}
            className={isRunning ? 'btn-danger w-full' : 'btn-success w-full'}
          >
            {isRunning ? (
              <>
                <Square size={18} />
                Stop
              </>
            ) : (
              <>
                <Play size={18} />
                {mode === 'verify' ? 'Start Verification' : 'Start Identification'}
              </>
            )}
          </button>

          {isRunning && (
            <div className="flex items-center gap-2 text-sm text-dark-lighter">
              <LoadingSpinner size="sm" />
              Waiting for fingerprint...
            </div>
          )}
        </div>

        {/* Result display */}
        <div className="card flex flex-col items-center justify-center min-h-[360px]">
          {!showResult ? (
            <div className="text-center text-dark-lighter">
              <ScanLine size={48} className="mx-auto mb-3 opacity-30" />
              <p className="text-sm">
                {mode === 'verify'
                  ? 'Select a user and start verification'
                  : 'Start identification to find matching user'}
              </p>
            </div>
          ) : (
            <div className={`text-center w-full animate-in ${isAccepted ? '' : ''}`}>
              {/* Result icon */}
              <div
                className={`mx-auto w-24 h-24 rounded-full flex items-center justify-center mb-4 transition-all duration-500 ${
                  isAccepted
                    ? 'bg-success/10 text-success ring-4 ring-success/20'
                    : 'bg-danger/10 text-danger ring-4 ring-danger/20'
                }`}
              >
                {isAccepted ? (
                  <ShieldCheck size={48} />
                ) : (
                  <ShieldX size={48} />
                )}
              </div>

              {/* Result text */}
              <h3
                className={`text-3xl font-bold mb-2 ${
                  isAccepted ? 'text-success' : 'text-danger'
                }`}
              >
                {isAccepted ? 'ACCEPTED' : 'REJECTED'}
              </h3>

              {/* Confidence bar */}
              <div className="w-full max-w-xs mx-auto mb-4">
                <div className="flex items-center justify-between text-xs mb-1">
                  <span className="text-dark-lighter">Confidence</span>
                  <span className="font-semibold">{(confidence * 100).toFixed(1)}%</span>
                </div>
                <div className="h-3 bg-gray-200 rounded-full overflow-hidden">
                  <div
                    className={`h-full rounded-full transition-all duration-700 ${
                      isAccepted ? 'bg-success' : 'bg-danger'
                    }`}
                    style={{ width: `${confidence * 100}%` }}
                  />
                </div>
              </div>

              {/* Matched user info */}
              {matchedUser && (
                <div className="card bg-gray-50 text-left mt-4">
                  <div className="flex items-center gap-3">
                    <div className="p-2 bg-primary/10 rounded-lg">
                      <User size={20} className="text-primary" />
                    </div>
                    <div>
                      <p className="font-semibold text-dark">{matchedUser.full_name}</p>
                      <p className="text-xs text-dark-lighter">
                        {matchedUser.employee_id} - {matchedUser.department}
                      </p>
                    </div>
                  </div>
                </div>
              )}

              {/* Latency */}
              <p className="text-xs text-dark-lighter mt-3">
                Latency: {result?.latency_ms ?? 0}ms
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default VerificationPage;
