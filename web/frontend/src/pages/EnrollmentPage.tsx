import { useState, useCallback } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import toast from 'react-hot-toast';
import {
  ChevronRight,
  ChevronLeft,
  Check,
  Camera,
  RefreshCw,
} from 'lucide-react';
import { usersApi, fingerprintApi } from '../services/api';
import FingerprintCanvas from '../components/FingerprintCanvas';
import LoadingSpinner from '../components/LoadingSpinner';
import type { FingerType, CreateUserRequest, CaptureResponse } from '../types';

// ============================================================
// Constants
// ============================================================

const STEPS = [
  { id: 1, label: 'User Details' },
  { id: 2, label: 'Select Fingers' },
  { id: 3, label: 'Capture' },
  { id: 4, label: 'Review' },
];

const FINGER_MAP: { key: FingerType; label: string; hand: 'left' | 'right'; index: number }[] = [
  { key: 'left_thumb', label: 'Thumb', hand: 'left', index: 0 },
  { key: 'left_index', label: 'Index', hand: 'left', index: 1 },
  { key: 'left_middle', label: 'Middle', hand: 'left', index: 2 },
  { key: 'left_ring', label: 'Ring', hand: 'left', index: 3 },
  { key: 'left_little', label: 'Little', hand: 'left', index: 4 },
  { key: 'right_thumb', label: 'Thumb', hand: 'right', index: 0 },
  { key: 'right_index', label: 'Index', hand: 'right', index: 1 },
  { key: 'right_middle', label: 'Middle', hand: 'right', index: 2 },
  { key: 'right_ring', label: 'Ring', hand: 'right', index: 3 },
  { key: 'right_little', label: 'Little', hand: 'right', index: 4 },
];

const REQUIRED_CAPTURES = 3;

// ============================================================
// Component
// ============================================================

