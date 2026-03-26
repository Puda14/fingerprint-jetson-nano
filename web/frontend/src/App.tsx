import { Routes, Route, Navigate } from 'react-router-dom';
import MainLayout from './layouts/MainLayout';
import DashboardPage from './pages/DashboardPage';
import VerificationPage from './pages/VerificationPage';
import EnrollmentPage from './pages/EnrollmentPage';
import UsersPage from './pages/UsersPage';
import ModelsPage from './pages/ModelsPage';
import SettingsPage from './pages/SettingsPage';

function App() {
  return (
    <Routes>
      <Route path="/" element={<MainLayout />}>
        <Route index element={<Navigate to="/dashboard" replace />} />
        <Route path="dashboard" element={<DashboardPage />} />
        <Route path="verify" element={<VerificationPage />} />
        <Route path="enroll" element={<EnrollmentPage />} />
        <Route path="users" element={<UsersPage />} />
        <Route path="models" element={<ModelsPage />} />
        <Route path="settings" element={<SettingsPage />} />
      </Route>
    </Routes>
  );
}

export default App;
