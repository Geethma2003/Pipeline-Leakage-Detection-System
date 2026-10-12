import React, { createContext, useContext, useEffect, useState, useRef, useCallback } from 'react';
import {
  TelemetryRecord,
  BaselineProfile,
  WindowDecision,
  HardwareDiagnostics,
  TelemetryStreamPayload,
  GPSData,
  HighResLocalization,
  ADCDiagnostics,
  FlowTelemetry,
  WirelessTelemetry
} from '../types';
import { api } from '../services/api';

interface TelemetryContextType {
  isConnected: boolean;
  systemState: "INITIALIZING" | "NORMAL" | "SUSPECTED_ANOMALY" | "CONFIRMED_LEAK" | "SENSOR_FAULT" | "COMMUNICATION_LOST" | "LOW_OR_NO_FLOW" | string;
  demoMode: boolean;
  demoScenario: "normal" | "pump_disturbance" | "confirmed_leak";
  latestTelemetry: TelemetryRecord | null;
  baseline: BaselineProfile;
  currentWindowSec: number;
  latestDecision: WindowDecision | null;
  diagnostics: HardwareDiagnostics | null;
  gps: GPSData | null;
  localization: HighResLocalization | null;
  adc: ADCDiagnostics | null;
  flow: FlowTelemetry | null;
  wireless: WirelessTelemetry | null;
  telemetryHistory: TelemetryRecord[];
  flowHistory: Array<{ timeStr: string; second_index: number; flow_in_lpm: number; flow_out_lpm: number; flow_diff_lpm: number }>;
  isPaused: boolean;
  firebaseStatus: { initialized: boolean; online: boolean; project_id: string; last_error?: string | null };
  setPaused: (paused: boolean) => void;
  toggleDemoMode: (enabled: boolean, scenario?: string) => Promise<void>;
  setDemoScenario: (scenario: "normal" | "pump_disturbance" | "confirmed_leak") => Promise<void>;
  sendHardwareCommand: (command: string, parameter?: number, confirmNoLeak?: boolean) => Promise<any>;
  clearHistory: () => void;
}

const defaultBaseline: BaselineProfile = {
  s1_rms_median: 12.0,
  s1_rms_mad: 1.2,
  s1_thresh: 25.0,
  s2_rms_median: 11.5,
  s2_rms_mad: 1.1,
  s2_thresh: 24.0,
  is_calibrated: true
};

const defaultDiagnostics: HardwareDiagnostics = {
  serial_port: 'NONE',
  baud_rate: 115200,
  connection_status: 'DEMO_MODE',
  esp32_uptime_sec: 0,
  sample_rate_hz: 1000,
  timing_overruns: 0,
  s1_adc_offset_ok: true,
  s2_adc_offset_ok: true,
  pipe_length_m: 2.0,
  s1_position_m: 0.0,
  s2_position_m: 2.0
};

const TelemetryContext = createContext<TelemetryContextType | undefined>(undefined);

