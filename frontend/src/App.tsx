import React, { useState } from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { TelemetryProvider } from './context/TelemetryContext';
import { ThemeProvider } from './context/ThemeContext';
import { Navbar } from './components/layout/Navbar';
import { Sidebar } from './components/layout/Sidebar';
import { DemoBanner } from './components/layout/DemoBanner';

import { DashboardView } from './views/DashboardView';
import { AnalyticsView } from './views/AnalyticsView';
import { PipelineView } from './views/PipelineView';
import { DetectionView } from './views/DetectionView';
import { HistoryView } from './views/HistoryView';
import { ExperimentsView } from './views/ExperimentsView';
import { SettingsView } from './views/SettingsView';

export const App: React.FC = () => {
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  return (
    <ThemeProvider>
      <TelemetryProvider>
        <Router>
          <div className="min-h-screen bg-navy-950 text-slate-100 flex flex-col font-sans bg-grid-pattern selection:bg-cyan-500 selection:text-navy-950">
            {/* Top Navigation Bar */}
            <Navbar
              mobileMenuOpen={mobileMenuOpen}
              setMobileMenuOpen={setMobileMenuOpen}
            />

            {/* Synthetic Demo Mode Banner */}
            <DemoBanner />

            <div className="flex-1 flex pt-0">
              {/* Left Sidebar Menu */}
              <Sidebar
                mobileMenuOpen={mobileMenuOpen}
                setMobileMenuOpen={setMobileMenuOpen}
              />

              {/* Main Content Area */}
              <main className="flex-1 lg:pl-64 transition-all p-4 sm:p-6 lg:p-8 max-w-7xl mx-auto w-full">
                <Routes>
                  <Route path="/" element={<DashboardView />} />
                  <Route path="/analytics" element={<AnalyticsView />} />
                  <Route path="/pipeline" element={<PipelineView />} />
                  <Route path="/detection" element={<DetectionView />} />
                  <Route path="/history" element={<HistoryView />} />
                  <Route path="/experiments" element={<ExperimentsView />} />
                  <Route path="/settings" element={<SettingsView />} />
                  <Route path="*" element={<Navigate to="/" replace />} />
                </Routes>
              </main>
            </div>
          </div>
        </Router>
      </TelemetryProvider>
    </ThemeProvider>
  );
};

export default App;
