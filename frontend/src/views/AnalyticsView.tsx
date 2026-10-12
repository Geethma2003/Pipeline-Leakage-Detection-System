import React, { useState } from 'react';
import { useTelemetry } from '../context/TelemetryContext';
import { LineChart, Line, XAxis, YAxis, Tooltip, Legend, CartesianGrid, ResponsiveContainer, BarChart, Bar } from 'recharts';
import { LineChart as AnalyticsIcon, Pause, Play, Download, Clock } from 'lucide-react';

export const AnalyticsView: React.FC = () => {
  const { telemetryHistory, baseline, isPaused, setPaused } = useTelemetry();
  const [timeWindow, setTimeWindow] = useState<'1m' | '5m' | '15m' | 'all'>('1m');

  const getFilteredHistory = () => {
    switch (timeWindow) {
      case '1m': return telemetryHistory.slice(-60);
      case '5m': return telemetryHistory.slice(-300);
      case '15m': return telemetryHistory.slice(-900);
      default: return telemetryHistory;
    }
  };

  const filteredData = getFilteredHistory();

  const exportCsv = () => {
    if (!filteredData.length) return;
    const headers = ["second_index", "s1_rms", "s2_rms", "s1_p2p", "s2_p2p", "s1_stvar", "s2_stvar"];
    const rows = filteredData.map(d => [d.second_index, d.s1_rms, d.s2_rms, d.s1_p2p, d.s2_p2p, d.s1_stvar, d.s2_stvar].join(','));
    const blob = new Blob([[headers.join(','), ...rows].join('\n')], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `aquaguard_analytics_${Date.now()}.csv`;
    a.click();
  };

  return (
    <div className="space-y-6 animate-fadeIn">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-extrabold text-slate-100 font-outfit tracking-tight flex items-center gap-2.5">
            <AnalyticsIcon className="w-7 h-7 text-cyan-400" />
            Live Sensor Analytics & DSP Feature Charts
          </h1>
          <p className="text-xs text-slate-400 mt-1">
            Detailed time-series graphs for RMS, Peak-to-Peak amplitude, Short-Term Variability, and threshold margins
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {/* Time Window Selectors */}
          <div className="inline-flex rounded-lg bg-navy-900 p-1 border border-cyan-500/20 text-xs font-mono">
            <button
              onClick={() => setTimeWindow('1m')}
              className={`px-3 py-1.5 rounded-md transition ${timeWindow === '1m' ? 'bg-cyan-500/20 text-cyan-300 font-bold border border-cyan-500/30' : 'text-slate-400'}`}
            >
              1 Min
            </button>
            <button
              onClick={() => setTimeWindow('5m')}
              className={`px-3 py-1.5 rounded-md transition ${timeWindow === '5m' ? 'bg-cyan-500/20 text-cyan-300 font-bold border border-cyan-500/30' : 'text-slate-400'}`}
            >
              5 Min
            </button>
            <button
              onClick={() => setTimeWindow('15m')}
              className={`px-3 py-1.5 rounded-md transition ${timeWindow === '15m' ? 'bg-cyan-500/20 text-cyan-300 font-bold border border-cyan-500/30' : 'text-slate-400'}`}
            >
              15 Min
            </button>
            <button
              onClick={() => setTimeWindow('all')}
              className={`px-3 py-1.5 rounded-md transition ${timeWindow === 'all' ? 'bg-cyan-500/20 text-cyan-300 font-bold border border-cyan-500/30' : 'text-slate-400'}`}
            >
              All History
            </button>
          </div>

          <button
            onClick={() => setPaused(!isPaused)}
            className="px-3 py-1.5 rounded-lg text-xs font-semibold bg-navy-950 text-slate-300 border border-cyan-500/20 hover:border-cyan-500/40 flex items-center gap-1.5"
          >
            {isPaused ? <Play className="w-3.5 h-3.5 text-amber-400" /> : <Pause className="w-3.5 h-3.5" />}
            {isPaused ? 'Resume' : 'Pause'}
          </button>

          <button
            onClick={exportCsv}
            className="px-3 py-1.5 rounded-lg text-xs font-semibold bg-cyan-500/20 text-cyan-300 border border-cyan-500/40 flex items-center gap-1.5"
          >
            <Download className="w-3.5 h-3.5" />
            Export CSV
          </button>
        </div>
      </div>

      {/* Sensor 1 RMS Chart */}
      <div className="glass-card p-5 space-y-3">
        <h3 className="font-bold text-sm text-cyan-300 font-outfit">
          Sensor 1 RMS Vibration Amplitude (0.0m) vs Threshold
        </h3>
        <div className="h-64 w-full">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={filteredData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
              <XAxis dataKey="second_index" stroke="#64748b" tick={{ fontSize: 10 }} />
              <YAxis stroke="#64748b" tick={{ fontSize: 10 }} />
              <Tooltip contentStyle={{ backgroundColor: '#090d16', borderColor: 'rgba(56, 189, 248, 0.3)', fontSize: '11px' }} />
              <Line type="monotone" dataKey="s1_rms" name="S1 RMS" stroke="#38bdf8" strokeWidth={2} dot={false} isAnimationActive={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Sensor 2 RMS Chart */}
      <div className="glass-card p-5 space-y-3">
        <h3 className="font-bold text-sm text-orange-300 font-outfit">
          Sensor 2 RMS Vibration Amplitude (2.0m) vs Threshold
        </h3>
        <div className="h-64 w-full">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={filteredData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
              <XAxis dataKey="second_index" stroke="#64748b" tick={{ fontSize: 10 }} />
              <YAxis stroke="#64748b" tick={{ fontSize: 10 }} />
              <Tooltip contentStyle={{ backgroundColor: '#090d16', borderColor: 'rgba(56, 189, 248, 0.3)', fontSize: '11px' }} />
              <Line type="monotone" dataKey="s2_rms" name="S2 RMS" stroke="#f97316" strokeWidth={2} dot={false} isAnimationActive={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  );
};
