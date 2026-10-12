import React from 'react';
import { Clock, ShieldAlert, CheckCircle2, AlertTriangle, Cpu } from 'lucide-react';

interface ProgressIndicatorProps {
  currentSecond: number;
  totalWindowSec?: number;
  windowCount: number;
  totalAlerts: number;
  lastAlertTimestamp?: string | null;
}

export const ProgressIndicator: React.FC<ProgressIndicatorProps> = ({
  currentSecond,
  totalWindowSec = 60,
  windowCount,
  totalAlerts,
  lastAlertTimestamp
}) => {
  const percentage = Math.min(100, Math.max(0, (currentSecond / totalWindowSec) * 100));

  return (
    <div className="glass-card p-5 relative overflow-hidden">
      <div className="flex items-center justify-between mb-3 pb-2 border-b border-cyan-500/15">
        <h4 className="font-semibold text-sm text-slate-100 flex items-center gap-2 font-outfit">
          <Clock className="w-4 h-4 text-cyan-400" />
          60-Second Analysis Window Progress
        </h4>
        <span className="text-xs font-mono font-semibold text-cyan-400 bg-cyan-500/10 px-2.5 py-0.5 rounded-full border border-cyan-500/20">
          Window #{windowCount || 1}
        </span>
      </div>

      {/* Progress Bar */}
      <div className="space-y-1.5 my-3">
        <div className="flex justify-between text-xs text-slate-300">
          <span className="font-medium">Collecting Window Samples:</span>
          <span className="font-mono font-bold text-cyan-300">{currentSecond} / {totalWindowSec} sec ({percentage.toFixed(0)}%)</span>
        </div>
        <div className="h-3 w-full bg-navy-950 rounded-full overflow-hidden p-0.5 border border-cyan-500/20">
          <div
            className="h-full bg-gradient-to-r from-cyan-500 via-teal-400 to-blue-500 rounded-full transition-all duration-300 shadow-glow-cyan"
            style={{ width: `${percentage}%` }}
          />
        </div>
      </div>

      {/* Quick Alert Stats */}
      <div className="grid grid-cols-2 gap-3 pt-2 text-xs">
        <div className="p-2.5 rounded-lg bg-navy-950/60 border border-slate-800 flex items-center justify-between">
          <span className="text-slate-400">Total Anomaly Alerts:</span>
          <span className={`font-mono font-bold ${totalAlerts > 0 ? 'text-red-400' : 'text-emerald-400'}`}>
            {totalAlerts}
          </span>
        </div>

        <div className="p-2.5 rounded-lg bg-navy-950/60 border border-slate-800 flex items-center justify-between">
          <span className="text-slate-400">Last Alert:</span>
          <span className="font-mono text-slate-300">
            {lastAlertTimestamp ? new Date(lastAlertTimestamp).toLocaleTimeString() : 'None'}
          </span>
        </div>
      </div>
    </div>
  );
};
