import { useState, useMemo, useCallback } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import toast from 'react-hot-toast';
import {
  Search,
  X,
  Edit3,
  Trash2,
  UserX,
  Fingerprint,
  Clock,
} from 'lucide-react';
import { usersApi, logsApi } from '../services/api';
import DataTable from '../components/DataTable';
import type { Column } from '../components/DataTable';
import StatusBadge from '../components/StatusBadge';
import ConfirmDialog from '../components/ConfirmDialog';
import LoadingSpinner from '../components/LoadingSpinner';
import type { User, VerificationLog } from '../types';

function UsersPage() {
  const queryClient = useQueryClient();

  // Filters
  const [search, setSearch] = useState('');
  const [departmentFilter, setDepartmentFilter] = useState('');
  const [roleFilter, setRoleFilter] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [page, setPage] = useState(1);
  const limit = 15;

  // Detail panel
  const [selectedUser, setSelectedUser] = useState<User | null>(null);
  const [detailTab, setDetailTab] = useState<'info' | 'fingers' | 'logs'>('info');

  // Dialogs
  const [deleteUser, setDeleteUser] = useState<User | null>(null);
  const [editingUser, setEditingUser] = useState<User | null>(null);
  const [editForm, setEditForm] = useState({ full_name: '', department: '', role: '' });

  // Queries
  const { data: usersRes, isLoading } = useQuery({
    queryKey: ['users', page, search, departmentFilter, roleFilter, statusFilter],
    queryFn: () =>
      usersApi.list({
        page,
        limit,
        search: search || undefined,
        department: departmentFilter || undefined,
        role: roleFilter || undefined,
        status: statusFilter || undefined,
      }),
  });

  const users = usersRes?.data ?? [];
  const totalPages = usersRes ? Math.ceil(usersRes.total / limit) : 1;

  const { data: userLogsRes } = useQuery({
    queryKey: ['logs', 'user', selectedUser?.id],
    queryFn: () => logsApi.list({ user_id: selectedUser!.id, limit: 10 }),
    enabled: !!selectedUser && detailTab === 'logs',
  });

  // Derive unique departments and roles for filters
  const departments = useMemo(() => {
    const set = new Set(users.map((u) => u.department).filter(Boolean));
    return Array.from(set).sort();
  }, [users]);

  const roles = useMemo(() => {
    const set = new Set(users.map((u) => u.role).filter(Boolean));
    return Array.from(set).sort();
  }, [users]);

  // Mutations
  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: number; data: Partial<User> }) =>
      usersApi.update(id, data),
    onSuccess: () => {
      toast.success('User updated');
      queryClient.invalidateQueries({ queryKey: ['users'] });
      setEditingUser(null);
    },
    onError: (err: Error) => toast.error(err.message),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: number) => usersApi.delete(id),
    onSuccess: () => {
      toast.success('User deleted');
      queryClient.invalidateQueries({ queryKey: ['users'] });
      setDeleteUser(null);
      if (selectedUser?.id === deleteUser?.id) setSelectedUser(null);
    },
    onError: (err: Error) => toast.error(err.message),
  });

  const deactivateMutation = useMutation({
    mutationFn: (id: number) => usersApi.update(id, { status: 'inactive' }),
    onSuccess: () => {
      toast.success('User deactivated');
      queryClient.invalidateQueries({ queryKey: ['users'] });
    },
    onError: (err: Error) => toast.error(err.message),
  });

  const startEdit = useCallback((user: User) => {
    setEditingUser(user);
    setEditForm({
      full_name: user.full_name,
      department: user.department,
      role: user.role,
    });
  }, []);

  // Table columns
  const columns: Column<User>[] = useMemo(
    () => [
      { key: 'id', header: 'ID', sortable: true, width: '60px' },
      { key: 'employee_id', header: 'Employee ID', sortable: true },
      { key: 'full_name', header: 'Name', sortable: true },
      { key: 'department', header: 'Department', sortable: true },
      { key: 'role', header: 'Role', sortable: true },
      {
        key: 'fingerprints',
        header: 'Fingers',
        render: (user: User) => (
          <span className="text-sm font-medium">
            {user.fingerprints?.length ?? 0}
          </span>
        ),
      },
      {
        key: 'status',
        header: 'Status',
        render: (user: User) => <StatusBadge status={user.status} />,
      },
      {
        key: 'actions',
        header: 'Actions',
        width: '140px',
        render: (user: User) => (
          <div className="flex items-center gap-1" onClick={(e) => e.stopPropagation()}>
            <button
              onClick={() => startEdit(user)}
              className="p-2 hover:bg-gray-100 rounded-lg transition-colors"
              title="Edit"
            >
              <Edit3 size={16} className="text-primary" />
            </button>
            <button
              onClick={() => deactivateMutation.mutate(user.id)}
              className="p-2 hover:bg-gray-100 rounded-lg transition-colors"
              title="Deactivate"
            >
              <UserX size={16} className="text-warning" />
            </button>
            <button
              onClick={() => setDeleteUser(user)}
              className="p-2 hover:bg-gray-100 rounded-lg transition-colors"
              title="Delete"
            >
              <Trash2 size={16} className="text-danger" />
            </button>
          </div>
        ),
      },
    ],
    [startEdit, deactivateMutation],
  );

  return (
    <div className="space-y-4">
      {/* Search & Filters */}
      <div className="card">
        <div className="flex flex-wrap items-center gap-3">
          <div className="relative flex-1 min-w-[200px]">
            <Search size={18} className="absolute left-3 top-1/2 -translate-y-1/2 text-dark-lighter" />
            <input
              type="text"
              value={search}
              onChange={(e) => { setSearch(e.target.value); setPage(1); }}
              placeholder="Search by name or employee ID..."
              className="input-field pl-10"
            />
          </div>
          <select
            value={departmentFilter}
            onChange={(e) => { setDepartmentFilter(e.target.value); setPage(1); }}
            className="select-field w-auto min-w-[150px]"
          >
            <option value="">All Departments</option>
            {departments.map((d) => (
              <option key={d} value={d}>{d}</option>
            ))}
          </select>
          <select
            value={roleFilter}
            onChange={(e) => { setRoleFilter(e.target.value); setPage(1); }}
            className="select-field w-auto min-w-[120px]"
          >
            <option value="">All Roles</option>
            {roles.map((r) => (
              <option key={r} value={r}>{r}</option>
            ))}
          </select>
          <select
            value={statusFilter}
            onChange={(e) => { setStatusFilter(e.target.value); setPage(1); }}
            className="select-field w-auto min-w-[120px]"
          >
            <option value="">All Status</option>
            <option value="active">Active</option>
            <option value="inactive">Inactive</option>
            <option value="suspended">Suspended</option>
          </select>
        </div>
      </div>

      <div className="flex gap-4">
        {/* Table */}
        <div className="flex-1 min-w-0">
          <DataTable<User>
            columns={columns}
            data={users}
            keyExtractor={(u) => u.id}
            isLoading={isLoading}
            emptyMessage="No users found"
            page={page}
            totalPages={totalPages}
            onPageChange={setPage}
            onRowClick={(u) => setSelectedUser(u)}
          />
        </div>

        {/* Detail Panel (slide-in) */}
        {selectedUser && (
          <div className="w-80 shrink-0 card space-y-4 self-start hidden lg:block">
            <div className="flex items-center justify-between">
              <h3 className="font-semibold text-dark">User Detail</h3>
              <button
                onClick={() => setSelectedUser(null)}
                className="p-1 hover:bg-gray-100 rounded"
              >
                <X size={18} />
              </button>
            </div>

            {/* Tabs */}
            <div className="flex border-b border-gray-200">
              {(['info', 'fingers', 'logs'] as const).map((tab) => (
                <button
                  key={tab}
                  onClick={() => setDetailTab(tab)}
                  className={`flex-1 py-2 text-sm font-medium border-b-2 transition-colors capitalize ${
                    detailTab === tab
                      ? 'border-primary text-primary'
                      : 'border-transparent text-dark-lighter hover:text-dark'
                  }`}
                >
                  {tab}
                </button>
              ))}
            </div>

            {/* Tab content */}
            {detailTab === 'info' && (
              <div className="space-y-3 text-sm">
                <InfoRow label="Employee ID" value={selectedUser.employee_id} />
                <InfoRow label="Full Name" value={selectedUser.full_name} />
                <InfoRow label="Department" value={selectedUser.department || '-'} />
                <InfoRow label="Role" value={selectedUser.role || '-'} />
                <InfoRow label="Status" value={selectedUser.status} />
                <InfoRow label="Created" value={new Date(selectedUser.created_at).toLocaleDateString()} />
              </div>
            )}

            {detailTab === 'fingers' && (
              <div className="space-y-2">
                {selectedUser.fingerprints?.length ? (
                  selectedUser.fingerprints.map((fp) => (
                    <div
                      key={fp.id}
                      className="flex items-center justify-between py-2 px-3 bg-gray-50 rounded-lg"
                    >
                      <div className="flex items-center gap-2">
                        <Fingerprint size={16} className="text-primary" />
                        <span className="capitalize text-sm">
                          {fp.finger_type.replace('_', ' ')}
                        </span>
                      </div>
                      <span
                        className={`text-xs font-semibold ${
                          fp.quality_score >= 80
                            ? 'text-success'
                            : fp.quality_score >= 60
                            ? 'text-warning'
                            : 'text-danger'
                        }`}
                      >
                        {fp.quality_score}%
                      </span>
                    </div>
                  ))
                ) : (
                  <p className="text-sm text-dark-lighter text-center py-4">
                    No fingerprints enrolled
                  </p>
                )}
              </div>
            )}

            {detailTab === 'logs' && (
              <div className="space-y-2">
                {userLogsRes?.data?.length ? (
                  userLogsRes.data.map((log: VerificationLog) => (
                    <div key={log.id} className="flex items-center justify-between py-2 px-3 bg-gray-50 rounded-lg text-xs">
                      <div className="flex items-center gap-2">
                        <Clock size={14} className="text-dark-lighter" />
                        <span>{new Date(log.timestamp).toLocaleString()}</span>
                      </div>
                      <span
                        className={`font-semibold ${
                          log.result === 'accept' ? 'text-success' : 'text-danger'
                        }`}
                      >
                        {log.result.toUpperCase()}
                      </span>
                    </div>
                  ))
                ) : (
                  <p className="text-sm text-dark-lighter text-center py-4">
                    No verification logs
                  </p>
                )}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Edit Modal */}
      {editingUser && (
        <div className="fixed inset-0 z-50 flex items-center justify-center">
          <div className="fixed inset-0 bg-black/50" onClick={() => setEditingUser(null)} />
          <div className="relative bg-white rounded-xl shadow-xl p-6 max-w-md w-full mx-4">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-semibold">Edit User</h3>
              <button onClick={() => setEditingUser(null)} className="p-1 hover:bg-gray-100 rounded">
                <X size={18} />
              </button>
            </div>
            <div className="space-y-3">
              <div>
                <label className="block text-sm font-medium text-dark-lighter mb-1">Full Name</label>
                <input
                  type="text"
                  value={editForm.full_name}
                  onChange={(e) => setEditForm((f) => ({ ...f, full_name: e.target.value }))}
                  className="input-field"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-dark-lighter mb-1">Department</label>
                <input
                  type="text"
                  value={editForm.department}
                  onChange={(e) => setEditForm((f) => ({ ...f, department: e.target.value }))}
                  className="input-field"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-dark-lighter mb-1">Role</label>
                <input
                  type="text"
                  value={editForm.role}
                  onChange={(e) => setEditForm((f) => ({ ...f, role: e.target.value }))}
                  className="input-field"
                />
              </div>
            </div>
            <div className="flex justify-end gap-3 mt-6">
              <button onClick={() => setEditingUser(null)} className="btn-outline">Cancel</button>
              <button
                onClick={() => updateMutation.mutate({ id: editingUser.id, data: editForm })}
                disabled={updateMutation.isPending}
                className="btn-primary"
              >
                {updateMutation.isPending ? <LoadingSpinner size="sm" /> : 'Save'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Delete Confirmation */}
      <ConfirmDialog
        isOpen={!!deleteUser}
        title="Delete User"
        message={`Are you sure you want to delete ${deleteUser?.full_name}? This action cannot be undone and will remove all enrolled fingerprints.`}
        confirmLabel="Delete"
        onConfirm={() => deleteUser && deleteMutation.mutate(deleteUser.id)}
        onCancel={() => setDeleteUser(null)}
      />
    </div>
  );
}

function InfoRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between">
      <span className="text-dark-lighter">{label}</span>
      <span className="font-medium text-dark capitalize">{value}</span>
    </div>
  );
}

export default UsersPage;
