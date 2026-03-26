interface StatusBadgeProps {
  status: 'online' | 'offline' | 'warning' | 'active' | 'inactive' | 'suspended' | 'ready' | 'error' | 'capturing' | 'disconnected';
  label?: string;
  showDot?: boolean;
}

function StatusBadge({ status, label, showDot = true }: StatusBadgeProps) {
  const config: Record<string, { dot: string; bg: string; text: string; defaultLabel: string }> = {
    online: { dot: 'bg-success', bg: 'bg-success/10', text: 'text-success-dark', defaultLabel: 'Online' },
    offline: { dot: 'bg-gray-400', bg: 'bg-gray-100', text: 'text-gray-600', defaultLabel: 'Offline' },
    warning: { dot: 'bg-warning', bg: 'bg-warning/10', text: 'text-warning-dark', defaultLabel: 'Warning' },
    active: { dot: 'bg-success', bg: 'bg-success/10', text: 'text-success-dark', defaultLabel: 'Active' },
    inactive: { dot: 'bg-gray-400', bg: 'bg-gray-100', text: 'text-gray-600', defaultLabel: 'Inactive' },
    suspended: { dot: 'bg-danger', bg: 'bg-danger/10', text: 'text-danger-dark', defaultLabel: 'Suspended' },
    ready: { dot: 'bg-success', bg: 'bg-success/10', text: 'text-success-dark', defaultLabel: 'Ready' },
    error: { dot: 'bg-danger', bg: 'bg-danger/10', text: 'text-danger-dark', defaultLabel: 'Error' },
    capturing: { dot: 'bg-warning', bg: 'bg-warning/10', text: 'text-warning-dark', defaultLabel: 'Capturing' },
    disconnected: { dot: 'bg-gray-400', bg: 'bg-gray-100', text: 'text-gray-600', defaultLabel: 'Disconnected' },
  };

  const c = config[status] ?? config.offline;
  const displayLabel = label ?? c.defaultLabel;

  return (
    <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium ${c.bg} ${c.text}`}>
      {showDot && (
        <span className={`w-2 h-2 rounded-full ${c.dot} animate-pulse-dot`} />
      )}
      {displayLabel}
    </span>
  );
}

export default StatusBadge;
