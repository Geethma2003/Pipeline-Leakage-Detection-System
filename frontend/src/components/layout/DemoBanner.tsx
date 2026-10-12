import React from 'react';
import { useTelemetry } from '../../context/TelemetryContext';
import { AlertTriangle, Play, ShieldAlert, Cpu } from 'lucide-react';

export const DemoBanner: React.FC = () => {
  const { demoMode, demoScenario, setDemoScenario, toggleDemoMode, diagnostics } = useTelemetry();

  if (!demoMode && diagnostics?.connection_status === 'CONNECTED') {
    return null;
  }

  return (
    <div className="bg-gradient-to-r from-amber-500/15 via-purple-500/15 to-cyan-500/15 border-b border-amber-500/30 px-4 py-2 text-xs flex flex-wrap items-center justify-between gap-2 shadow-sm">
      <div className="flex items-center gap-2">
        <span className="flex h-2.5 w-2.5 relative">
          <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-amber-400 opacity-75"></span>
          <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-amber-500"></span>
        </span>
        <span className="font-semibold text-amber-400 tracking-wide uppercase flex items-center gap-1.5">
          <AlertTriangle className="w-3.5 h-3.5" />
          {demoMode ? 'DEMO MODE ACTIVE — SYNTHETIC TIME-SERIES DATA' : 'HARDWARE DISCONNECTED — DEMO FALLBACK'}
        </span>
        <span className="hidden md:inline text-slate-400">|</span>
        <span className="hidden md:inline text-slate-300">
          Synthetic scenario simulation for system evaluation & UI demonstration
        </span>
      </div>

      <div className="flex items-center gap-2">
        <span className="text-slate-300 font-medium hidden sm:inline">Scenario:</span>
        <div className="inline-flex rounded-lg bg-navy-900/90 p-0.5 border border-amber-500/30">
          <button
            onClick={() => setDemoScenario('normal')}
            className={`px-2.5 py-1 rounded-md transition-all text-xs font-medium ${
              demoScenario === 'normal'
                ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 shadow'
                : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            Normal State
          </button>
          <button
            onClick={() => setDemoScenario('pump_disturbance')}
            className={`px-2.5 py-1 rounded-md transition-all text-xs font-medium ${
              demoScenario === 'pump_disturbance'
                ? 'bg-amber-500/20 text-amber-300 border border-amber-500/40 shadow'
                : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            Pump Disturbance
          </button>
          <button
            onClick={() => setDemoScenario('confirmed_leak')}
            className={`px-2.5 py-1 rounded-md transition-all text-xs font-medium ${
              demoScenario === 'confirmed_leak'
                ? 'bg-red-500/20 text-red-300 border border-red-500/40 shadow'
                : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            Sustained Anomaly
          </button>
        </div>

        {diagnostics?.connection_status === 'CONNECTED' && (
          <button
            onClick={() => toggleDemoMode(false)}
            className="ml-2 px-2.5 py-1 rounded-md bg-cyan-500/20 text-cyan-300 hover:bg-cyan-500/30 border border-cyan-500/40 transition-all font-medium flex items-center gap-1"
          >
            <Cpu className="w-3 h-3" />
            Switch to Live Arduino Uno
          </button>
        )}
      </div>
    </div>
  );
};
