import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { ConfigProvider, theme, Spin } from 'antd';
import koKR from 'antd/locale/ko_KR';
import { AuthProvider, useAuth } from './contexts/AuthContext';
import { RecoveryProvider } from './hooks/useRecoverySignal';
import AppLayout from './components/AppLayout';
import LoginPage from './pages/LoginPage';
import AuthCallbackPage from './pages/AuthCallbackPage';
import { lazy, Suspense, type ReactNode } from 'react';

const DashboardPage = lazy(() => import('./pages/DashboardPage'));
const TradingPage = lazy(() => import('./pages/TradingPage'));
const AnalyticsPage = lazy(() => import('./pages/AnalyticsPage'));
const SettingsPage = lazy(() => import('./pages/SettingsPage'));
const ReportsPage = lazy(() => import('./pages/ReportsPage'));
const GuidePage = lazy(() => import('./pages/GuidePage'));
const SentimentImpactPage = lazy(() => import('./pages/SentimentImpactPage'));
const DislocationPaperPage = lazy(() => import('./pages/DislocationPaperPage'));

/* ── Auth Guard ─────────────────────────────────────────── */

function RequireAuth({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth();

  if (loading) return null; // 세션 복원 중
  if (!user) return <Navigate to="/login" replace />;

  return <>{children}</>;
}

/* ── App ────────────────────────────────────────────────── */

export default function App() {
  return (
    <ConfigProvider
      locale={koKR}
      theme={{
        algorithm: theme.darkAlgorithm,
        token: {
          colorPrimary: '#1668dc',
          borderRadius: 6,
          fontFamily:
            "'Freesentation', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
        },
      }}
    >
      <AuthProvider>
        <RecoveryProvider>
          <BrowserRouter>
            <Routes>
              {/* Public routes */}
              <Route path="/login" element={<LoginPage />} />
              <Route path="/auth/callback" element={<AuthCallbackPage />} />

              {/* Protected routes */}
              <Route
                element={
                  <RequireAuth>
                    <Suspense fallback={
                      <div style={{ textAlign: 'center', padding: 80 }}>
                        <Spin size="large" />
                      </div>
                    }>
                      <AppLayout />
                    </Suspense>
                  </RequireAuth>
                }
              >
                <Route index element={<DashboardPage />} />
                <Route path="trading" element={<TradingPage />} />
                <Route path="analytics" element={<AnalyticsPage />} />
                <Route path="settings" element={<SettingsPage />} />
                <Route path="reports" element={<ReportsPage />} />
                <Route path="guide" element={<GuidePage />} />
                <Route path="sentiment-impact" element={<SentimentImpactPage />} />
                <Route path="dislocation-paper" element={<DislocationPaperPage />} />
              </Route>

              {/* Fallback */}
              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
          </BrowserRouter>
        </RecoveryProvider>
      </AuthProvider>
    </ConfigProvider>
  );
}
