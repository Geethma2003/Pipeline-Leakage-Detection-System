import React, { useState, useEffect } from 'react';
import { useTelemetry } from '../../context/TelemetryContext';
import { api } from '../../services/api';
import { SerialPortInfo } from '../../types';
import { Settings, Cpu, Radio, RefreshCw, AlertTriangle, ShieldCheck, CheckCircle2, Terminal, Wifi, Plug } from 'lucide-react';

export const SettingsHardwareView: React.FC = () => {
  const { diagnostics, adc, sendHardwareCommand } = useTelemetry();
  const [ports, setPorts] = useState<SerialPortInfo[]>([]);
  const [selectedPort, setSelectedPort] = useState<string>('');
  const [baudRate, setBaudRate] = useState<number>(115200);
  const [loadingPorts, setLoadingPorts] = useState<boolean>(false);
  const [connecting, setConnecting] = useState<boolean>(false);

  const [persistenceParam, setPersistenceParam] = useState<number>(42);
  const [recalibrateConfirm, setRecalibrateConfirm] = useState<boolean>(false);
  const [recalibrateLoading, setRecalibrateLoading] = useState<boolean>(false);
  const [actionMessage, setActionMessage] = useState<{ text: string; isError: boolean } | null>(null);

  useEffect(() => {
    fetchPorts();
  }, []);

  const fetchPorts = async () => {
    setLoadingPorts(true);
    try {
      const data = await api.getSerialPorts();
      setPorts(data);
      
      if (data.length > 0) {
        // Find if active port or existing selection is in list
        const activeDevice = diagnostics?.serial_port && data.some(p => p.device === diagnostics.serial_port) ? diagnostics.serial_port : null;
        const existingDevice = selectedPort && data.some(p => p.device === selectedPort) ? selectedPort : null;
        const esp32Device = data.find(p => p.is_esp32)?.device;
        
        setSelectedPort(activeDevice || existingDevice || esp32Device || data[0].device);
      } else {
        setSelectedPort('');
      }
    } catch (e: any) {
      console.error('Failed to fetch serial ports', e);
      setActionMessage({ text: `Failed to scan serial ports: ${e.message}`, isError: true });
    } finally {
      setLoadingPorts(false);
    }
  };

  const handleConnect = async () => {
    if (!selectedPort) {
      setActionMessage({ text: 'Please select a valid COM port to connect.', isError: true });
      return;
    }
    setConnecting(true);
    setActionMessage(null);
    try {
      await api.connectSerial(selectedPort, baudRate);
      setActionMessage({
        text: `Connected successfully to ${selectedPort} at ${baudRate} baud. Live Arduino Uno serial data active.`,
        isError: false
      });
      // Refresh port scan list after connecting
      fetchPorts();
    } catch (e: any) {
      setActionMessage({ text: `Connection Error: ${e.message}`, isError: true });
    } finally {
      setConnecting(false);
    }
  };

  const handleDisconnect = async () => {
    try {
      await api.disconnectSerial();
      setActionMessage({ text: 'Disconnected serial port. Switched to Demo Mode.', isError: false });
    } catch (e: any) {
      setActionMessage({ text: `Disconnect Error: ${e.message}`, isError: true });
    }
  };

  const handleTriggerRecalibration = async () => {
    if (!recalibrateConfirm) {
      alert('You must confirm that the pump is running normally and NO leak is present before recalibrating baseline.');
      return;
    }
    setRecalibrateLoading(true);
    try {
      await sendHardwareCommand('RECALIBRATE', undefined, true);
      setActionMessage({ text: 'Dispatched 60-second baseline recalibration command to Arduino firmware.', isError: false });
    } catch (e: any) {
      setActionMessage({ text: `Recalibration Error: ${e.message}`, isError: true });
    } finally {
      setRecalibrateLoading(false);
    }
  };

  const handleSetPersistence = async () => {
    try {
      await sendHardwareCommand('SET_PERSISTENCE', persistenceParam);
      setActionMessage({ text: `Updated persistence threshold parameter to ${persistenceParam}/60 seconds.`, isError: false });
    } catch (e: any) {
      setActionMessage({ text: `Param Error: ${e.message}`, isError: true });
    }
  };

  const connStatus = diagnostics?.connection_status || 'DISCONNECTED';

  return (
    <div className="space-y-6">
      {/* Active Diagnostics & Status Header Banner */}
      <div className="glass-card p-6 flex flex-wrap items-center justify-between gap-4 border-l-4 border-l-cyan-500">
        <div>
          <h2 className="text-xl font-bold text-slate-100 font-outfit flex items-center gap-2">
            <Cpu className="w-6 h-6 text-cyan-400" />
            Hardware & Communication Settings
          </h2>
          <p className="text-xs text-slate-400 mt-1 font-mono">
            Active Port: <span className="text-cyan-300 font-bold">{diagnostics?.serial_port || 'None'}</span> | Uptime: <span className="text-slate-200">{diagnostics?.esp32_uptime_sec || 0}s</span> | Rate: <span className="text-slate-200">{diagnostics?.sample_rate_hz || 1000} Hz</span>
          </p>
        </div>

        <div className="flex items-center gap-3">
          {connStatus === 'CONNECTED' && (
            <span className="px-3.5 py-1.5 rounded-full text-xs font-bold font-mono bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 flex items-center gap-1.5 shadow-glow-emerald">
              <CheckCircle2 className="w-4 h-4 text-emerald-400" />
              LIVE ARDUINO UNO CONNECTED
            </span>
          )}
          {connStatus === 'PORT_LOCKED' && (
            <span className="px-3.5 py-1.5 rounded-full text-xs font-bold font-mono bg-amber-500/20 text-amber-300 border border-amber-500/40 flex items-center gap-1.5">
              <AlertTriangle className="w-4 h-4 text-amber-400" />
              PORT LOCKED BY OTHER APP
            </span>
          )}
          {connStatus === 'DEMO_MODE' && (
            <span className="px-3.5 py-1.5 rounded-full text-xs font-bold font-mono bg-cyan-500/20 text-cyan-300 border border-cyan-500/40 flex items-center gap-1.5">
              <Radio className="w-4 h-4 text-cyan-400" />
              DEMO SIMULATION MODE
            </span>
          )}
          {connStatus === 'DISCONNECTED' && (
            <span className="px-3.5 py-1.5 rounded-full text-xs font-bold font-mono bg-rose-500/20 text-rose-300 border border-rose-500/40 flex items-center gap-1.5">
              <Plug className="w-4 h-4 text-rose-400" />
              DISCONNECTED
            </span>
          )}
        </div>
      </div>

      {/* Serial Port Connection Card */}
      <div className="glass-card p-6 space-y-4">
        <div className="flex items-center justify-between pb-3 border-b border-cyan-500/15">
          <h3 className="font-bold text-lg text-slate-100 flex items-center gap-2 font-outfit">
            <Radio className="w-5 h-5 text-cyan-400" />
            Arduino Uno Serial USB Connection Manager
          </h3>
          <button
            onClick={fetchPorts}
            disabled={loadingPorts}
            className="p-2 px-3 rounded-lg bg-navy-950 text-slate-300 hover:text-white border border-cyan-500/20 text-xs flex items-center gap-1.5 transition"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loadingPorts ? 'animate-spin text-cyan-400' : ''}`} />
            Scan Ports
          </button>
        </div>

        {actionMessage && (
          <div className={`p-3 rounded-lg border text-xs font-mono flex items-start gap-2 ${
            actionMessage.isError
              ? 'bg-rose-500/15 border-rose-500/40 text-rose-300'
              : 'bg-emerald-500/15 border-emerald-500/40 text-emerald-300'
          }`}>
            {actionMessage.isError ? <AlertTriangle className="w-4 h-4 shrink-0 text-rose-400 mt-0.5" /> : <ShieldCheck className="w-4 h-4 shrink-0 text-emerald-400 mt-0.5" />}
            <div>{actionMessage.text}</div>
          </div>
        )}

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-xs">
          <div>
            <label className="text-slate-400 block font-mono mb-1">Serial COM Port:</label>
            <select
              value={selectedPort}
              onChange={(e) => setSelectedPort(e.target.value)}
              className="w-full bg-navy-950 border border-cyan-500/20 rounded-lg p-2.5 text-slate-200 focus:outline-none focus:border-cyan-500/50 font-mono"
            >
              {ports.map((p) => (
                <option key={p.device} value={p.device}>
                  {p.device} - {p.description}{p.is_esp32 ? ' [Arduino/Serial Detected]' : ''}
                </option>
              ))}
              {ports.length === 0 && <option value="">No COM Ports Found (Click Scan)</option>}
            </select>
          </div>

          <div>
            <label className="text-slate-400 block font-mono mb-1">Baud Rate:</label>
            <select
              value={baudRate}
              onChange={(e) => setBaudRate(Number(e.target.value))}
              className="w-full bg-navy-950 border border-cyan-500/20 rounded-lg p-2.5 text-slate-200 focus:outline-none focus:border-cyan-500/50 font-mono"
            >
              <option value={115200}>115200 (Arduino Default)</option>
              <option value={9600}>9600</option>
              <option value={57600}>57600</option>
              <option value={230400}>230400</option>
            </select>
          </div>

          <div className="flex items-end gap-2">
            <button
              onClick={handleConnect}
              disabled={connecting || !selectedPort}
              className={`flex-1 py-2.5 rounded-lg font-semibold text-xs transition ${
                connecting || !selectedPort
                  ? 'bg-navy-950 text-slate-600 border border-slate-800 cursor-not-allowed'
                  : 'bg-cyan-500/20 text-cyan-300 hover:bg-cyan-500/30 border border-cyan-500/40 shadow-glow-cyan'
              }`}
            >
              {connecting ? 'Connecting...' : 'Connect Serial'}
            </button>
            <button
              onClick={handleDisconnect}
              className="px-4 py-2.5 rounded-lg bg-navy-950 text-slate-400 hover:text-slate-200 border border-slate-800 font-semibold"
            >
              Disconnect
            </button>
          </div>
        </div>

        {/* Port Ownership Warning */}
        <div className="p-3.5 rounded-xl bg-navy-950/80 border border-amber-500/30 text-xs space-y-1">
          <span className="font-bold text-amber-400 flex items-center gap-1.5 font-mono">
            <AlertTriangle className="w-4 h-4 text-amber-400" /> COM Port Single-Owner Constraint Notice
          </span>
          <p className="text-slate-300 text-[11px] leading-relaxed">
            Windows permits only one application to open a COM serial port at a time. Close Arduino Serial Monitor, VS Code Serial Terminal, or <code className="text-cyan-300 font-mono">serial_logger.py</code> before clicking <strong>Connect Serial</strong> to avoid <code className="text-rose-400 font-mono">Access is denied</code> error locks.
          </p>
        </div>
      </div>

      {/* Recalibration & Parameters */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Baseline Recalibration Card */}
        <div className="glass-card p-6 space-y-4">
          <h4 className="font-bold text-base text-slate-100 flex items-center gap-2 font-outfit">
            <RefreshCw className="w-5 h-5 text-cyan-400" />
            Baseline Recalibration Control ('B' Command)
          </h4>
          <p className="text-xs text-slate-400 leading-relaxed">
            Triggers a 60-second baseline collection on Arduino Uno to re-evaluate median RMS and MAD thresholds.
          </p>

          <label className="flex items-center gap-2.5 p-3 rounded-lg bg-navy-950 border border-amber-500/30 text-xs cursor-pointer">
            <input
              type="checkbox"
              checked={recalibrateConfirm}
              onChange={(e) => setRecalibrateConfirm(e.target.checked)}
              className="rounded bg-navy-900 border-slate-700 text-cyan-500 focus:ring-cyan-500"
            />
            <span className="text-amber-300 font-medium">
              I confirm the water pump is operating normally and NO leak is present.
            </span>
          </label>

          <button
            onClick={handleTriggerRecalibration}
            disabled={!recalibrateConfirm || recalibrateLoading}
            className={`w-full py-2.5 rounded-lg text-xs font-bold transition ${
              recalibrateConfirm
                ? 'bg-cyan-500/20 text-cyan-300 hover:bg-cyan-500/30 border border-cyan-500/40 shadow-glow-cyan'
                : 'bg-navy-950 text-slate-600 border border-slate-800 cursor-not-allowed'
            }`}
          >
            {recalibrateLoading ? 'Recalibrating...' : 'Trigger Recalibration (Send "B" Command)'}
          </button>
        </div>

        {/* Configurable Persistence Threshold */}
        <div className="glass-card p-6 space-y-4">
          <h4 className="font-bold text-base text-slate-100 flex items-center gap-2 font-outfit">
            <Terminal className="w-5 h-5 text-cyan-400" />
            Configurable Persistence Parameter ('P' Command)
          </h4>
          <p className="text-xs text-slate-400">
            Set required abnormal seconds in 60s window (Default: 42 out of 60 seconds = 70% persistence).
          </p>

          <div className="flex items-center gap-3">
            <input
              type="number"
              min={10}
              max={60}
              value={persistenceParam}
              onChange={(e) => setPersistenceParam(Number(e.target.value))}
              className="w-24 bg-navy-950 border border-cyan-500/20 rounded-lg p-2 text-center text-cyan-300 font-mono font-bold text-sm focus:outline-none focus:border-cyan-500/50"
            />
            <span className="text-xs text-slate-400 font-mono">/ 60 seconds</span>
            <button
              onClick={handleSetPersistence}
              className="px-4 py-2 rounded-lg bg-cyan-500/20 text-cyan-300 hover:bg-cyan-500/30 border border-cyan-500/40 text-xs font-semibold ml-auto"
            >
              Apply Parameter
            </button>
          </div>
        </div>
      </div>

      {/* ADC Signal Conditioning & Raw Hardware Diagnostics */}
      <div className="glass-card p-6 space-y-5 border-l-4 border-l-cyan-500">
        <div className="flex flex-wrap items-center justify-between gap-3 pb-3 border-b border-cyan-500/15">
          <div>
            <h3 className="font-bold text-lg text-slate-100 flex items-center gap-2 font-outfit">
              <Cpu className="w-5 h-5 text-cyan-400" />
              Raw ADC Hardware Conditioning & Rail Bias Diagnostics
            </h3>
            <p className="text-xs text-slate-400 mt-1">
              Live per-second ADC sample rail analysis for Piezo Sensor 1 (A0) and Piezo Sensor 2 (A1)
            </p>
          </div>
          {((adc?.s1_clips || 0) > 0 || (adc?.s2_clips || 0) > 0) && (
            <span className="px-3 py-1 rounded-full text-xs font-bold font-mono bg-rose-500/20 text-rose-300 border border-rose-500/40 flex items-center gap-1.5 animate-pulse">
              <AlertTriangle className="w-4 h-4 text-rose-400" />
              ADC CLIPPING FAULT DETECTED
            </span>
          )}
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs font-mono">
          {/* Sensor 1 Channel Card */}
          <div className="p-4 rounded-xl bg-navy-950/80 border border-cyan-500/20 space-y-3">
            <div className="flex justify-between items-center pb-2 border-b border-cyan-500/10">
              <span className="font-bold text-cyan-300">Piezo Sensor 1 — A0</span>
              <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                (adc?.s1_clips || 0) > 25 ? 'bg-rose-500/20 text-rose-300 border border-rose-500/30' : 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30'
              }`}>
                {(adc?.s1_clips || 0) > 25 ? 'CLIPPED' : 'NORMAL'}
              </span>
            </div>
            <div className="grid grid-cols-2 gap-2 text-[11px]">
              <div>
                <span className="text-slate-500 block">DC Bias (Mean):</span>
                <span className="text-slate-200 font-bold">{adc?.s1_mean?.toFixed(1) ?? diagnostics?.s1_mean?.toFixed(1) ?? '2048.0'} counts (~{(((adc?.s1_mean ?? diagnostics?.s1_mean ?? 2048.0) * 3.3) / 4095).toFixed(2)}V)</span>
              </div>
              <div>
                <span className="text-slate-500 block">Min .. Max:</span>
                <span className="text-slate-200 font-bold">[{adc?.s1_min ?? diagnostics?.s1_min ?? 0} .. {adc?.s1_max ?? diagnostics?.s1_max ?? 4095}]</span>
              </div>
              <div>
                <span className="text-slate-500 block">Rail Hits:</span>
                <span className={`font-bold ${(adc?.s1_clips || 0) > 0 ? 'text-rose-400' : 'text-slate-200'}`}>
                  {adc?.s1_clips ?? diagnostics?.s1_clips ?? 0} samples
                </span>
              </div>
              <div>
                <span className="text-slate-500 block">Clipping %:</span>
                <span className={`font-bold ${(adc?.s1_clip_pct || 0) > 2.0 ? 'text-rose-400' : 'text-slate-200'}`}>
                  {(adc?.s1_clip_pct ?? diagnostics?.s1_clip_pct ?? 0.0).toFixed(1)}%
                </span>
              </div>
            </div>
          </div>

          {/* Sensor 2 Channel Card */}
          <div className="p-4 rounded-xl bg-navy-950/80 border border-orange-500/20 space-y-3">
            <div className="flex justify-between items-center pb-2 border-b border-orange-500/10">
              <span className="font-bold text-orange-300">Piezo Sensor 2 — A1</span>
              <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                (adc?.s2_clips || 0) > 25 ? 'bg-rose-500/20 text-rose-300 border border-rose-500/30' : 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30'
              }`}>
                {(adc?.s2_clips || 0) > 25 ? 'CLIPPED' : 'NORMAL'}
              </span>
            </div>
            <div className="grid grid-cols-2 gap-2 text-[11px]">
              <div>
                <span className="text-slate-500 block">DC Bias (Mean):</span>
                <span className={`font-bold ${((adc?.s2_mean ?? diagnostics?.s2_mean ?? 2048) < 1000 || (adc?.s2_mean ?? diagnostics?.s2_mean ?? 2048) > 3000) ? 'text-rose-400' : 'text-slate-200'}`}>
                  {adc?.s2_mean?.toFixed(1) ?? diagnostics?.s2_mean?.toFixed(1) ?? '2048.0'} counts (~{(((adc?.s2_mean ?? diagnostics?.s2_mean ?? 2048.0) * 3.3) / 4095).toFixed(2)}V)
                </span>
              </div>
              <div>
                <span className="text-slate-500 block">Min .. Max:</span>
                <span className="text-slate-200 font-bold">[{adc?.s2_min ?? diagnostics?.s2_min ?? 0} .. {adc?.s2_max ?? diagnostics?.s2_max ?? 4095}]</span>
              </div>
              <div>
                <span className="text-slate-500 block">Rail Hits:</span>
                <span className={`font-bold ${(adc?.s2_clips || 0) > 0 ? 'text-rose-400' : 'text-slate-200'}`}>
                  {adc?.s2_clips ?? diagnostics?.s2_clips ?? 0} samples
                </span>
              </div>
              <div>
                <span className="text-slate-500 block">Clipping %:</span>
                <span className={`font-bold ${(adc?.s2_clip_pct || 0) > 2.0 ? 'text-rose-400' : 'text-slate-200'}`}>
                  {(adc?.s2_clip_pct ?? diagnostics?.s2_clip_pct ?? 0.0).toFixed(1)}%
                </span>
              </div>
            </div>
          </div>
        </div>

        {/* Physical Troubleshooting Checklist */}
        <div className="p-4 rounded-xl bg-navy-950/60 border border-cyan-500/15 space-y-2 text-xs">
          <h4 className="font-bold text-slate-200 flex items-center gap-1.5 font-outfit text-sm">
            <ShieldCheck className="w-4 h-4 text-cyan-400" />
            Piezo Sensor 2 (A1) Hardware Clipping Troubleshooting Procedure:
          </h4>
          <ol className="list-decimal list-inside space-y-1 text-slate-300 text-[11px] leading-relaxed">
            <li><strong>DC Bias Check:</strong> Measure DC voltage with a multimeter at Arduino A1 with pump stopped. On Arduino Uno (5V ref), it must sit at ~2.5V (±0.25V). If 0V or 5V, check the voltage divider.</li>
            <li><strong>AC Coupling:</strong> Confirm a 0.1µF (100nF) ceramic capacitor is in series between the piezo transducer and A1 to block sensor DC offset.</li>
            <li><strong>Charge Bleeder Resistor:</strong> Ensure a 1MΩ resistor is connected across the piezo element to dissipate piezoelectric pyroelectric charge accumulation.</li>
            <li><strong>Clamping Protection:</strong> Verify BAT54S dual Schottky diodes are clamping A1 to GND and 5V to prevent destructive overvoltage.</li>
            <li><strong>GPS & Ground Isolation:</strong> Keep GPS UART wiring away from high-impedance piezo leads, and ensure common GND with Arduino Uno.</li>
          </ol>
        </div>
      </div>
    </div>
  );
};
