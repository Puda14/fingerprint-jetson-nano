import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import {
  Users,
  ScanLine,
  CheckCircle,
  Clock,
  UserPlus,
  Fingerprint,
} from 'lucide-react';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from 'recharts';
import { statsApi, logsApi } from '../services/api';
import StatsCard from '../components/StatsCard';
import LoadingSpinner from '../components/LoadingSpinner';
import type { VerificationLog } from '../types';

function DashboardPage() {
  const navigate = useNavigate();

  const { data: statsRes, isLoading: statsLoading } = useQuery({
    queryKey: ['stats'],
    queryFn: statsApi.get,
    refetchInterval: 30_000,
  });

  const { data: logsRes, isLoading: logsLoading } = useQuery({
    queryKey: ['logs', 'recent'],
    queryFn: () => logsApi.list({ page: 1, limit: 20 }),
    refetchInterval: 15_000,
  });

  const stats = statsRes?.data;
  const logs = logsRes?.data ?? [];
  const chartData = stats?.verifications_by_day ?? [];

  if (statsLoading) {
    return <LoadingSpinner size="lg" className="mt-20" />;
  }

  return (
    <div className="space-y-6">
      {/* Stats cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4">
        <StatsCard
          icon={Users}
          label="Total Users"
          value={stats?.total_users ?? 0}
          color="primary"
        />
        <StatsCard
          icon={ScanLine}
          label="Verifications Today"
          value={stats?.verifications_today ?? 0}
          color="success"
        />
        <StatsCard
          icon={CheckCircle}
          label="Acceptance Rate"
          value={`${(stats?.acceptance_rate ?? 0).toFixed(1)}%`}
          color="warning"
        />
        <StatsCard
          icon={Clock}
          label="Avg Latency"
          value={`${(stats?.avg_latency_ms ?? 0).toFixed(0)}ms`}
          color="danger"
        />
      </div>

      {/* Quick actions */}
      <div className="flex flex-wrap gap-3">
        <button onClick={() => navigate('/enroll')} className="btn-primary">
          <UserPlus size={18} />
          New Enrollment
        </button>
        <button onClick={() => navigate('/verify')} className="btn-success">
          <Fingerprint size={18} />
          Start Verification
        </button>
      </div>

      {/* Chart */}
      <div className="card">
        <h3 className="text-base font-semibold text-dark mb-4">
          Verifications - Last 7 Days
        </h3>
        {chartData.length > 0 ? (
          <ResponsiveContainer width="100%" height={280}>
            <LineChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#ECF0F1" />
              <XAxis
                dataKey="date"
                tick={{ fontSize: 12, fill: '#5D6D7E' }}
                tickFormatter={(v: string) => {
                  const d = new Date(v);
                  return `${d.getMonth() + 1}/${d.getDate()}`;
                }}
              />
              <YAxis tick={{ fontSize: 12, fill: '#5D6D7E' }} />
              <Tooltip
                contentStyle={{
                  borderRadius: '8px',
                  border: '1px solid #ECF0F1',
                  fontSize: '13px',
                }}
              />
              <Legend />
              <Line
                type="monotone"
                dataKey="accepted"
                stroke="#27AE60"
                strokeWidth={2}
                dot={{ r: 4 }}
                name="Accepted"
              />
              <Line
                type="monotone"
                dataKey="rejected"
                stroke="#E74C3C"
                strokeWidth={2}
                dot={{ r: 4 }}
                name="Rejected"
              />
              <Line
                type="monotone"
                dataKey="total"
                stroke="#1B4F72"
                strokeWidth={2}
                dot={{ r: 4 }}
                name="Total"
              />
            </LineChart>
          </ResponsiveContainer>
        ) : (
          <div className="flex items-center justify-center h-64 text-dark-lighter">
            No verification data yet
          </div>
        )}
      </div>

      {/* Recent logs */}
      <div className="card">
        <h3 className="text-base font-semibold text-dark mb-4">
          Recent Verification Logs
        </h3>
        {logsLoading ? (
          <LoadingSpinner />
        ) : logs.length === 0 ? (
          <p className="text-center text-dark-lighter py-8">No logs yet</p>
        ) : (
          <div className="overflow-x-auto -mx-5">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-gray-50 border-b border-gray-100">
                  <th className="px-5 py-2.5 text-left font-semibold text-dark-lighter">Time</th>
                  <th className="px-5 py-2.5 text-left font-semibold text-dark-lighter">User</th>
                  <th className="px-5 py-2.5 text-left font-semibold text-dark-lighter">Mode</th>
                  <th className="px-5 py-2.5 text-left font-semibold text-dark-lighter">Result</th>
                  <th className="px-5 py-2.5 text-left font-semibold text-dark-lighter">Confidence</th>
                  <th className="px-5 py-2.5 text-left font-semibold text-dark-lighter">Latency</th>
                </tr>
              </thead>
              <tbody>
                {logs.map((log: VerificationLog) => (
                  <tr key={log.id} className="border-b border-gray-50 last:border-0">
                    <td className="px-5 py-2.5 text-dark-lighter whitespace-nowrap">
                      {new Date(log.timestamp).toLocaleTimeString()}
                    </td>
                    <td className="px-5 py-2.5">{log.user_name ?? 'Unknown'}</td>
                    <td className="px-5 py-2.5">
                      <span className="capitalize">{log.mode}</span>
                    </td>
                    <td className="px-5 py-2.5">
                      <span
                        className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold ${
                          log.result === 'accept'
                            ? 'bg-success/10 text-success-dark'
                            : 'bg-danger/10 text-danger-dark'
                        }`}
                      >
                        {log.result === 'accept' ? 'ACCEPT' : 'REJECT'}
                      </span>
                    </td>
                    <td className="px-5 py-2.5">{(log.confidence * 100).toFixed(1)}%</td>
                    <td className="px-5 py-2.5">{log.latency_ms}ms</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

export default DashboardPage;
