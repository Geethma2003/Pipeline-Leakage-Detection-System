import React from 'react';
import { useTelemetry } from '../context/TelemetryContext';
import { LiveDualChart } from '../components/dashboard/LiveDualChart';
import { SensorCard } from '../components/dashboard/SensorCard';
import { ArduinoWirelessFlowCard } from '../components/dashboard/ArduinoWirelessFlowCard';
import { ProgressIndicator } from '../components/dashboard/ProgressIndicator';
import { RecentEventsPanel } from '../components/dashboard/RecentEventsPanel';
import { LiveGpsMap } from '../components/pipeline/LiveGpsMap';
import { HighResolutionLocalizationCard } from '../components/pipeline/HighResolutionLocalizationCard';
import { Activity } from 'lucide-react';


export const DashboardView: React.FC = () => {
  const {
    isConnected,
    diagnostics,
    demoMode,
    latestTelemetry,
    baseline,
    currentWindowSec,
    latestDecision,
    telemetryHistory,
    isPaused,
    setPaused
  } = useTelemetry();

  // Calculate abnormal seconds in history for S1 & S2
  const s1AbnormalSec = telemetryHistory.slice(-60).filter(d => d.s1_abnormal === 1).length;
  const s2AbnormalSec = telemetryHistory.slice(-60).filter(d => d.s2_abnormal === 1).length;

  return (
    <div className="space-y-6 animate-fadeIn">
      {/* Page Header */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-extrabold text-slate-100 font-outfit tracking-tight flex items-center gap-2.5">
            <Activity className="w-7 h-7 text-cyan-400" />
            Overview Dashboard
          </h1>
          <p className="text-xs text-slate-400 mt-1">
            Real-time Arduino Uno nRF24L01+ wireless telemetry, dual YF-S201 flow verification, dual-sensor RMS vibration, and live GPS monitoring
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-3">
          {/* Data Freshness Indicator */}
          <div className={`px-3 py-1.5 rounded-xl border text-xs font-mono font-bold flex items-center gap-2 ${
            !isConnected
              ? 'bg-rose-500/15 border-rose-500/40 text-rose-300'
              : (diagnostics?.data_freshness === 'LIVE' || demoMode)
              ? 'bg-emerald-500/15 border-emerald-500/40 text-emerald-300 shadow-glow-emerald'
              : diagnostics?.data_freshness === 'DELAYED'
              ? 'bg-amber-500/15 border-amber-500/40 text-amber-300'
              : 'bg-rose-500/15 border-rose-500/40 text-rose-300 animate-pulse'
          }`}>
            <span className={`w-2.5 h-2.5 rounded-full ${
              (diagnostics?.data_freshness === 'LIVE' || demoMode) ? 'bg-emerald-400 animate-ping' : 'bg-amber-400'
            }`}></span>
            <span>
              DATA FRESHNESS: {demoMode ? 'LIVE (DEMO)' : (diagnostics?.data_freshness || 'LIVE')}
            </span>
            {!demoMode && diagnostics?.last_record_age_sec !== undefined && (
              <span className="text-[11px] text-slate-400 font-normal">
                ({diagnostics.last_record_age_sec.toFixed(1)}s ago)
              </span>
            )}
          </div>

          {/* WebSocket Status */}
          <div className="px-3 py-1.5 rounded-xl bg-navy-900 border border-cyan-500/20 text-xs font-mono flex items-center gap-1.5 text-slate-300">
            <span className={`w-2 h-2 rounded-full ${isConnected ? 'bg-cyan-400' : 'bg-rose-500'}`}></span>
            <span>WS: {isConnected ? 'CONNECTED' : 'DISCONNECTED'}</span>
          </div>

          {/* Hardware Telemetry Rate */}
          <div className="px-3 py-1.5 rounded-xl bg-navy-900 border border-cyan-500/20 text-xs font-mono text-slate-300 flex items-center gap-2">
            <span>Rate: <strong className="text-cyan-300">{diagnostics?.telemetry_hz || 0.5} Hz</strong></span>
            <span className="text-slate-600">|</span>
            <span>Radio: <strong className="text-slate-200">nRF24 250kbps</strong></span>
          </div>
        </div>
      </div>

      {/* Arduino Uno nRF24 Telemetry & Dual Flow Verification Card */}
      <ArduinoWirelessFlowCard />

      {/* Sensor Cards Row */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <SensorCard
          sensorId="s1"
          title="Piezoelectric Sensor 1"
          position="0.0 Meters"
          gpio="Arduino ADC A0"
          latest={latestTelemetry}
          baseline={baseline}
          abnormalSecCount={s1AbnormalSec}
        />
        <SensorCard
          sensorId="s2"
          title="Piezoelectric Sensor 2"
          position="2.0 Meters"
          gpio="Arduino ADC A1"
          latest={latestTelemetry}
          baseline={baseline}
          abnormalSecCount={s2AbnormalSec}
        />
      </div>

      {/* High-Resolution Leak Localization (TDOA) Section */}
      <HighResolutionLocalizationCard />

      {/* Interactive Live GPS Map Section */}
      <LiveGpsMap />


      {/* Main Real-Time Telemetry Graph */}
      <LiveDualChart
        data={telemetryHistory}
        baseline={baseline}
        isPaused={isPaused}
        onTogglePause={() => setPaused(!isPaused)}
      />

      {/* Bottom Row: 60s Analysis Progress & Recent Events */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <ProgressIndicator
          currentSecond={currentWindowSec}
          windowCount={latestDecision?.window_index || 1}
          totalAlerts={latestDecision && latestDecision.decision !== 'NORMAL' ? 1 : 0}
          lastAlertTimestamp={latestDecision?.timestamp}
        />
        <RecentEventsPanel />
      </div>
    </div>
  );
};