function EnrollmentPage() {
  const queryClient = useQueryClient();

  // Step state
  const [step, setStep] = useState(1);

  // Step 1: User details
  const [userForm, setUserForm] = useState<CreateUserRequest>({
    employee_id: '',
    full_name: '',
    department: '',
    role: '',
  });
  const [createdUserId, setCreatedUserId] = useState<number | null>(null);

  // Step 2: Finger selection
  const [selectedFingers, setSelectedFingers] = useState<Set<FingerType>>(new Set());

  // Step 3: Captures
  const [captureIndex, setCaptureIndex] = useState(0);
  const [currentFingerIdx, setCurrentFingerIdx] = useState(0);
  const [captures, setCaptures] = useState<Record<string, CaptureResponse[]>>({});
  const [isCapturing, setIsCapturing] = useState(false);

  // Mutations
  const createUserMutation = useMutation({
    mutationFn: usersApi.create,
    onSuccess: (res) => {
      if (res.data) {
        setCreatedUserId(res.data.id);
        toast.success('User created successfully');
        setStep(2);
      }
    },
    onError: (err: Error) => {
      toast.error(err.message || 'Failed to create user');
    },
  });

  const enrollMutation = useMutation({
    mutationFn: fingerprintApi.enroll,
    onSuccess: () => {
      toast.success('Fingerprint enrolled successfully');
    },
    onError: (err: Error) => {
      toast.error(err.message || 'Enrollment failed');
    },
  });

  // Handlers
  const handleUserFormChange = useCallback(
    (field: keyof CreateUserRequest, value: string) => {
      setUserForm((prev) => ({ ...prev, [field]: value }));
    },
    [],
  );

  const handleCreateUser = useCallback(() => {
    if (!userForm.employee_id || !userForm.full_name) {
      toast.error('Employee ID and Full Name are required');
      return;
    }
    createUserMutation.mutate(userForm);
  }, [userForm, createUserMutation]);

  const toggleFinger = useCallback((finger: FingerType) => {
    setSelectedFingers((prev) => {
      const next = new Set(prev);
      if (next.has(finger)) {
        next.delete(finger);
      } else {
        next.add(finger);
      }
      return next;
    });
  }, []);

  const selectedFingersList = FINGER_MAP.filter((f) => selectedFingers.has(f.key));
  const currentFinger = selectedFingersList[currentFingerIdx];

  const handleCapture = useCallback(async () => {
    if (!currentFinger) return;
    setIsCapturing(true);
    try {
      const res = await fingerprintApi.capture();
      if (res.data) {
        setCaptures((prev) => {
          const key = currentFinger.key;
          const existing = prev[key] ?? [];
          return { ...prev, [key]: [...existing, res.data!] };
        });
        const nextCapIndex = captureIndex + 1;
        if (nextCapIndex >= REQUIRED_CAPTURES) {
          // Move to next finger
          if (currentFingerIdx < selectedFingersList.length - 1) {
            setCurrentFingerIdx((prev) => prev + 1);
            setCaptureIndex(0);
          }
          // else: all done - stay
        } else {
          setCaptureIndex(nextCapIndex);
        }
      }
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Capture failed');
    } finally {
      setIsCapturing(false);
    }
  }, [currentFinger, captureIndex, currentFingerIdx, selectedFingersList.length]);

  const handleRetake = useCallback(() => {
    if (!currentFinger) return;
    setCaptures((prev) => ({ ...prev, [currentFinger.key]: [] }));
    setCaptureIndex(0);
  }, [currentFinger]);

  const allCapturesDone = selectedFingersList.every(
    (f) => (captures[f.key]?.length ?? 0) >= REQUIRED_CAPTURES,
  );

  const handleFinishEnrollment = useCallback(async () => {
    if (!createdUserId) return;
    for (const finger of selectedFingersList) {
      const imgs = captures[finger.key] ?? [];
      if (imgs.length < REQUIRED_CAPTURES) continue;
      await enrollMutation.mutateAsync({
        user_id: createdUserId,
        finger_type: finger.key,
        images: imgs.map((c) => c.image),
      });
    }
    queryClient.invalidateQueries({ queryKey: ['users'] });
    toast.success('Enrollment complete!');
    // Reset
    setStep(1);
    setUserForm({ employee_id: '', full_name: '', department: '', role: '' });
    setCreatedUserId(null);
    setSelectedFingers(new Set());
    setCaptures({});
    setCaptureIndex(0);
    setCurrentFingerIdx(0);
  }, [createdUserId, selectedFingersList, captures, enrollMutation, queryClient]);

  const currentFingerCaptures = currentFinger ? (captures[currentFinger.key] ?? []) : [];

  // ============================================================
  // Render
  // ============================================================

  return (
    <div className="max-w-3xl mx-auto space-y-6">
      {/* Progress bar */}
      <div className="card">
        <div className="flex items-center justify-between">
          {STEPS.map((s, i) => (
            <div key={s.id} className="flex items-center flex-1">
              <div className="flex items-center gap-2">
                <div
                  className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-bold ${
                    step > s.id
                      ? 'bg-success text-white'
                      : step === s.id
                      ? 'bg-primary text-white'
                      : 'bg-gray-200 text-dark-lighter'
                  }`}
                >
                  {step > s.id ? <Check size={16} /> : s.id}
                </div>
                <span
                  className={`text-sm font-medium hidden sm:inline ${
                    step >= s.id ? 'text-dark' : 'text-dark-lighter'
                  }`}
                >
                  {s.label}
                </span>
              </div>
              {i < STEPS.length - 1 && (
                <div
                  className={`flex-1 h-0.5 mx-3 ${
                    step > s.id ? 'bg-success' : 'bg-gray-200'
                  }`}
                />
              )}
            </div>
          ))}
        </div>
      </div>

      {/* Step 1: User Details */}
      {step === 1 && (
        <div className="card space-y-4">
          <h3 className="text-lg font-semibold text-dark">User Details</h3>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-dark-lighter mb-1">
                Employee ID *
              </label>
              <input
                type="text"
                value={userForm.employee_id}
                onChange={(e) => handleUserFormChange('employee_id', e.target.value)}
                placeholder="e.g. EMP001"
                className="input-field"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-dark-lighter mb-1">
                Full Name *
              </label>
              <input
                type="text"
                value={userForm.full_name}
                onChange={(e) => handleUserFormChange('full_name', e.target.value)}
                placeholder="e.g. John Doe"
                className="input-field"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-dark-lighter mb-1">
                Department
              </label>
              <input
                type="text"
                value={userForm.department}
                onChange={(e) => handleUserFormChange('department', e.target.value)}
                placeholder="e.g. Engineering"
                className="input-field"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-dark-lighter mb-1">
                Role
              </label>
              <input
                type="text"
                value={userForm.role}
                onChange={(e) => handleUserFormChange('role', e.target.value)}
                placeholder="e.g. Developer"
                className="input-field"
              />
            </div>
          </div>
          <div className="flex justify-end pt-2">
            <button
              onClick={handleCreateUser}
              disabled={createUserMutation.isPending}
              className="btn-primary"
            >
              {createUserMutation.isPending ? (
                <LoadingSpinner size="sm" />
              ) : (
                <>
                  Next
                  <ChevronRight size={18} />
                </>
              )}
            </button>
          </div>
        </div>
      )}

      {/* Step 2: Finger Selection */}
      {step === 2 && (
        <div className="card space-y-6">
          <h3 className="text-lg font-semibold text-dark">Select Fingers to Enroll</h3>

          {/* Hand diagram */}
          <div className="grid grid-cols-2 gap-6">
            {(['left', 'right'] as const).map((hand) => (
              <div key={hand} className="space-y-3">
                <h4 className="text-sm font-semibold text-dark-lighter capitalize text-center">
                  {hand} Hand
                </h4>
                {/* Simple SVG hand diagram */}
                <svg viewBox="0 0 200 280" className="w-full max-w-[200px] mx-auto">
                  {/* Palm */}
                  <ellipse cx="100" cy="200" rx="70" ry="60" fill="#F5CBA7" stroke="#D4A574" strokeWidth="2" />
                  {/* Fingers */}
                  {[
                    { x: 35, y: 130, h: 50, idx: hand === 'left' ? 4 : 0 },
                    { x: 55, y: 80, h: 70, idx: hand === 'left' ? 3 : 1 },
                    { x: 85, y: 60, h: 80, idx: hand === 'left' ? 2 : 2 },
                    { x: 115, y: 75, h: 70, idx: hand === 'left' ? 1 : 3 },
                    { x: 145, y: 110, h: 55, idx: hand === 'left' ? 0 : 4 },
                  ].map((finger) => {
                    const fingerData = FINGER_MAP.find(
                      (f) => f.hand === hand && f.index === finger.idx,
                    );
                    if (!fingerData) return null;
                    const isSelected = selectedFingers.has(fingerData.key);
                    return (
                      <g key={fingerData.key}>
                        <rect
                          x={finger.x - 12}
                          y={finger.y}
                          width={24}
                          height={finger.h}
                          rx={12}
                          fill={isSelected ? '#27AE60' : '#F5CBA7'}
                          stroke={isSelected ? '#1E8449' : '#D4A574'}
                          strokeWidth={2}
                          className="cursor-pointer transition-colors"
                          onClick={() => toggleFinger(fingerData.key)}
                        />
                        {/* Fingertip circle */}
                        <circle
                          cx={finger.x}
                          cy={finger.y + 10}
                          r={10}
                          fill={isSelected ? '#2ECC71' : '#FDEBD0'}
                          stroke={isSelected ? '#1E8449' : '#D4A574'}
                          strokeWidth={1.5}
                          className="cursor-pointer"
                          onClick={() => toggleFinger(fingerData.key)}
                        />
                        {isSelected && (
                          <text
                            x={finger.x}
                            y={finger.y + 14}
                            textAnchor="middle"
                            fontSize="10"
                            fill="white"
                            fontWeight="bold"
                          >
                            ✓
                          </text>
                        )}
                      </g>
                    );
                  })}
                </svg>
                {/* Finger labels */}
                <div className="flex flex-wrap justify-center gap-1">
                  {FINGER_MAP.filter((f) => f.hand === hand).map((f) => (
                    <button
                      key={f.key}
                      onClick={() => toggleFinger(f.key)}
                      className={`text-xs px-2 py-1 rounded-full font-medium transition-colors ${
                        selectedFingers.has(f.key)
                          ? 'bg-success text-white'
                          : 'bg-gray-100 text-dark-lighter hover:bg-gray-200'
                      }`}
                    >
                      {f.label}
                    </button>
                  ))}
                </div>
              </div>
            ))}
          </div>

          <p className="text-sm text-dark-lighter text-center">
            {selectedFingers.size} finger{selectedFingers.size !== 1 ? 's' : ''} selected
            ({REQUIRED_CAPTURES} captures per finger)
          </p>

          <div className="flex justify-between pt-2">
            <button onClick={() => setStep(1)} className="btn-outline">
              <ChevronLeft size={18} />
              Back
            </button>
            <button
              onClick={() => {
                if (selectedFingers.size === 0) {
                  toast.error('Select at least one finger');
                  return;
                }
                setCurrentFingerIdx(0);
                setCaptureIndex(0);
                setStep(3);
              }}
              className="btn-primary"
            >
              Next
              <ChevronRight size={18} />
            </button>
          </div>
        </div>
      )}

      {/* Step 3: Capture */}
      {step === 3 && currentFinger && (
        <div className="card space-y-4">
          <h3 className="text-lg font-semibold text-dark">
            Capture Fingerprints
          </h3>
          <p className="text-sm text-dark-lighter">
            Finger: <span className="font-semibold text-dark capitalize">
              {currentFinger.hand} {currentFinger.label}
            </span>{' '}
            ({currentFingerIdx + 1} of {selectedFingersList.length})
          </p>

          {/* Capture progress dots */}
          <div className="flex items-center gap-2">
            {Array.from({ length: REQUIRED_CAPTURES }).map((_, i) => (
              <div
                key={i}
                className={`w-4 h-4 rounded-full border-2 transition-colors ${
                  i < currentFingerCaptures.length
                    ? 'bg-success border-success'
                    : i === currentFingerCaptures.length
                    ? 'border-primary bg-primary/20'
                    : 'border-gray-300'
                }`}
              />
            ))}
            <span className="text-sm text-dark-lighter ml-2">
              {currentFingerCaptures.length} / {REQUIRED_CAPTURES}
            </span>
          </div>

          {/* Preview area */}
          <div className="flex flex-col items-center gap-4 py-4">
            <FingerprintCanvas
              imageData={currentFingerCaptures.length > 0
                ? currentFingerCaptures[currentFingerCaptures.length - 1].image
                : null}
              qualityScore={currentFingerCaptures.length > 0
                ? currentFingerCaptures[currentFingerCaptures.length - 1].quality_score
                : null}
            />

            {/* Quality color coding */}
            {currentFingerCaptures.length > 0 && (
              <div className="flex gap-4 text-xs">
                {currentFingerCaptures.map((cap, i) => {
                  const color = cap.quality_score >= 80
                    ? 'bg-success'
                    : cap.quality_score >= 60
                    ? 'bg-warning'
                    : 'bg-danger';
                  return (
                    <div key={i} className="flex items-center gap-1">
                      <div className={`w-3 h-3 rounded-full ${color}`} />
                      <span>#{i + 1}: {cap.quality_score}%</span>
                    </div>
                  );
                })}
              </div>
            )}

            <div className="flex items-center gap-3">
              <button
                onClick={handleCapture}
                disabled={isCapturing || currentFingerCaptures.length >= REQUIRED_CAPTURES}
                className="btn-primary"
              >
                {isCapturing ? (
                  <LoadingSpinner size="sm" />
                ) : (
                  <>
                    <Camera size={18} />
                    Capture ({currentFingerCaptures.length + 1}/{REQUIRED_CAPTURES})
                  </>
                )}
              </button>
              {currentFingerCaptures.length > 0 && (
                <button onClick={handleRetake} className="btn-outline">
                  <RefreshCw size={18} />
                  Retake
                </button>
              )}
            </div>
          </div>

          <div className="flex justify-between pt-2">
            <button onClick={() => setStep(2)} className="btn-outline">
              <ChevronLeft size={18} />
              Back
            </button>
            <button
              onClick={() => setStep(4)}
              disabled={!allCapturesDone}
              className="btn-primary"
            >
              Review
              <ChevronRight size={18} />
            </button>
          </div>
        </div>
      )}

      {/* Step 4: Review & Confirm */}
      {step === 4 && (
        <div className="card space-y-4">
          <h3 className="text-lg font-semibold text-dark">Review & Confirm</h3>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 bg-gray-50 rounded-lg p-4">
            <div>
              <span className="text-xs text-dark-lighter">Employee ID</span>
              <p className="font-semibold">{userForm.employee_id}</p>
            </div>
            <div>
              <span className="text-xs text-dark-lighter">Full Name</span>
              <p className="font-semibold">{userForm.full_name}</p>
            </div>
            <div>
              <span className="text-xs text-dark-lighter">Department</span>
              <p className="font-semibold">{userForm.department || '-'}</p>
            </div>
            <div>
              <span className="text-xs text-dark-lighter">Role</span>
              <p className="font-semibold">{userForm.role || '-'}</p>
            </div>
          </div>

          <h4 className="text-sm font-semibold text-dark-lighter">
            Enrolled Fingers ({selectedFingersList.length})
          </h4>
          <div className="space-y-2">
            {selectedFingersList.map((finger) => {
              const caps = captures[finger.key] ?? [];
              const avgQuality = caps.length > 0
                ? caps.reduce((sum, c) => sum + c.quality_score, 0) / caps.length
                : 0;
              return (
                <div
                  key={finger.key}
                  className="flex items-center justify-between py-2 px-3 bg-gray-50 rounded-lg"
                >
                  <span className="text-sm capitalize font-medium">
                    {finger.hand} {finger.label}
                  </span>
                  <div className="flex items-center gap-4 text-sm">
                    <span className="text-dark-lighter">
                      {caps.length} captures
                    </span>
                    <span
                      className={`font-semibold ${
                        avgQuality >= 80
                          ? 'text-success'
                          : avgQuality >= 60
                          ? 'text-warning'
                          : 'text-danger'
                      }`}
                    >
                      Avg: {avgQuality.toFixed(0)}%
                    </span>
                  </div>
                </div>
              );
            })}
          </div>

          <div className="flex justify-between pt-4">
            <button onClick={() => setStep(3)} className="btn-outline">
              <ChevronLeft size={18} />
              Back
            </button>
            <button
              onClick={handleFinishEnrollment}
              disabled={enrollMutation.isPending}
              className="btn-success"
            >
              {enrollMutation.isPending ? (
                <LoadingSpinner size="sm" />
              ) : (
                <>
                  <Check size={18} />
                  Confirm Enrollment
                </>
              )}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

export default EnrollmentPage;
