import type { LucideIcon } from 'lucide-react';

interface StatsCardProps {
  icon: LucideIcon;
  label: string;
  value: string | number;
  trend?: {
    value: number;
    isPositive: boolean;
  };
  color?: 'primary' | 'success' | 'danger' | 'warning';
}

function StatsCard({ icon: Icon, label, value, trend, color = 'primary' }: StatsCardProps) {
  const colorClasses = {
    primary: 'bg-primary/10 text-primary',
    success: 'bg-success/10 text-success',
    danger: 'bg-danger/10 text-danger',
    warning: 'bg-warning/10 text-warning',
  };

  return (
    <div className="card flex items-start gap-4">
      <div className={`p-3 rounded-lg ${colorClasses[color]}`}>
        <Icon size={24} />
      </div>
      <div className="flex-1 min-w-0">
        <p className="text-sm text-dark-lighter truncate">{label}</p>
        <p className="text-2xl font-bold text-dark mt-0.5">{value}</p>
        {trend && (
          <p className={`text-xs mt-1 font-medium ${trend.isPositive ? 'text-success' : 'text-danger'}`}>
            {trend.isPositive ? '+' : ''}{trend.value}%
            <span className="text-dark-lighter font-normal ml-1">vs yesterday</span>
          </p>
        )}
      </div>
    </div>
  );
}

export default StatsCard;
