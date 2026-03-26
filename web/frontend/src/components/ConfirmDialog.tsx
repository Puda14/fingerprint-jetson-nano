import { AlertTriangle, X } from 'lucide-react';

interface ConfirmDialogProps {
  isOpen: boolean;
  title: string;
  message: string;
  confirmLabel?: string;
  cancelLabel?: string;
  variant?: 'danger' | 'warning' | 'primary';
  onConfirm: () => void;
  onCancel: () => void;
}

function ConfirmDialog({
  isOpen,
  title,
  message,
  confirmLabel = 'Confirm',
  cancelLabel = 'Cancel',
  variant = 'danger',
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  if (!isOpen) return null;

  const confirmClasses = {
    danger: 'btn-danger',
    warning: 'bg-warning text-white px-4 py-2 rounded-lg font-medium hover:bg-warning-light min-h-touch min-w-touch inline-flex items-center justify-center gap-2',
    primary: 'btn-primary',
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="fixed inset-0 bg-black/50" onClick={onCancel} />
      <div className="relative bg-white rounded-xl shadow-xl p-6 max-w-md w-full mx-4 animate-in">
        <button
          onClick={onCancel}
          className="absolute top-4 right-4 p-1 text-dark-lighter hover:text-dark rounded-lg hover:bg-gray-100 transition-colors"
        >
          <X size={20} />
        </button>

        <div className="flex items-start gap-4">
          <div className={`p-2 rounded-lg ${variant === 'danger' ? 'bg-danger/10 text-danger' : variant === 'warning' ? 'bg-warning/10 text-warning' : 'bg-primary/10 text-primary'}`}>
            <AlertTriangle size={24} />
          </div>
          <div className="flex-1">
            <h3 className="text-lg font-semibold text-dark">{title}</h3>
            <p className="mt-2 text-sm text-dark-lighter leading-relaxed">{message}</p>
          </div>
        </div>

        <div className="flex items-center justify-end gap-3 mt-6">
          <button onClick={onCancel} className="btn-outline">
            {cancelLabel}
          </button>
          <button onClick={onConfirm} className={confirmClasses[variant]}>
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}

export default ConfirmDialog;