export const TelemetryProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [isConnected, setIsConnected] = useState<boolean>(false);
  const [systemState, setSystemState] = useState<string>("INITIALIZING");
  const [demoMode, setDemoMode] = useState<boolean>(true);
  const [demoScenario, setDemoScenarioState] = useState<"normal" | "pump_disturbance" | "confirmed_leak">("normal");
  const [latestTelemetry, setLatestTelemetry] = useState<TelemetryRecord | null>(null);
  const [baseline, setBaseline] = useState<BaselineProfile>(defaultBaseline);
  const [currentWindowSec, setCurrentWindowSec] = useState<number>(0);
  const [latestDecision, setLatestDecision] = useState<WindowDecision | null>(null);
  const [diagnostics, setDiagnostics] = useState<HardwareDiagnostics | null>(defaultDiagnostics);
  const [gps, setGps] = useState<GPSData | null>(null);
  const [localization, setLocalization] = useState<HighResLocalization | null>(null);
  const [adc, setAdc] = useState<ADCDiagnostics | null>(null);
  const [flow, setFlow] = useState<FlowTelemetry | null>(null);
  const [wireless, setWireless] = useState<WirelessTelemetry | null>(null);
  const [telemetryHistory, setTelemetryHistory] = useState<TelemetryRecord[]>([]);
  const [flowHistory, setFlowHistory] = useState<Array<{ timeStr: string; second_index: number; flow_in_lpm: number; flow_out_lpm: number; flow_diff_lpm: number }>>([]);

  const [isPaused, setIsPaused] = useState<boolean>(false);
  const [firebaseStatus, setFirebaseStatus] = useState<{ initialized: boolean; online: boolean; project_id: string; last_error?: string | null }>({
    initialized: false,
    online: false,
    project_id: 'aquaguard-pipeline'
  });

  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimerRef = useRef<any>(null);
  const isUnmountedRef = useRef<boolean>(false);
  const isPausedRef = useRef<boolean>(isPaused);
  isPausedRef.current = isPaused;

  const checkFirebaseAndSerial = useCallback(async () => {
    if (isUnmountedRef.current) return;
    try {
      const fbStatus = await api.getFirebaseStatus();
      if (!isUnmountedRef.current) setFirebaseStatus(fbStatus);

      const serStatus = await api.getSerialStatus();
      if (!isUnmountedRef.current && serStatus && serStatus.connected) {
        setDiagnostics((prev) => ({
          ...(prev || defaultDiagnostics),
          serial_port: serStatus.port,
          baud_rate: serStatus.baud_rate,
          connection_status: 'CONNECTED'
        }));
      }

      const gpsLoc = await api.getGPSLocation();
      if (!isUnmountedRef.current && gpsLoc) {
        setGps(gpsLoc);
      }
    } catch (e) {
      console.warn('[CONTEXT] System status fetch warning:', e);
    }
  }, []);

  useEffect(() => {
    checkFirebaseAndSerial();
  }, [checkFirebaseAndSerial]);

  const connectWebSocket = useCallback(() => {
    if (isUnmountedRef.current) return;

    if (reconnectTimerRef.current) {
      clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    }

    if (wsRef.current && (wsRef.current.readyState === WebSocket.OPEN || wsRef.current.readyState === WebSocket.CONNECTING)) {
      return;
    }

    const wsUrl = (import.meta.env.VITE_WS_URL || 'ws://localhost:8000').replace(/^http/, 'ws') + '/ws/telemetry';
    const ws = new WebSocket(wsUrl);

    ws.onopen = () => {
      if (isUnmountedRef.current) {
        ws.close();
        return;
      }
      setIsConnected(true);
      console.log('[WS CONTEXT] Connected to WebSocket endpoint');
    };

    ws.onmessage = (event) => {
      if (isUnmountedRef.current) return;
      try {
        const payload: TelemetryStreamPayload = JSON.parse(event.data);
        if (payload.type === 'telemetry_update' || payload.diagnostics) {
          setSystemState(payload.system_state);
          setDemoMode(payload.demo_mode);
          setDemoScenarioState(payload.demo_scenario);
          setBaseline(payload.baseline);
          setCurrentWindowSec(payload.current_window_sec);
          if (payload.diagnostics) setDiagnostics(payload.diagnostics);
          if (payload.window_decision) setLatestDecision(payload.window_decision);
          if (payload.gps !== undefined) setGps(payload.gps);
          if (payload.localization !== undefined) setLocalization(payload.localization);
          if (payload.adc !== undefined) setAdc(payload.adc);
          if (payload.flow !== undefined) setFlow(payload.flow);
          if (payload.wireless !== undefined) setWireless(payload.wireless);


          if (!payload.demo_mode) {
            // Purge demo items if in live hardware mode
            setTelemetryHistory((prev) => prev.filter((r) => !r.is_demo));
          }

          if (!isPausedRef.current) {
            if (payload.wireless) {
              const timeStr = payload.wireless.utc_timestamp
                ? new Date(payload.wireless.utc_timestamp).toLocaleTimeString()
                : new Date().toLocaleTimeString();
              setFlowHistory((prev) => {
                const entry = {
                  timeStr,
                  second_index: payload.wireless!.packet_sequence,
                  flow_in_lpm: payload.wireless!.flow_in_lpm,
                  flow_out_lpm: payload.wireless!.flow_out_lpm,
                  flow_diff_lpm: payload.wireless!.flow_diff_lpm
                };
                const updated = [...prev, entry];
                return updated.length > 500 ? updated.slice(updated.length - 500) : updated;
              });
            } else if (payload.flow) {
              const timeStr = new Date().toLocaleTimeString();
              setFlowHistory((prev) => {
                const entry = {
                  timeStr,
                  second_index: payload.flow!.esp32_ms ? Math.floor(payload.flow!.esp32_ms / 1000) : prev.length,
                  flow_in_lpm: payload.flow!.flow_in_lpm,
                  flow_out_lpm: payload.flow!.flow_out_lpm,
                  flow_diff_lpm: payload.flow!.flow_diff_lpm
                };
                const updated = [...prev, entry];
                return updated.length > 500 ? updated.slice(updated.length - 500) : updated;
              });
            }
          }

          if (payload.telemetry) {
            if (!isPausedRef.current) {
              setLatestTelemetry(payload.telemetry);
              setTelemetryHistory((prev) => {
                const filtered = payload.demo_mode ? prev : prev.filter((r) => !r.is_demo);
                const updated = [...filtered, payload.telemetry!];
                return updated.length > 1000 ? updated.slice(updated.length - 1000) : updated;
              });
            }
          } else {
            setLatestTelemetry(null);
          }
        }
      } catch (err) {
        console.error('[WS PARSE ERROR]', err);
      }
    };

    ws.onclose = () => {
      if (isUnmountedRef.current) return;
      setIsConnected(false);
      console.warn('[WS CONTEXT] Closed. Retrying in 3s...');
      reconnectTimerRef.current = setTimeout(() => {
        if (!isUnmountedRef.current) {
          connectWebSocket();
        }
      }, 3000);
    };

    ws.onerror = (err) => {
      console.error('[WS CONTEXT ERROR]', err);
      ws.close();
    };

    wsRef.current = ws;
  }, []);

  useEffect(() => {
    isUnmountedRef.current = false;
    connectWebSocket();

    return () => {
      isUnmountedRef.current = true;
      if (reconnectTimerRef.current) {
        clearTimeout(reconnectTimerRef.current);
        reconnectTimerRef.current = null;
      }
      if (wsRef.current) {
        wsRef.current.onclose = null;
        wsRef.current.onerror = null;
        wsRef.current.close();
        wsRef.current = null;
      }
    };
  }, [connectWebSocket]);

  const toggleDemoMode = async (enabled: boolean, scenario: string = 'normal') => {
    try {
      await api.setMode(enabled, scenario);
      setDemoMode(enabled);
      setDemoScenarioState(scenario as any);
    } catch (e) {
      console.error('Failed to set demo mode', e);
    }
  };

  const setDemoScenario = async (scenario: "normal" | "pump_disturbance" | "confirmed_leak") => {
    try {
      await api.setMode(demoMode, scenario);
      setDemoScenarioState(scenario);

      if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
        wsRef.current.send(JSON.stringify({ action: 'set_scenario', scenario }));
      }
    } catch (e) {
      console.error('Failed to set demo scenario', e);
    }
  };

  const sendHardwareCommand = async (command: string, parameter?: number, confirmNoLeak?: boolean) => {
    return api.sendHardwareCommand(command, parameter, confirmNoLeak);
  };

  const clearHistory = () => {
    setTelemetryHistory([]);
    setFlowHistory([]);
  };

  return (
    <TelemetryContext.Provider
      value={{
        isConnected,
        systemState,
        demoMode,
        demoScenario,
        latestTelemetry,
        baseline,
        currentWindowSec,
        latestDecision,
        diagnostics,
        gps,
        localization,
        adc,
        flow,
        wireless,
        telemetryHistory,
        flowHistory,
        isPaused,
        firebaseStatus,
        setPaused: setIsPaused,
        toggleDemoMode,
        setDemoScenario,
        sendHardwareCommand,
        clearHistory
      }}
    >
      {children}
    </TelemetryContext.Provider>
  );
};

export const useTelemetry = () => {
  const context = useContext(TelemetryContext);
  if (!context) {
    throw new Error('useTelemetry must be used within a TelemetryProvider');
  }
  return context;
};

