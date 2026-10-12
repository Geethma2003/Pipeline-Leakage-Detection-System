import React from 'react';
import { Activity, ShieldCheck, AlertCircle, AlertTriangle, Waves, Cpu } from 'lucide-react';
import { TelemetryRecord, BaselineProfile } from '../../types';
import { useTelemetry } from '../../context/TelemetryContext';

interface SensorCardProps {
  sensorId: 's1' | 's2';
  title: string;
  position: string;
  gpio: string;
  latest: TelemetryRecord | null;
  baseline: BaselineProfile;
  abnormalSecCount: number;
}

export const SensorCard: React.FC<SensorCardProps> = React.memo(({
  sensorId,
  title,
  position,
  gpio,
  latest,
  baseline,
  abnormalSecCount
}) => {
  const { adc, diagnostics, wireless } = useTelemetry();

  const rms = sensorId === 's1' ? (wireless?.rms1 ?? latest?.s1_rms ?? 0) : (wireless?.rms2 ?? latest?.s2_rms ?? 0);
  const p2p = sensorId === 's1' ? (wireless?.p2p1 ?? latest?.s1_p2p ?? 0) : (wireless?.p2p2 ?? latest?.s2_p2p ?? 0);
  const variance = sensorId === 's1' ? (latest?.s1_variance ?? 0) : (latest?.s2_variance ?? 0);
  const isAbnormal = sensorId === 's1' ? latest?.s1_abnormal === 1 : latest?.s2_abnormal === 1;
  const thresh = sensorId === 's1' ? baseline.s1_thresh : baseline.s2_thresh;
  const baselineMedian = sensorId === 's1' ? baseline.s1_rms_median : baseline.s2_rms_median;

  const isWirelessClipped = sensorId === 's1' ? wireless?.s1_clipped : wireless?.s2_clipped;
  const isVibInvalid = wireless?.vibration_invalid;

  // Raw ADC metrics from firmware telemetry
  const rawMin = sensorId === 's1' ? (adc?.s1_min ?? diagnostics?.s1_min ?? 0) : (adc?.s2_min ?? diagnostics?.s2_min ?? 0);
  const rawMax = sensorId === 's1' ? (adc?.s1_max ?? diagnostics?.s1_max ?? 1023) : (adc?.s2_max ?? diagnostics?.s2_max ?? 1023);
  const rawMean = sensorId === 's1' ? (adc?.s1_mean ?? diagnostics?.s1_mean ?? 512.0) : (adc?.s2_mean ?? diagnostics?.s2_mean ?? 512.0);
  const railClips = sensorId === 's1' ? (adc?.s1_clips ?? diagnostics?.s1_clips ?? 0) : (adc?.s2_clips ?? diagnostics?.s2_clips ?? 0);
  const clipPct = sensorId === 's1' ? (adc?.s1_clip_pct ?? diagnostics?.s1_clip_pct ?? 0.0) : (adc?.s2_clip_pct ?? diagnostics?.s2_clip_pct ?? 0.0);

  // Saturation / Clipping Detection (10-bit Arduino ADC max is 1023)
  const isClipped = Boolean(isWirelessClipped || railClips > 10 || p2p >= 1020.0 || clipPct > 2.0);
  const biasVolts = (rawMean * 5.0) / 1023.0;
  const isBiasAbnormal = rawMean < 200 || rawMean > 850;

  const borderGlow = (latest || wireless)
    ? isClipped
      ? 'border-rose-500/80 shadow-glow-red ring-1 ring-rose-500/50'
      : isAbnormal
      ? 'border-red-500/60 shadow-glow-red'
      : sensorId === 's1'
      ? 'border-cyan-500/25 hover:border-cyan-500/40'
      : 'border-orange-500/25 hover:border-orange-500/40'
    : 'border-slate-800 opacity-80';

  return (
    <div className={`glass-card p-5 relative overflow-hidden transition-all duration-300 ${borderGlow}`}>
      {/* Background Accent Gradient */}
      <div className={`absolute top-0 right-0 w-32 h-32 opacity-10 rounded-full blur-2xl ${
        sensorId === 's1' ? 'bg-cyan-500' : 'bg-orange-500'
      }`} />

      <div className="flex items-center justify-between mb-3 pb-2 border-b border-cyan-500/15 relative z-10">
        <div className="flex items-center gap-2.5">
          <div className={`w-8 h-8 rounded-lg flex items-center justify-center font-bold text-xs ${
            sensorId === 's1' ? 'bg-cyan-500/20 text-cyan-400 border border-cyan-500/30' : 'bg-orange-500/20 text-orange-400 border border-orange-500/30'
          }`}>
            {sensorId.toUpperCase()}
          </div>
          <div>
            <h4 className="font-semibold text-sm text-slate-100 font-outfit">{title}</h4>
            <span className="text-[10px] font-mono text-slate-400">Position: {position} (Arduino 10-bit ADC)</span>
          </div>
        </div>

        <span className={`px-2.5 py-1 rounded-full text-[10px] font-bold tracking-wider uppercase border flex items-center gap-1 ${
          (!latest && !wireless)
            ? 'bg-slate-800/60 text-slate-400 border-slate-700'
            : isClipped
            ? 'bg-rose-500/25 text-rose-300 border-rose-500/60 animate-pulse'
            : isVibInvalid
            ? 'bg-amber-500/20 text-amber-300 border-amber-500/40'
            : isAbnormal
            ? 'bg-red-500/20 text-red-400 border-red-500/40 animate-pulse'
            : 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30'
        }`}>
          {isClipped && <AlertTriangle className="w-3 h-3 text-rose-400 inline" />}
          {(!latest && !wireless) ? 'Awaiting Telemetry' : isClipped ? 'ADC Clipping Warning' : isVibInvalid ? 'Signal Invalid' : isAbnormal ? 'Abnormal Second' : 'Normal'}
        </span>
      </div>

      {/* Main RMS Reading */}
      <div className="grid grid-cols-2 gap-4 my-3 relative z-10">
        <div>
          <span className="text-[11px] font-mono text-slate-400 uppercase tracking-wider block">Live RMS (10-bit ADC Counts)</span>
          <div className="flex items-baseline gap-1.5 mt-0.5">
            {(latest || wireless) ? (
              <>
                <span className={`text-3xl font-extrabold tracking-tight font-outfit ${
                  isClipped ? 'text-rose-400' : isAbnormal ? 'text-red-400' : sensorId === 's1' ? 'text-cyan-400' : 'text-orange-400'
                }`}>
                  {rms.toFixed(1)}
                </span>
                <span className="text-xs text-slate-500 font-mono">Counts</span>
              </>
            ) : (
              <span className="text-xl font-bold text-slate-500 font-mono italic">NO DATA</span>
            )}
          </div>
        </div>

        <div>
          <span className="text-[11px] font-mono text-slate-400 uppercase tracking-wider block">Threshold</span>
          <div className="flex items-baseline gap-1.5 mt-0.5">
            <span className="text-xl font-bold text-slate-300 font-mono">{thresh.toFixed(1)}</span>
            <span className="text-[10px] text-slate-500">Median: {baselineMedian.toFixed(1)}</span>
          </div>
        </div>
      </div>

      {/* Secondary Metrics */}
      <div className="grid grid-cols-3 gap-2 pt-3 border-t border-cyan-500/10 text-xs relative z-10">
        <div className="bg-navy-950/60 p-2 rounded-lg border border-slate-800">
          <span className="text-[10px] text-slate-400 block font-mono">Peak-Peak (Counts)</span>
          <span className={`font-semibold font-mono ${p2p >= 1020 ? 'text-rose-400 font-bold' : 'text-slate-200'}`}>
            {(latest || wireless) ? p2p.toFixed(0) : '--'}
          </span>
        </div>
        <div className="bg-navy-950/60 p-2 rounded-lg border border-slate-800">
          <span className="text-[10px] text-slate-400 block font-mono">Variance</span>
          <span className="font-semibold text-slate-200 font-mono">{latest ? variance.toFixed(0) : '--'}</span>
        </div>
        <div className="bg-navy-950/60 p-2 rounded-lg border border-slate-800">
          <span className="text-[10px] text-slate-400 block font-mono">Abnormal (60s)</span>
          <span className={`font-semibold font-mono ${abnormalSecCount >= 42 ? 'text-red-400 font-bold' : 'text-slate-200'}`}>
            {abnormalSecCount}/60s
          </span>
        </div>
      </div>

      {/* Raw ADC Hardware Conditioning & Diagnostics Section */}
      <div className="mt-3 pt-2.5 border-t border-cyan-500/10 text-[11px] font-mono space-y-1.5 relative z-10">
        <div className="flex items-center justify-between text-slate-400">
          <span className="flex items-center gap-1 text-[10px] uppercase tracking-wider">
            <Cpu className="w-3 h-3 text-cyan-400" /> Raw ADC Hardware Bias:
          </span>
          <span className={`font-bold ${isBiasAbnormal ? 'text-amber-400' : 'text-emerald-400'}`}>
            {rawMean.toFixed(1)} counts ({biasVolts.toFixed(2)}V)
          </span>
        </div>

        <div className="grid grid-cols-2 gap-2 text-[10px]">
          <div className="bg-navy-950/80 px-2 py-1.5 rounded border border-slate-800/80 flex justify-between">
            <span className="text-slate-500">Min..Max:</span>
            <span className="text-slate-300 font-semibold">[{rawMin} .. {rawMax}]</span>
          </div>
          <div className={`px-2 py-1.5 rounded border flex justify-between ${
            railClips > 0 ? 'bg-rose-500/10 border-rose-500/40 text-rose-300' : 'bg-navy-950/80 border-slate-800/80 text-slate-300'
          }`}>
            <span className={railClips > 0 ? 'text-rose-400' : 'text-slate-500'}>Clips / %:</span>
            <span className="font-bold">{railClips} ({clipPct.toFixed(1)}%)</span>
          </div>
        </div>

        {isClipped && (
          <div className="p-2 rounded bg-rose-500/15 border border-rose-500/30 text-[10px] text-rose-300 flex items-start gap-1.5">
            <AlertCircle className="w-3.5 h-3.5 text-rose-400 mt-0.5 shrink-0" />
            <span>
              <strong>ADC Clipping Fault:</strong> Signal is hitting 0V or 3.3V rails ({clipPct.toFixed(1)}% clipped). Check 1.65V DC divider, piezo bleeder resistor, or preamp gain.
            </span>
          </div>
        )}
      </div>
    </div>
  );
});
