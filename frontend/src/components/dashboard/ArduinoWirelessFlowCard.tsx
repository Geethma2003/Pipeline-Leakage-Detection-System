import React from 'react';
import { Radio, Droplet, AlertTriangle, CheckCircle, ShieldAlert, WifiOff, Clock, Layers, RefreshCw } from 'lucide-react';
import { useTelemetry } from '../../context/TelemetryContext';

export const ArduinoWirelessFlowCard: React.FC = React.memo(() => {
  const { wireless, flow, diagnostics, demoMode } = useTelemetry();

  const source = wireless?.communication_source || "ARDUINO_UNO_NRF24";
  const port = diagnostics?.serial_port || "COM14";
  const baud = diagnostics?.baud_rate || 115200;
  const isConnected = diagnostics?.connection_status === 'CONNECTED';

  // Metrics
  const flowIn = wireless?.flow_in_lpm ?? flow?.flow_in_lpm ?? 0.0;
  const flowOut = wireless?.flow_out_lpm ?? flow?.flow_out_lpm ?? 0.0;
  const flowDiff = wireless?.flow_diff_lpm ?? flow?.flow_diff_lpm ?? Math.abs(flowIn - flowOut);
  const leakAlarm = wireless?.leak_alarm ?? flow?.leak_confirmed ?? false;
  const statusStr = wireless?.status_str ?? flow?.status ?? (flowIn < 0.5 ? "LOW_OR_NO_FLOW" : (leakAlarm ? "LEAK_CONFIRMED" : "NO_LEAK"));

  // Radio diagnostics
  const sequence = wireless?.packet_sequence ?? 0;
  const nodeId = wireless?.node_id ?? 1;
  const missed = wireless?.missed_packets ?? 0;
  const seqReset = wireless?.sequence_reset ?? 0;
  const isClipped1 = wireless?.s1_clipped ?? false;
  const isClipped2 = wireless?.s2_clipped ?? false;
  const isVibInvalid = wireless?.vibration_invalid ?? false;

  const lastRxIso = wireless?.utc_timestamp;
  const lastRxTimeStr = lastRxIso ? new Date(lastRxIso).toLocaleTimeString() : 'Awaiting packet...';

  // Status Badge Rendering
  let badgeColor = "bg-emerald-500/15 text-emerald-300 border-emerald-500/30";
  let badgeIcon = <CheckCircle className="w-4 h-4 text-emerald-400" />;
  let badgeText = "NORMAL FLOW (NO LEAK)";

  if (statusStr === "COMMUNICATION_LOST" || statusStr === "COMMUNICATION LOST") {
    badgeColor = "bg-rose-500/20 text-rose-300 border-rose-500/50 animate-pulse";
    badgeIcon = <WifiOff className="w-4 h-4 text-rose-400" />;
    badgeText = "COMMUNICATION LOST (>5s STALE)";
  } else if (statusStr === "LOW_OR_NO_FLOW") {
    badgeColor = "bg-slate-700/40 text-slate-300 border-slate-600";
    badgeIcon = <Droplet className="w-4 h-4 text-slate-400" />;
    badgeText = "LOW OR NO FLOW (< 0.50 L/min)";
  } else if (statusStr === "LEAK_CONFIRMED" || leakAlarm) {
    badgeColor = "bg-red-500/25 text-red-300 border-red-500/60 shadow-glow-red animate-pulse";
    badgeIcon = <ShieldAlert className="w-4 h-4 text-red-400" />;
    badgeText = "FLOW-BASED LEAK CONFIRMED (3x5s WINDOWS)";
  } else if (statusStr === "VERIFYING_FLOW" || flowDiff >= 0.10) {
    badgeColor = "bg-amber-500/20 text-amber-300 border-amber-500/40 shadow-glow-amber";
    badgeIcon = <AlertTriangle className="w-4 h-4 text-amber-400" />;
    badgeText = "FLOW IMBALANCE DETECTED (VERIFYING)";
  }

  return (
    <div className="glass-card p-5 relative overflow-hidden transition-all duration-300 border border-cyan-500/20">
      {/* Background Accent Gradient */}
      <div className="absolute top-0 right-0 w-64 h-64 bg-cyan-500/5 rounded-full blur-3xl pointer-events-none" />

      {/* Header Row */}
      <div className="flex flex-wrap items-center justify-between gap-4 mb-4 pb-3 border-b border-cyan-500/15 relative z-10">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-cyan-500/20 to-blue-600/20 border border-cyan-500/40 flex items-center justify-center shadow-glow-cyan">
            <Radio className="w-5 h-5 text-cyan-400" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h3 className="font-bold text-lg text-slate-100 font-outfit">
                Arduino Uno nRF24L01+ Wireless Telemetry
              </h3>
              <span className={`px-2 py-0.5 rounded text-[10px] font-mono font-bold uppercase tracking-wider border ${
                demoMode
                  ? 'bg-amber-500/15 text-amber-300 border-amber-500/30'
                  : 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30 shadow-glow-emerald'
              }`}>
                {demoMode ? 'SIMULATION' : 'LIVE COM14 HARDWARE'}
              </span>
            </div>
            <p className="text-xs text-slate-400">
              Receiver: Arduino Uno on {port} @ {baud} baud | Protocol: RF24_V1 Fixed-Point | Source: {source}
            </p>
          </div>
        </div>

        {/* Status Badge */}
        <div className={`px-3.5 py-1.5 rounded-xl border text-xs font-bold font-mono flex items-center gap-2 ${badgeColor}`}>
          {badgeIcon}
          <span>{badgeText}</span>
        </div>
      </div>

      {/* Flow Sensor Verification Row (2x YF-S201) */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-4 relative z-10">
        {/* Inlet Flow Card */}
        <div className="bg-navy-950/70 p-3.5 rounded-xl border border-cyan-500/20 relative">
          <span className="text-[11px] font-mono text-cyan-400 uppercase tracking-wider block">
            Inlet Flow (YF-S201)
          </span>
          <div className="flex items-baseline gap-1.5 mt-1">
            <span className="text-2xl font-extrabold text-slate-100 font-outfit">
              {flowIn.toFixed(2)}
            </span>
            <span className="text-xs text-cyan-400 font-mono">L/min</span>
          </div>
          <span className="text-[10px] text-slate-500 block mt-0.5 font-mono">
            Min threshold: 0.50 L/min
          </span>
        </div>

        {/* Outlet Flow Card */}
        <div className="bg-navy-950/70 p-3.5 rounded-xl border border-orange-500/20 relative">
          <span className="text-[11px] font-mono text-orange-400 uppercase tracking-wider block">
            Outlet Flow (YF-S201)
          </span>
          <div className="flex items-baseline gap-1.5 mt-1">
            <span className="text-2xl font-extrabold text-slate-100 font-outfit">
              {flowOut.toFixed(2)}
            </span>
            <span className="text-xs text-orange-400 font-mono">L/min</span>
          </div>
          <span className="text-[10px] text-slate-500 block mt-0.5 font-mono">
            Calculated over 5s windows
          </span>
        </div>

        {/* Flow Difference Card */}
        <div className="bg-navy-950/70 p-3.5 rounded-xl border border-rose-500/20 relative">
          <span className="text-[11px] font-mono text-rose-400 uppercase tracking-wider block">
            Flow Difference (|In - Out|)
          </span>
          <div className="flex items-baseline gap-1.5 mt-1">
            <span className={`text-2xl font-extrabold font-outfit ${flowDiff >= 0.10 && flowIn >= 0.50 ? 'text-rose-400' : 'text-slate-100'}`}>
              {flowDiff.toFixed(2)}
            </span>
            <span className="text-xs text-rose-400 font-mono">L/min</span>
          </div>
          <span className="text-[10px] text-slate-500 block mt-0.5 font-mono">
            Leak threshold: ≥ 0.10 L/min
          </span>
        </div>

        {/* Flow-based Leak Alarm State */}
        <div className={`p-3.5 rounded-xl border relative ${
          leakAlarm
            ? 'bg-red-500/15 border-red-500/50 shadow-glow-red'
            : 'bg-navy-950/70 border-cyan-500/20'
        }`}>
          <span className="text-[11px] font-mono text-slate-400 uppercase tracking-wider block">
            Flow Leak Alarm
          </span>
          <div className="flex items-baseline gap-2 mt-1">
            <span className={`text-2xl font-extrabold font-outfit ${leakAlarm ? 'text-red-400 animate-pulse' : 'text-emerald-400'}`}>
              {leakAlarm ? 'YES (ALARM)' : 'NO (CLEAR)'}
            </span>
          </div>
          <span className="text-[10px] text-slate-400 block mt-0.5 font-mono">
            {leakAlarm ? '3 consecutive 5s windows failed' : 'Confirmed on Arduino transmitter'}
          </span>
        </div>
      </div>

      {/* Wireless Link & Signal Diagnostics Bar */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-2.5 pt-3 border-t border-cyan-500/10 text-xs font-mono relative z-10">
        {/* Node & Sequence */}
        <div className="bg-navy-950/60 p-2.5 rounded-lg border border-slate-800">
          <span className="text-[10px] text-slate-400 block">Packet Sequence</span>
          <span className="font-bold text-cyan-300">#{sequence} (Node {nodeId})</span>
        </div>

        {/* Missed Packets */}
        <div className="bg-navy-950/60 p-2.5 rounded-lg border border-slate-800">
          <span className="text-[10px] text-slate-400 block">Missed Since Last</span>
          <span className={`font-bold ${missed > 0 ? 'text-amber-400' : 'text-slate-200'}`}>
            {missed} pkts {seqReset === 1 ? '(Reset)' : ''}
          </span>
        </div>

        {/* Vibration Clipping Warnings */}
        <div className="bg-navy-950/60 p-2.5 rounded-lg border border-slate-800">
          <span className="text-[10px] text-slate-400 block">Piezo Clipping Flag</span>
          <span className={`font-bold ${isClipped1 || isClipped2 ? 'text-rose-400' : 'text-emerald-400'}`}>
            {isClipped1 && isClipped2 ? 'S1 & S2 CLIP' : isClipped1 ? 'S1 CLIP' : isClipped2 ? 'S2 CLIP' : 'NONE (CLEAN)'}
          </span>
        </div>

        {/* Signal Validity */}
        <div className="bg-navy-950/60 p-2.5 rounded-lg border border-slate-800">
          <span className="text-[10px] text-slate-400 block">Vibration Validity</span>
          <span className={`font-bold ${isVibInvalid ? 'text-amber-400' : 'text-emerald-400'}`}>
            {isVibInvalid ? 'INVALID WINDOW' : 'VALID'}
          </span>
        </div>

        {/* Last Packet Reception */}
        <div className="bg-navy-950/60 p-2.5 rounded-lg border border-slate-800 col-span-2 md:col-span-1">
          <span className="text-[10px] text-slate-400 block flex items-center gap-1">
            <Clock className="w-3 h-3 text-cyan-400" /> Received At
          </span>
          <span className="font-bold text-slate-200 truncate block">
            {lastRxTimeStr}
          </span>
        </div>
      </div>
    </div>
  );
});
