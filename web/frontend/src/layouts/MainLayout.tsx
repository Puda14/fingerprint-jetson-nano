import { useState } from 'react';
import { Outlet, NavLink, useLocation } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import {
  LayoutDashboard,
  ScanLine,
  UserPlus,
  Users,
  Cpu,
  Settings,
  Menu,
  X,
  Fingerprint,
  Wifi,
  WifiOff,
  Activity,
} from 'lucide-react';
import { healthApi } from '../services/api';
import StatusBadge from '../components/StatusBadge';

const NAV_ITEMS = [
  { path: '/dashboard', label: 'Dashboard', icon: LayoutDashboard },
  { path: '/verify', label: 'Verify', icon: ScanLine },
  { path: '/enroll', label: 'Enroll', icon: UserPlus },
  { path: '/users', label: 'Users', icon: Users },
  { path: '/models', label: 'Models', icon: Cpu },
  { path: '/settings', label: 'Settings', icon: Settings },
];

function MainLayout() {
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const location = useLocation();

  const { data: health } = useQuery({
    queryKey: ['health'],
    queryFn: healthApi.get,
    refetchInterval: 10_000,
  });

  const sensorConnected = health?.data?.sensor?.connected ?? false;
  const systemStatus = health?.data?.status ?? 'unhealthy';

  const currentPage = NAV_ITEMS.find((item) =>
    location.pathname.startsWith(item.path),
  );

  return (
    <div className="flex h-screen bg-background overflow-hidden">
      {/* Mobile overlay */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 bg-black/40 z-40 lg:hidden"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      {/* Sidebar */}
      <aside
        className={`
          fixed lg:static inset-y-0 left-0 z-50
          w-64 bg-dark text-white flex flex-col
          transform transition-transform duration-200 ease-in-out
          ${sidebarOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0'}
        `}
      >
        {/* Logo */}
        <div className="flex items-center gap-3 px-5 py-4 border-b border-white/10">
          <div className="p-2 bg-primary rounded-lg">
            <Fingerprint size={24} className="text-white" />
          </div>
          <div>
            <h1 className="font-bold text-base">MDGT Edge</h1>
            <p className="text-xs text-gray-400">Fingerprint System</p>
          </div>
          <button
            onClick={() => setSidebarOpen(false)}
            className="ml-auto p-1 hover:bg-white/10 rounded lg:hidden"
          >
            <X size={20} />
          </button>
        </div>

        {/* Navigation */}
        <nav className="flex-1 py-3 px-3 space-y-1 overflow-y-auto">
          {NAV_ITEMS.map((item) => (
            <NavLink
              key={item.path}
              to={item.path}
              onClick={() => setSidebarOpen(false)}
              className={({ isActive }) =>
                `flex items-center gap-3 px-3 py-3 rounded-lg font-medium text-sm transition-colors min-h-touch
                ${isActive
                  ? 'bg-primary text-white'
                  : 'text-gray-300 hover:bg-white/10 hover:text-white'
                }`
              }
            >
              <item.icon size={20} />
              {item.label}
            </NavLink>
          ))}
        </nav>

        {/* Sensor status footer */}
        <div className="px-4 py-3 border-t border-white/10">
          <div className="flex items-center gap-2 text-sm">
            {sensorConnected ? (
              <>
                <Wifi size={16} className="text-success" />
                <span className="text-gray-300">Sensor Connected</span>
              </>
            ) : (
              <>
                <WifiOff size={16} className="text-danger" />
                <span className="text-gray-400">Sensor Disconnected</span>
              </>
            )}
          </div>
        </div>
      </aside>

      {/* Main content area */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Top bar */}
        <header className="bg-white border-b border-gray-200 px-4 py-3 flex items-center gap-4 shrink-0">
          <button
            onClick={() => setSidebarOpen(true)}
            className="p-2 hover:bg-gray-100 rounded-lg lg:hidden min-h-touch min-w-touch flex items-center justify-center"
          >
            <Menu size={22} />
          </button>

          <h2 className="text-lg font-semibold text-dark">
            {currentPage?.label ?? 'MDGT Edge'}
          </h2>

          <div className="ml-auto flex items-center gap-3">
            <StatusBadge
              status={systemStatus === 'healthy' ? 'online' : systemStatus === 'degraded' ? 'warning' : 'error'}
              label={systemStatus === 'healthy' ? 'System OK' : systemStatus === 'degraded' ? 'Degraded' : 'Unhealthy'}
            />
            <div className="hidden sm:flex items-center gap-2 text-sm text-dark-lighter">
              <Activity size={16} />
              <span>{health?.data?.device?.cpu_usage?.toFixed(0) ?? '--'}% CPU</span>
            </div>
          </div>
        </header>

        {/* Page content */}
        <main className="flex-1 overflow-y-auto p-4 lg:p-6">
          <Outlet />
        </main>
      </div>
    </div>
  );
}

export default MainLayout;
