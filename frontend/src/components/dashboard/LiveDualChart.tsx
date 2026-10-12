import React, { useState } from 'react';
import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  Legend,
  ReferenceLine,
  CartesianGrid
} from 'recharts';
import { TelemetryRecord, BaselineProfile } from '../../types';
import { Activity, Pause, Play, Download, Droplet } from 'lucide-react';
import { useTelemetry } from '../../context/TelemetryContext';

interface LiveDualChartProps {
  data: TelemetryRecord[];
  baseline: BaselineProfile;
  isPaused: boolean;
  onTogglePause: () => void;
}

export const LiveDualChart: React.FC<LiveDualChartProps> = React.memo(({
  data,
  baseline,
  isPaused,
  onTogglePause
}) => {
  const { flowHistory } = useTelemetry();
  const [chartMode, setChartMode] = useState<'vibration' | 'flow'>('vibration');

  // Format vibration data (last 60 records)
  const formattedVibData = data.slice(-60).map((d) => {
    const timeStr = d.pc_timestamp ? new Date(d.pc_timestamp).toLocaleTimeString() : `${d.second_index}s`;
    return {
      ...d,
      timeStr,
      s1_thresh: baseline.s1_thresh,
      s2_thresh: baseline.s2_thresh
    };
  });

  // Format flow data (last 60 records)
  const formattedFlowData = flowHistory.slice(-60);

  const exportCsv = () => {
    if (chartMode === 'vibration') {
      if (!data.length) return;
      const headers = ["second_index", "s1_rms_10bit_counts", "s2_rms_10bit_counts", "s1_p2p", "s2_p2p", "s1_abnormal", "s2_abnormal"];
      const rows = data.map(d => [d.second_index, d.s1_rms, d.s2_rms, d.s1_p2p, d.s2_p2p, d.s1_abnormal, d.s2_abnormal].join(','));
      const blob = new Blob([[headers.join(','), ...rows].join('\n')], { type: 'text/csv' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `aquaguard_vibration_10bit_adc_${Date.now()}.csv`;
      a.click();
    } else {
      if (!flowHistory.length) return;
      const headers = ["second_index", "flow_in_lpm", "flow_out_lpm", "flow_diff_lpm"];
      const rows = flowHistory.map(f => [f.second_index, f.flow_in_lpm, f.flow_out_lpm, f.flow_diff_lpm].join(','));
      const blob = new Blob([[headers.join(','), ...rows].join('\n')], { type: 'text/csv' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `aquaguard_flow_telemetry_${Date.now()}.csv`;
      a.click();
    }
  };

  return (
    <div className="glass-card p-5 relative overflow-hidden">
      <div className="flex flex-wrap items-center justify-between gap-4 mb-4 pb-3 border-b border-cyan-500/15">
        <div>
          <h3 className="font-semibold text-lg text-slate-100 flex items-center gap-2 font-outfit">
            {chartMode === 'vibration' ? (
              <>
                <Activity className="w-5 h-5 text-cyan-400" />
                Live Dual-Sensor Vibration Telemetry (10-bit ADC Counts)
              </>
            ) : (
              <>
                <Droplet className="w-5 h-5 text-cyan-400" />
                Live Dual YF-S201 Flow Sensor Telemetry (L/min)
              </>
            )}
          </h3>
          <p className="text-xs text-slate-400">
            {chartMode === 'vibration'
              ? 'Real-time vibration intensity (0–1023 ADC counts) for Arduino Uno A0 (0.0m) & A1 (2.0m)'
              : 'Dual flow verification: Inlet (YF-S201) vs. Outlet (YF-S201) with 0.50 L/min min floor & 0.10 L/min imbalance threshold'}
          </p>
        </div>

        <div className="flex items-center gap-2">
          {/* Mode Switcher */}
          <div className="flex bg-navy-950 p-0.5 rounded-lg border border-cyan-500/20 text-xs">
            <button
              onClick={() => setChartMode('vibration')}
              className={`px-3 py-1 rounded-md font-medium transition-all ${
                chartMode === 'vibration'
                  ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-500/40 shadow-glow-cyan'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              Vibration (RMS)
            </button>
            <button
              onClick={() => setChartMode('flow')}
              className={`px-3 py-1 rounded-md font-medium transition-all ${
                chartMode === 'flow'
                  ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-500/40 shadow-glow-cyan'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              Flow Rates (L/min)
            </button>
          </div>

          <button
            onClick={onTogglePause}
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold flex items-center gap-1.5 border transition-all ${
              isPaused
                ? 'bg-amber-500/20 text-amber-300 border-amber-500/40 shadow-glow-amber'
                : 'bg-navy-950 text-slate-300 border-cyan-500/20 hover:border-cyan-500/40'
            }`}
          >
            {isPaused ? <Play className="w-3.5 h-3.5" /> : <Pause className="w-3.5 h-3.5" />}
            {isPaused ? 'Resume Stream' : 'Pause'}
          </button>

          <button
            onClick={exportCsv}
            className="px-3 py-1.5 rounded-lg text-xs font-semibold bg-navy-950 text-cyan-400 hover:text-cyan-300 border border-cyan-500/20 hover:border-cyan-500/40 transition-all flex items-center gap-1.5"
          >
            <Download className="w-3.5 h-3.5" />
            Export CSV
          </button>
        </div>
      </div>

      <div className="h-72 w-full">
        {chartMode === 'vibration' ? (
          formattedVibData.length === 0 ? (
            <div className="h-full flex items-center justify-center text-slate-500 text-sm italic">
              Waiting for live vibration telemetry...
            </div>
          ) : (
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={formattedVibData} margin={{ top: 10, right: 20, left: -10, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" opacity={0.6} />
                <XAxis
                  dataKey="second_index"
                  stroke="#64748b"
                  tick={{ fontSize: 11 }}
                  tickFormatter={(val) => `${val}s`}
                />
                <YAxis
                  stroke="#64748b"
                  tick={{ fontSize: 11 }}
                  domain={[0, 'auto']}
                  unit=" cnt"
                />
                <Tooltip
                  contentStyle={{
                    backgroundColor: '#090d16',
                    borderColor: 'rgba(56, 189, 248, 0.3)',
                    borderRadius: '0.75rem',
                    fontSize: '12px',
                    boxShadow: '0 10px 25px -5px rgba(0, 0, 0, 0.5)'
                  }}
                  formatter={(value: any, name: any) => [`${Number(value).toFixed(1)} counts`, String(name || '')] as [string, string]}
                />
                <Legend verticalAlign="top" height={36} wrapperStyle={{ fontSize: '12px' }} />

                {/* Threshold Lines */}
                <ReferenceLine
                  y={baseline.s1_thresh}
                  stroke="#ef4444"
                  strokeDasharray="4 4"
                  label={{ value: `S1 Thresh (${baseline.s1_thresh.toFixed(1)})`, fill: '#ef4444', fontSize: 10, position: 'insideTopRight' }}
                />
                <ReferenceLine
                  y={baseline.s2_thresh}
                  stroke="#f59e0b"
                  strokeDasharray="4 4"
                  label={{ value: `S2 Thresh (${baseline.s2_thresh.toFixed(1)})`, fill: '#f59e0b', fontSize: 10, position: 'insideBottomRight' }}
                />

                {/* Sensor 1 Line */}
                <Line
                  type="monotone"
                  dataKey="s1_rms"
                  name="Sensor 1 RMS (A0, 0.0m)"
                  stroke="#38bdf8"
                  strokeWidth={2}
                  dot={false}
                  activeDot={{ r: 5, fill: '#38bdf8' }}
                  isAnimationActive={false}
                />

                {/* Sensor 2 Line */}
                <Line
                  type="monotone"
                  dataKey="s2_rms"
                  name="Sensor 2 RMS (A1, 2.0m)"
                  stroke="#f97316"
                  strokeWidth={2}
                  dot={false}
                  activeDot={{ r: 5, fill: '#f97316' }}
                  isAnimationActive={false}
                />
              </LineChart>
            </ResponsiveContainer>
          )
        ) : (
          formattedFlowData.length === 0 ? (
            <div className="h-full flex items-center justify-center text-slate-500 text-sm italic">
              Waiting for live flow telemetry...
            </div>
          ) : (
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={formattedFlowData} margin={{ top: 10, right: 20, left: -10, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" opacity={0.6} />
                <XAxis
                  dataKey="second_index"
                  stroke="#64748b"
                  tick={{ fontSize: 11 }}
                  tickFormatter={(val) => `#${val}`}
                />
                <YAxis
                  stroke="#64748b"
                  tick={{ fontSize: 11 }}
                  domain={[0, 'auto']}
                  unit=" L/m"
                />
                <Tooltip
                  contentStyle={{
                    backgroundColor: '#090d16',
                    borderColor: 'rgba(56, 189, 248, 0.3)',
                    borderRadius: '0.75rem',
                    fontSize: '12px',
                    boxShadow: '0 10px 25px -5px rgba(0, 0, 0, 0.5)'
                  }}
                  formatter={(value: any, name: any) => [`${Number(value).toFixed(2)} L/min`, String(name || '')] as [string, string]}
                />
                <Legend verticalAlign="top" height={36} wrapperStyle={{ fontSize: '12px' }} />

                {/* Flow Evaluation Reference Lines */}
                <ReferenceLine
                  y={0.50}
                  stroke="#94a3b8"
                  strokeDasharray="4 4"
                  label={{ value: "Min Flow Floor (0.50 L/min)", fill: '#94a3b8', fontSize: 10, position: 'insideTopLeft' }}
                />
                <ReferenceLine
                  y={0.10}
                  stroke="#ef4444"
                  strokeDasharray="3 3"
                  label={{ value: "Leak Diff Thresh (0.10 L/min)", fill: '#ef4444', fontSize: 10, position: 'insideBottomRight' }}
                />

                {/* Inlet Flow Line */}
                <Line
                  type="monotone"
                  dataKey="flow_in_lpm"
                  name="Inlet Flow (L/min)"
                  stroke="#38bdf8"
                  strokeWidth={2.5}
                  dot={false}
                  activeDot={{ r: 5, fill: '#38bdf8' }}
                  isAnimationActive={false}
                />

                {/* Outlet Flow Line */}
                <Line
                  type="monotone"
                  dataKey="flow_out_lpm"
                  name="Outlet Flow (L/min)"
                  stroke="#f97316"
                  strokeWidth={2.5}
                  dot={false}
                  activeDot={{ r: 5, fill: '#f97316' }}
                  isAnimationActive={false}
                />

                {/* Flow Difference Line */}
                <Line
                  type="monotone"
                  dataKey="flow_diff_lpm"
                  name="Flow Imbalance (|In - Out|)"
                  stroke="#ef4444"
                  strokeWidth={1.5}
                  strokeDasharray="3 3"
                  dot={false}
                  activeDot={{ r: 4, fill: '#ef4444' }}
                  isAnimationActive={false}
                />
              </LineChart>
            </ResponsiveContainer>
          )
        )}
      </div>
    </div>
  );
});
