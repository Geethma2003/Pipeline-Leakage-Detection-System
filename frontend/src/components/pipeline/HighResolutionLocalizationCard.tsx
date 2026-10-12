import React, { useMemo } from 'react';
import { useTelemetry } from '../../context/TelemetryContext';
import {
  Activity,
  Waves,
  Zap,
  Gauge,
  MapPin,
  AlertTriangle,
  CheckCircle2,
  HelpCircle,
  Clock,
  Compass,
  ArrowRightLeft,
  Droplets,
  Lock,
  Unlock,
  ShieldCheck,
  ShieldAlert
} from 'lucide-react';

export const HighResolutionLocalizationCard: React.FC = () => {
  const { localization, demoMode, isConnected, flow, wireless, latestTelemetry } = useTelemetry();

  const pipeLength = localization?.pipe_length_m ?? 2.0;
  const s1Pos = localization?.s1_pos_m ?? 0.0;
  const s2Pos = localization?.s2_pos_m ?? 2.0;
  const deltaTUs = localization?.delta_t_us ?? 0.0;
  const sampleRateHz = localization?.sample_rate_hz ?? 0;
  const velocityMps = localization?.propagation_velocity_mps ?? 1250.0;
  const locValid = localization?.loc_valid ?? false;
  const d1 = localization?.leak_distance_s1_m;
  const d2 = localization?.leak_distance_s2_m;
  const confidence = localization?.confidence_pct ?? 0.0;
  const uncertaintyM = localization?.uncertainty_m ?? 0.15;
  const correlationPeak = localization?.correlation_peak ?? 0.0;
  const psr = localization?.psr ?? 0.0;
  const statusText = localization?.status ?? 'LOCATION UNAVAILABLE — INSUFFICIENT SIGNAL QUALITY';

  // Dual YF-S201 Flow Sensor Verification Properties
  const flowConfirmed = flow?.leak_confirmed ?? false;
  const flowProgress = flow?.leak_progress ?? 0;
  const flowIn = flow?.flow_in_lpm ?? 0.0;
  const flowOut = flow?.flow_out_lpm ?? 0.0;
  const flowDiff = flow?.flow_diff_lpm ?? 0.0;
  const flowInPulses = flow?.in_pulses ?? 0;
  const flowOutPulses = flow?.out_pulses ?? 0;
  const flowStatus = flow?.status ?? 'NO_FLOW';

  // CRITICAL RULE: Flow sensors are the ONLY authority for confirming leakage.
  // Vibration sensors are ONLY responsible for estimating location.
  // Official leak position is NEVER revealed until flow confirms the leak AND a valid vibration estimate exists!
  const isLocationRevealed = flowConfirmed && locValid && d1 !== null && d1 !== undefined;

  // Waveform data (only rendered when real waveform points are present)
  const s1Wave = localization?.s1_waveform ?? [];
  const s2Wave = localization?.s2_waveform ?? [];

  // Calculate SVG X coordinates on 2.0m scale (from x=80 to x=720, total width 640px = 320px/meter)
  const startX = 80;
  const endX = 720;
  const totalPx = endX - startX;

  const leakX = useMemo(() => {
    if (isLocationRevealed && d1 !== null && d1 !== undefined) {
      const clamped = Math.max(0.0, Math.min(pipeLength, d1));
      return startX + (clamped / pipeLength) * totalPx;
    }
    return null;
  }, [isLocationRevealed, d1, pipeLength, startX, totalPx]);

  const uncertaintyPx = useMemo(() => {
    return (uncertaintyM / pipeLength) * totalPx;
  }, [uncertaintyM, pipeLength, totalPx]);

  // Generate SVG path for waveforms
  const wavePointsToSvgPath = (points: number[], height: number, centerY: number): string => {
    if (!points || points.length === 0) return '';
    const maxVal = Math.max(...points.map((p) => Math.abs(p)), 20);
    const stepX = 700 / (points.length - 1);

    return points
      .map((val, idx) => {
        const x = 50 + idx * stepX;
        const normalized = (val / maxVal) * (height / 2);
        const y = centerY - normalized;
        return `${idx === 0 ? 'M' : 'L'} ${x.toFixed(1)} ${y.toFixed(1)}`;
      })
      .join(' ');
  };

  const s1Path = useMemo(() => wavePointsToSvgPath(s1Wave, 70, 50), [s1Wave]);
  const s2Path = useMemo(() => wavePointsToSvgPath(s2Wave, 70, 110), [s2Wave]);

  return (
    <div className="glass-card p-6 relative overflow-hidden space-y-6 border border-cyan-500/20 shadow-2xl">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-4 pb-4 border-b border-cyan-500/15">
        <div>
          <div className="flex items-center gap-2.5">
            <div className="p-2 rounded-xl bg-cyan-500/10 border border-cyan-500/30 text-cyan-400">
              <Zap className="w-6 h-6 animate-pulse" />
            </div>
            <div>
              <h2 className="text-xl font-extrabold text-slate-100 font-outfit tracking-tight flex items-center gap-2">
                Flow-Verified Leak Localization Architecture
              </h2>
              <p className="text-xs text-slate-400 mt-0.5">
                Dual YF-S201 Flow Confirmation Authority & Arduino Uno Dual-Piezoelectric TDOA Positioning
              </p>
            </div>
          </div>
        </div>

        {/* Dual Authority Status Badges */}
        <div className="flex flex-wrap items-center gap-2">
          {/* Flow Sensor Authority Badge */}
          <div
            className={`px-3 py-1.5 rounded-xl border text-xs font-mono font-bold flex items-center gap-2 ${
              flowConfirmed
                ? 'bg-red-500/15 border-red-500/40 text-red-300 shadow-glow-red animate-pulse'
                : 'bg-emerald-500/15 border-emerald-500/40 text-emerald-300'
            }`}
          >
            <Droplets className="w-4 h-4 text-cyan-400" />
            <span>
              {flowConfirmed
                ? 'FLOW: LEAK CONFIRMED (ALARM)'
                : 'FLOW: NORMAL BALANCED'}
            </span>
          </div>

          {/* Localization Status Badge */}
          <div
            className={`px-3 py-1.5 rounded-xl border text-xs font-mono font-bold flex items-center gap-2 ${
              isLocationRevealed
                ? 'bg-emerald-500/15 border-emerald-500/40 text-emerald-300 shadow-glow-emerald'
                : 'bg-slate-800/80 border-slate-700 text-slate-400'
            }`}
          >
            {isLocationRevealed ? (
              <Unlock className="w-4 h-4 text-emerald-400" />
            ) : (
              <Lock className="w-4 h-4 text-slate-400" />
            )}
            <span>{isLocationRevealed ? `LOCATION REVEALED (~${d1?.toFixed(2)}m)` : 'LOCATION CONCEALED'}</span>
          </div>
        </div>
      </div>

      {/* DUAL YF-S201 FLOW SENSOR VERIFICATION PANEL */}
      <div className="p-4.5 rounded-2xl bg-navy-950/90 border border-cyan-500/25 space-y-4 shadow-xl">
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-cyan-500/15 pb-3">
          <div className="flex items-center gap-2 text-xs font-bold text-slate-200">
            <Droplets className="w-4 h-4 text-cyan-400" />
            <span>Dual YF-S201 Flow Meters (5-Second Evaluation Windows)</span>
            <span className="text-[10px] text-cyan-400/90 font-mono font-normal">
              [Nominal K = 450 P/L | Min Inlet: 0.50 L/min]
            </span>
          </div>
          <div className="text-[11px] font-mono text-slate-400 flex items-center gap-2">
            <span>Status:</span>
            <span className={`px-2 py-0.5 rounded font-bold ${
              flowConfirmed ? 'bg-red-500/20 text-red-300' : 'bg-slate-800 text-slate-300'
            }`}>
              {flowStatus}
            </span>
          </div>
        </div>

        {/* Flow Metric Cards Grid */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {/* Inlet Flow (D2) */}
          <div className="p-3 rounded-xl bg-navy-900/80 border border-cyan-500/20 space-y-1">
            <div className="flex items-center justify-between text-[11px] text-slate-400">
              <span>Inlet Flow (Qin)</span>
              <span className="text-[10px] font-mono text-cyan-400">Inlet Flow — D2</span>
            </div>
            <div className="text-lg font-bold font-mono text-cyan-300">
              {flowIn.toFixed(3)} <span className="text-xs text-slate-400">L/min</span>
            </div>
            <div className="text-[10px] text-slate-500 font-mono">Arduino Uno Transmitter</div>
          </div>

          {/* Outlet Flow (D3) */}
          <div className="p-3 rounded-xl bg-navy-900/80 border border-cyan-500/20 space-y-1">
            <div className="flex items-center justify-between text-[11px] text-slate-400">
              <span>Outlet Flow (Qout)</span>
              <span className="text-[10px] font-mono text-orange-400">Outlet Flow — D3</span>
            </div>
            <div className="text-lg font-bold font-mono text-orange-300">
              {flowOut.toFixed(3)} <span className="text-xs text-slate-400">L/min</span>
            </div>
            <div className="text-[10px] text-slate-500 font-mono">Arduino Uno Transmitter</div>
          </div>

          {/* Differential Flow */}
          <div className={`p-3 rounded-xl border space-y-1 ${
            flowDiff >= 0.10
              ? 'bg-red-950/40 border-red-500/40 text-red-300'
              : 'bg-navy-900/80 border-cyan-500/20 text-slate-300'
          }`}>
            <div className="flex items-center justify-between text-[11px] text-slate-400">
              <span>Flow Difference (ΔQ)</span>
              <span className="text-[10px] font-mono text-slate-400">Thresh: 0.10</span>
            </div>
            <div className="text-lg font-bold font-mono">
              {flowDiff > 0 ? `+${flowDiff.toFixed(3)}` : flowDiff.toFixed(3)}{' '}
              <span className="text-xs text-slate-400">L/min</span>
            </div>
            <div className="text-[10px] font-mono text-slate-500">
              {flowDiff >= 0.10 ? '⚠️ Imbalance Exceeded' : '✓ Normal Balance'}
            </div>
          </div>

          {/* Transmitted Flow Alarm Verification Flag */}
          <div className="p-3 rounded-xl bg-navy-900/80 border border-cyan-500/20 space-y-2">
            <div className="flex items-center justify-between text-[11px] text-slate-400">
              <span>Leak Alarm Flag</span>
              <span className={`text-[10px] font-mono font-bold ${flowConfirmed ? 'text-red-400' : 'text-emerald-400'}`}>
                {flowConfirmed ? '0x08 (LEAK)' : '0x00 (CLEAR)'}
              </span>
            </div>
            <div className={`py-1 px-2 rounded-lg text-center font-mono font-bold text-xs ${
              flowConfirmed
                ? 'bg-red-500/20 text-red-300 border border-red-500/40 animate-pulse'
                : 'bg-emerald-500/15 text-emerald-300 border border-emerald-500/30'
            }`}>
              {flowConfirmed ? 'ALARM: CONFIRMED LEAK' : 'ALARM: NORMAL BALANCED'}
            </div>
            <div className="text-[10px] text-slate-500 font-mono text-center">
              Transmitted nRF24 Alarm Flag
            </div>
          </div>
        </div>

        {/* CRITICAL ARCHITECTURAL RULE CALLOUT */}
        <div className={`p-3.5 rounded-xl border text-xs flex items-start gap-3 ${
          isLocationRevealed
            ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-200'
            : flowConfirmed
            ? 'bg-amber-500/10 border-amber-500/30 text-amber-200'
            : 'bg-cyan-950/40 border-cyan-500/20 text-slate-300'
        }`}>
          {isLocationRevealed ? (
            <ShieldCheck className="w-5 h-5 text-emerald-400 shrink-0 mt-0.5" />
          ) : flowConfirmed ? (
            <AlertTriangle className="w-5 h-5 text-amber-400 shrink-0 mt-0.5" />
          ) : (
            <Lock className="w-5 h-5 text-cyan-400 shrink-0 mt-0.5" />
          )}
          <div className="space-y-1 text-[11px] leading-relaxed">
            <span className="font-bold tracking-wide uppercase font-mono block">
              {isLocationRevealed
                ? 'OFFICIAL CONFIRMED LEAK: ACOUSTIC LOCALIZATION REVEALED'
                : flowConfirmed
                ? 'LEAK CONFIRMED BY FLOW METERS — ACOUSTIC LOCATION UNAVAILABLE'
                : 'CRITICAL RULE: LEAK LOCATION CONCEALED UNTIL FLOW CONFIRMATION'}
            </span>
            <p className="text-slate-300">
              {isLocationRevealed
                ? `Flow sensors have confirmed leakage (>0.10 L/min imbalance). The acoustic localization result (~${d1?.toFixed(2)}m from Sensor 1) is an uncalibrated estimate (nominal 1250 m/s; physical test pending at 0.5m, 1.0m, 1.5m).`
                : flowConfirmed
                ? 'Flow sensors have confirmed leakage via verified transmitted alarm flag, but valid acoustic cross-correlation estimate is not yet available or out-of-range. System honestly reports location unavailable instead of inventing false coordinates.'
                : 'ONLY dual YF-S201 flow sensors determine whether a leak is confirmed. Dual piezoelectric sensors (Piezo 1 — A0 & Piezo 2 — A1) ONLY determine location. The website strictly conceals official leak coordinates until flow imbalance is verified.'}
            </p>
          </div>
        </div>
      </div>

      {/* Key Metric Grid */}
      <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-3">
        {/* Metric 1: Delta T */}
        <div className="p-3.5 rounded-xl bg-navy-950/80 border border-cyan-500/20 space-y-1">
          <div className="flex items-center justify-between text-slate-400 text-[11px]">
            <span>Time Shift (Δt)</span>
            <Clock className="w-3.5 h-3.5 text-cyan-400" />
          </div>
          <div className="text-base font-bold font-mono text-cyan-300">
            {deltaTUs > 0 ? `+${deltaTUs.toFixed(1)}` : deltaTUs.toFixed(1)} <span className="text-xs text-slate-400">μs</span>
          </div>
          <div className="text-[10px] text-slate-500 font-mono">t₂ - t₁ arrival skew</div>
        </div>

        {/* Metric 2: Sampling Rate */}
        <div className="p-3.5 rounded-xl bg-navy-950/80 border border-cyan-500/20 space-y-1">
          <div className="flex items-center justify-between text-slate-400 text-[11px]">
            <span>Sample Rate (fs)</span>
            <Gauge className="w-3.5 h-3.5 text-indigo-400" />
          </div>
          <div className="text-base font-bold font-mono text-indigo-300">
            {sampleRateHz > 0 ? `${sampleRateHz.toLocaleString()} Hz` : '~19.2 kHz'}
          </div>
          <div className="text-[10px] text-amber-400/90 font-mono">
            THEORETICAL (Prescaler 32)
          </div>
        </div>

        {/* Metric 3: Wave Velocity */}
        <div className="p-3.5 rounded-xl bg-navy-950/80 border border-cyan-500/20 space-y-1">
          <div className="flex items-center justify-between text-slate-400 text-[11px]">
            <span>Wave Speed (v)</span>
            <Waves className="w-3.5 h-3.5 text-sky-400" />
          </div>
          <div className="text-base font-bold font-mono text-sky-300">
            {velocityMps.toFixed(0)} <span className="text-xs text-slate-400">m/s</span>
          </div>
          <div className="text-[10px] text-amber-400/90 font-mono font-semibold">NOMINAL / UNCALIBRATED</div>
        </div>

        {/* Metric 4: Distance from S1 */}
        <div className="p-3.5 rounded-xl bg-navy-950/80 border border-cyan-500/20 space-y-1">
          <div className="flex items-center justify-between text-slate-400 text-[11px]">
            <span>Dist from S1</span>
            <MapPin className="w-3.5 h-3.5 text-emerald-400" />
          </div>
          <div className="text-base font-bold font-mono text-emerald-300">
            {locValid && d1 !== null && d1 !== undefined ? `${d1.toFixed(2)} m` : '—'}
          </div>
          <div className="text-[10px] text-slate-500 font-mono">From Sensor 1 (0.0m)</div>
        </div>

        {/* Metric 5: Distance from S2 */}
        <div className="p-3.5 rounded-xl bg-navy-950/80 border border-cyan-500/20 space-y-1">
          <div className="flex items-center justify-between text-slate-400 text-[11px]">
            <span>Dist from S2</span>
            <MapPin className="w-3.5 h-3.5 text-orange-400" />
          </div>
          <div className="text-base font-bold font-mono text-orange-300">
            {locValid && d2 !== null && d2 !== undefined ? `${d2.toFixed(2)} m` : '—'}
          </div>
          <div className="text-[10px] text-slate-500 font-mono">From Sensor 2 (2.0m)</div>
        </div>

        {/* Metric 6: Confidence & Uncertainty */}
        <div className="p-3.5 rounded-xl bg-navy-950/80 border border-cyan-500/20 space-y-1">
          <div className="flex items-center justify-between text-slate-400 text-[11px]">
            <span>Calibration Status</span>
            <CheckCircle2 className="w-3.5 h-3.5 text-teal-400" />
          </div>
          <div className="text-sm font-bold font-mono text-teal-300">
            {locValid ? 'UNCALIBRATED' : '—'}
          </div>
          <div className="text-[10px] text-amber-400/90 font-mono">
            Requires known test points
          </div>
        </div>

        {/* Metric 7: Correlation Quality */}
        <div className="p-3.5 rounded-xl bg-navy-950/80 border border-cyan-500/20 space-y-1">
          <div className="flex items-center justify-between text-slate-400 text-[11px]">
            <span>Corr Peak (R)</span>
            <Activity className="w-3.5 h-3.5 text-purple-400" />
          </div>
          <div className="text-base font-bold font-mono text-purple-300">
            {locValid && correlationPeak > 0 ? correlationPeak.toFixed(3) : '—'}
          </div>
          <div className="text-[10px] text-slate-500 font-mono">
            {locValid && psr > 0 ? `PSR: ${psr.toFixed(1)}x` : 'Min thresh: 0.65'}
          </div>
        </div>
      </div>

      {/* Physical 2.0-Meter Interactive Pipeline Schematic */}
      <div className="p-5 rounded-2xl bg-navy-950/90 border border-cyan-500/20 space-y-3">
        <div className="flex items-center justify-between text-xs text-slate-400">
          <span className="font-semibold text-slate-200 flex items-center gap-2">
            <Compass className="w-4 h-4 text-cyan-400" />
            2.0-Meter Physical Pipe Coordinate Space
          </span>
          <span className="font-mono text-[11px] text-slate-500">
            Formula: d₁ = (L - v · Δt) / 2
          </span>
        </div>

        <div className="relative w-full overflow-x-auto">
          <svg viewBox="0 0 800 130" className="w-full min-w-[650px] h-auto overflow-visible">
            {/* Pipe Cylinder */}
            <rect x="70" y="45" width="660" height="30" rx="8" fill="#1e293b" stroke="#334155" strokeWidth="2" />
            {/* Water Core */}
            <rect
              x="72"
              y="50"
              width="656"
              height="20"
              rx="4"
              fill="url(#waterTdoaGrad)"
              className="opacity-75"
            />

            <defs>
              <linearGradient id="waterTdoaGrad" x1="0%" y1="0%" x2="100%" y2="0%">
                <stop offset="0%" stopColor="#0284c7" />
                <stop offset="50%" stopColor="#06b6d4" />
                <stop offset="100%" stopColor="#0369a1" />
              </linearGradient>
            </defs>

            {/* Scale Tick Marks */}
            {[0, 0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0].map((meter) => {
              const x = startX + (meter / pipeLength) * totalPx;
              const isMajor = meter === 0 || meter === 1.0 || meter === 2.0;
              return (
                <g key={meter}>
                  <line
                    x1={x}
                    y1={isMajor ? 35 : 40}
                    x2={x}
                    y2={isMajor ? 85 : 80}
                    stroke={isMajor ? '#94a3b8' : '#475569'}
                    strokeWidth={isMajor ? 1.5 : 1}
                    strokeDasharray={isMajor ? 'none' : '2 2'}
                  />
                  <text
                    x={x}
                    y="105"
                    fill={isMajor ? '#cbd5e1' : '#64748b'}
                    fontSize="10"
                    fontFamily="monospace"
                    textAnchor="middle"
                  >
                    {meter.toFixed(2)}m
                  </text>
                </g>
              );
            })}

            {/* SENSOR 1 NODE (0.0 m) */}
            <g transform={`translate(${startX}, 45)`}>
              <rect x="-14" y="-28" width="28" height="24" rx="4" fill="#0f172a" stroke="#38bdf8" strokeWidth="2" />
              <circle cx="0" cy="-16" r="6" fill="#38bdf8" className="animate-pulse" />
              <text x="0" y="-34" fill="#38bdf8" fontSize="11" fontWeight="bold" textAnchor="middle">
                S1 (0.00m)
              </text>
              <text x="0" y="75" fill="#38bdf8" fontSize="10" fontFamily="monospace" textAnchor="middle">
                Piezo 1 — A0
              </text>
            </g>

            {/* SENSOR 2 NODE (2.0 m) */}
            <g transform={`translate(${endX}, 45)`}>
              <rect x="-14" y="-28" width="28" height="24" rx="4" fill="#0f172a" stroke="#f97316" strokeWidth="2" />
              <circle cx="0" cy="-16" r="6" fill="#f97316" className="animate-pulse" />
              <text x="0" y="-34" fill="#f97316" fontSize="11" fontWeight="bold" textAnchor="middle">
                S2 (2.00m)
              </text>
              <text x="0" y="75" fill="#f97316" fontSize="10" fontFamily="monospace" textAnchor="middle">
                Piezo 2 — A1
              </text>
            </g>

            {/* LEAK POSITION MARKER — NEVER DEFAULTS TO MIDPOINT (1.0m) */}
            {isLocationRevealed && leakX !== null ? (
              <g transform={`translate(${leakX}, 60)`}>
                {/* Uncertainty Range Band */}
                <rect
                  x={-uncertaintyPx}
                  y="-18"
                  width={uncertaintyPx * 2}
                  height="36"
                  rx="6"
                  fill="rgba(239, 68, 68, 0.25)"
                  stroke="#ef4444"
                  strokeWidth="1"
                  strokeDasharray="3 3"
                />
                <circle cx="0" cy="0" r="18" fill="rgba(239, 68, 68, 0.3)" className="animate-ping" />
                <circle cx="0" cy="0" r="9" fill="#ef4444" stroke="#ffffff" strokeWidth="2" />
                <line x1="0" y1="-26" x2="0" y2="-8" stroke="#ef4444" strokeWidth="2" />
                <text
                  x="0"
                  y="-30"
                  fill="#ef4444"
                  fontSize="12"
                  fontWeight="bold"
                  fontFamily="monospace"
                  textAnchor="middle"
                >
                  CONFIRMED LEAK: {(d1 ?? 0).toFixed(2)}m (±{(uncertaintyM * 100).toFixed(0)}cm)
                </text>
              </g>
            ) : !flowConfirmed ? (
              <g transform={`translate(${startX + totalPx / 2}, 60)`}>
                <rect
                  x="-195"
                  y="-22"
                  width="390"
                  height="30"
                  rx="6"
                  fill="#0f172a"
                  stroke="#64748b"
                  strokeWidth="1"
                  strokeDasharray="4 4"
                />
                <text
                  x="0"
                  y="-3"
                  fill="#94a3b8"
                  fontSize="11"
                  fontFamily="monospace"
                  textAnchor="middle"
                  fontWeight="bold"
                >
                  🔒 LOCATION CONCEALED — Normal Balanced Flow
                </text>
              </g>
            ) : (
              <g transform={`translate(${startX + totalPx / 2}, 60)`}>
                <rect
                  x="-210"
                  y="-22"
                  width="420"
                  height="30"
                  rx="6"
                  fill="#0f172a"
                  stroke="#f59e0b"
                  strokeWidth="1"
                  strokeDasharray="4 4"
                />
                <text
                  x="0"
                  y="-3"
                  fill="#f59e0b"
                  fontSize="11"
                  fontFamily="monospace"
                  textAnchor="middle"
                  fontWeight="bold"
                >
                  ⚠️ LEAK CONFIRMED BY FLOW — Acoustic Location Unavailable
                </text>
              </g>
            )}
          </svg>
        </div>
      </div>

      {/* Dual Synchronized Waveform Comparison Plot */}
      <div className="p-5 rounded-2xl bg-navy-950/90 border border-cyan-500/20 space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-2 text-xs">
          <span className="font-semibold text-slate-200 flex items-center gap-2">
            <Activity className="w-4 h-4 text-cyan-400" />
            Synchronized Waveform Capture & Arrival Skew
          </span>
          <div className="flex items-center gap-4 text-[11px] font-mono">
            <span className="flex items-center gap-1.5 text-cyan-400">
              <span className="w-2.5 h-1.5 bg-cyan-400 rounded-sm inline-block" />
              Piezo 1 — A0 (0.0m)
            </span>
            <span className="flex items-center gap-1.5 text-orange-400">
              <span className="w-2.5 h-1.5 bg-orange-400 rounded-sm inline-block" />
              Piezo 2 — A1 (2.0m)
            </span>
            <span className="text-slate-500">|</span>
            <span className="text-slate-400">Window: 5.0 ms (Arduino Uno Dual ADC)</span>
          </div>
        </div>

        <div className="relative w-full bg-navy-900/90 rounded-xl p-3 border border-slate-800">
          <svg viewBox="0 0 800 160" className="w-full h-auto min-h-[140px] overflow-visible">
            {/* Grid Lines */}
            {[20, 50, 80, 110, 140].map((y) => (
              <line key={y} x1="40" y1={y} x2="760" y2={y} stroke="#1e293b" strokeWidth="1" strokeDasharray="2 2" />
            ))}
            {[100, 200, 300, 400, 500, 600, 700].map((x) => (
              <line key={x} x1={x} y1="20" x2={x} y2="150" stroke="#1e293b" strokeWidth="1" strokeDasharray="2 2" />
            ))}

            {/* Center Zero Lines */}
            <line x1="40" y1="50" x2="760" y2="50" stroke="#334155" strokeWidth="1" />
            <line x1="40" y1="110" x2="760" y2="110" stroke="#334155" strokeWidth="1" />

            <text x="35" y="54" fill="#38bdf8" fontSize="10" fontFamily="monospace" textAnchor="end">
              A0
            </text>
            <text x="35" y="114" fill="#f97316" fontSize="10" fontFamily="monospace" textAnchor="end">
              A1
            </text>

            {/* Waveform Paths */}
            {s1Path && (
              <path
                d={s1Path}
                fill="none"
                stroke="#38bdf8"
                strokeWidth="2.5"
                strokeLinecap="round"
                strokeLinejoin="round"
                className="drop-shadow-[0_0_6px_rgba(56,189,248,0.5)]"
              />
            )}
            {s2Path && (
              <path
                d={s2Path}
                fill="none"
                stroke="#f97316"
                strokeWidth="2.5"
                strokeLinecap="round"
                strokeLinejoin="round"
                className="drop-shadow-[0_0_6px_rgba(249,115,22,0.5)]"
              />
            )}

            {/* Delay Indicator Bracket on Verified Localization */}
            {locValid && deltaTUs !== 0 && (
              <g transform="translate(350, 75)">
                <line x1="-30" y1="0" x2="30" y2="0" stroke="#ef4444" strokeWidth="1.5" strokeDasharray="3 2" />
                <text x="0" y="-6" fill="#ef4444" fontSize="10" fontFamily="monospace" textAnchor="middle">
                  Δt = {deltaTUs > 0 ? `+${deltaTUs.toFixed(1)}` : deltaTUs.toFixed(1)} μs
                </text>
              </g>
            )}
          </svg>
        </div>
      </div>

      {/* GPS vs. TDOA Distinction Banner */}
      <div className="p-4 rounded-xl bg-slate-900/80 border border-slate-800 text-slate-300 text-xs flex flex-col md:flex-row items-start md:items-center justify-between gap-3">
        <div className="flex items-start gap-2.5">
          <HelpCircle className="w-4 h-4 text-cyan-400 shrink-0 mt-0.5" />
          <div className="space-y-0.5 text-[11px]">
            <span className="font-bold text-slate-200">
              Measurement Architecture Distinction: GPS vs. TDOA
            </span>
            <p className="text-slate-400 leading-relaxed">
              <strong>GPS Telemetry</strong> specifies the macro geographic installation coordinates of the pipeline testbed
              in Sri Lanka. <strong>Arduino Uno TDOA</strong> computes the micro acoustic position
              along the 2.0-meter laboratory steel section using vibration time difference of arrival.
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2 shrink-0">
          <span className="px-2.5 py-1 rounded-lg bg-navy-950 border border-slate-700 text-[10px] font-mono text-slate-300">
            Steel L = 2.0m
          </span>
          <span className="px-2.5 py-1 rounded-lg bg-navy-950 border border-slate-700 text-[10px] font-mono text-slate-300">
            Arduino Uno TDOA
          </span>
        </div>
      </div>
    </div>
  );
};
