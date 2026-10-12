import React, { useState } from 'react';
import { useTelemetry } from '../../context/TelemetryContext';
import { useTheme } from '../../context/ThemeContext';
import {
  Activity,
  Radio,
  Sun,
  Moon,
  Menu,
  X,
  Bell,
  CloudCheck
} from 'lucide-react';

interface NavbarProps {
  mobileMenuOpen: boolean;
  setMobileMenuOpen: (open: boolean) => void;
}

export const Navbar: React.FC<NavbarProps> = ({ mobileMenuOpen, setMobileMenuOpen }) => {
  const { systemState, demoMode, toggleDemoMode, diagnostics, isConnected, latestDecision, firebaseStatus, currentWindowSec } = useTelemetry();
  const { theme, toggleTheme } = useTheme();
  const [showNotifications, setShowNotifications] = useState(false);

  const getStateBadge = () => {
    switch (systemState) {
      case 'INITIALIZING':
        return (
          <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-blue-500/15 text-blue-400 border border-blue-500/30">
            <span className="w-2 h-2 rounded-full bg-blue-400 animate-pulse"></span>
            EVALUATING WINDOW ({currentWindowSec}/60s)
          </span>
        );
      case 'NORMAL':
        return (
          <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-emerald-500/15 text-emerald-400 border border-emerald-500/30">
            <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
            NORMAL OPERATION
          </span>
        );
      case 'SUSPECTED_ANOMALY':
        return (
          <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-amber-500/15 text-amber-400 border border-amber-500/30">
            <span className="w-2 h-2 rounded-full bg-amber-400 animate-ping"></span>
            INVESTIGATING ANOMALY
          </span>
        );
      case 'CONFIRMED_LEAK':
        return (
          <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-bold bg-red-500/20 text-red-400 border border-red-500/50 animate-pulse-glow shadow-glow-red">
            <span className="w-2.5 h-2.5 rounded-full bg-red-500 animate-ping"></span>
            POSSIBLE LEAK ALARM
          </span>
        );
      case 'SENSOR_FAULT':
        return (
          <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-purple-500/15 text-purple-400 border border-purple-500/30">
            <span className="w-2 h-2 rounded-full bg-purple-400"></span>
            SENSOR / FAULT
          </span>
        );
      default:
        return null;
    }
  };

  return (
    <header className="sticky top-0 z-40 w-full bg-navy-900/90 backdrop-blur-md border-b border-cyan-500/15 transition-colors">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between gap-4">
        {/* Left Branding & Mobile Toggle */}
        <div className="flex items-center gap-3">
          <button
            onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
            className="lg:hidden p-2 rounded-lg text-slate-400 hover:text-white hover:bg-cyan-500/10 transition"
            aria-label="Toggle menu"
          >
            {mobileMenuOpen ? <X className="w-6 h-6" /> : <Menu className="w-6 h-6" />}
          </button>

          <div className="flex items-center gap-2.5">
            <div className="w-9 h-9 rounded-xl bg-gradient-to-tr from-cyan-600 via-teal-500 to-blue-500 p-0.5 shadow-glow-cyan">
              <div className="w-full h-full bg-navy-950 rounded-[10px] flex items-center justify-center">
                <Activity className="w-5 h-5 text-cyan-400 animate-pulse" />
              </div>
            </div>
            <div>
              <span className="font-extrabold text-lg tracking-tight bg-gradient-to-r from-cyan-400 via-teal-300 to-blue-400 bg-clip-text text-transparent font-outfit">
                AquaGuard <span className="text-white font-light">AI</span>
              </span>
              <span className="hidden sm:inline text-[10px] uppercase font-mono tracking-widest text-slate-400 block -mt-1">
                Smart Pipeline Monitoring
              </span>
            </div>
          </div>
        </div>

        {/* Center Live System Status */}
        <div className="hidden md:flex items-center gap-3">
          {getStateBadge()}

          <div className="flex items-center gap-2 px-2.5 py-1 rounded-full bg-navy-950 border border-slate-800 text-xs">
            <Radio className={`w-3.5 h-3.5 ${isConnected ? 'text-cyan-400 animate-pulse' : 'text-slate-500'}`} />
            <span className="text-slate-400 font-mono text-[11px]">
              {diagnostics?.connection_status === 'CONNECTED' ? (
                <span className="text-emerald-400 font-medium">Arduino Uno Receiver — {diagnostics.serial_port || 'COM14'}</span>
              ) : diagnostics?.connection_status === 'PORT_LOCKED' ? (
                <span className="text-amber-400 font-medium">COM Port Locked</span>
              ) : (
                <span className="text-cyan-300 font-medium">Demo Mode</span>
              )}
            </span>
          </div>

          {/* Firestore Connection Indicator */}
          <div className="hidden xl:flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-navy-950 border border-cyan-500/20 text-xs text-slate-400 font-mono text-[11px]">
            <CloudCheck className={`w-3.5 h-3.5 ${firebaseStatus.initialized && firebaseStatus.online ? 'text-cyan-400' : 'text-amber-400'}`} />
            <span>
              {firebaseStatus.initialized && firebaseStatus.online ? (
                <span className="text-cyan-300 font-medium">Firestore: aquaguard-pipeline</span>
              ) : (
                <span className="text-amber-400 font-medium">Firestore Offline ({firebaseStatus.last_error || 'Disconnected'})</span>
              )}
            </span>
          </div>
        </div>

        {/* Right Actions & Controls */}
        <div className="flex items-center gap-2.5">
          {/* Demo Mode Toggle Switch */}
          <div className="flex items-center gap-2 bg-navy-950 px-2.5 py-1.5 rounded-lg border border-cyan-500/20 text-xs">
            <span className="text-slate-400 font-medium hidden sm:inline">Demo</span>
            <button
              onClick={() => toggleDemoMode(!demoMode)}
              className={`relative inline-flex h-5 w-9 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none ${
                demoMode ? 'bg-cyan-500' : 'bg-slate-700'
              }`}
            >
              <span
                className={`pointer-events-none inline-block h-4 w-4 transform rounded-full bg-navy-950 shadow-lg ring-0 transition duration-200 ease-in-out ${
                  demoMode ? 'translate-x-4' : 'translate-x-0'
                }`}
              />
            </button>
          </div>

          {/* Notifications Dropdown */}
          <div className="relative">
            <button
              onClick={() => setShowNotifications(!showNotifications)}
              className="relative p-2 rounded-lg text-slate-400 hover:text-cyan-400 hover:bg-cyan-500/10 transition border border-transparent hover:border-cyan-500/20"
              aria-label="Notifications"
            >
              <Bell className="w-5 h-5" />
              {latestDecision && latestDecision.decision !== 'NORMAL' && (
                <span className="absolute top-1.5 right-1.5 w-2.5 h-2.5 rounded-full bg-red-500 animate-ping"></span>
              )}
            </button>

            {showNotifications && (
              <div className="absolute right-0 mt-2 w-80 glass-card p-4 shadow-2xl z-50">
                <div className="flex items-center justify-between mb-3 pb-2 border-b border-cyan-500/20">
                  <h4 className="font-semibold text-sm text-cyan-300 flex items-center gap-1.5">
                    <Bell className="w-4 h-4" /> System Alerts
                  </h4>
                  <span className="text-[10px] font-mono text-slate-400">60s Decision Log</span>
                </div>
                {latestDecision ? (
                  <div className="space-y-2">
                    <div className="p-2.5 rounded-lg bg-navy-950 border border-cyan-500/20 text-xs">
                      <div className="flex items-center justify-between font-semibold text-cyan-400 mb-1">
                        <span>{latestDecision.decision}</span>
                        <span className="text-[10px] font-mono text-slate-400">
                          {new Date(latestDecision.timestamp).toLocaleTimeString()}
                        </span>
                      </div>
                      <p className="text-slate-300 text-[11px] leading-relaxed">{latestDecision.reasoning}</p>
                    </div>
                  </div>
                ) : (
                  <p className="text-xs text-slate-400 italic text-center py-4">No recent anomaly notifications.</p>
                )}
              </div>
            )}
          </div>

          {/* Theme Switcher */}
          <button
            onClick={toggleTheme}
            className="p-2 rounded-lg text-slate-400 hover:text-cyan-400 hover:bg-cyan-500/10 transition border border-transparent hover:border-cyan-500/20"
            aria-label="Toggle theme"
          >
            {theme === 'dark' ? <Sun className="w-5 h-5" /> : <Moon className="w-5 h-5" />}
          </button>
        </div>
      </div>
    </header>
  );
};
