import {
  ExperimentAnalysisResponse,
  EventRecord,
  TelemetryRecord,
  SerialPortInfo,
  ExperimentMetrics,
  GPSData,
  FlowTelemetry
} from '../types';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

export const api = {
  async setMode(demoMode: boolean, scenario: string = 'normal'): Promise<any> {
    const res = await fetch(`${API_BASE_URL}/api/mode`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ demo_mode: demoMode, scenario })
    });
    return res.json();
  },

  async sendHardwareCommand(command: string, parameter?: number, confirmNoLeak?: boolean): Promise<any> {
    const res = await fetch(`${API_BASE_URL}/api/command`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ command, parameter, confirm_no_leak: confirmNoLeak })
    });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || 'Hardware command failed');
    }
    return res.json();
  },

  async getTelemetryHistory(limit: number = 300): Promise<TelemetryRecord[]> {
    const res = await fetch(`${API_BASE_URL}/api/telemetry/history?limit=${limit}`);
    return res.json();
  },

  async getEvents(limit: number = 100, status?: string): Promise<EventRecord[]> {
    const url = status ? `${API_BASE_URL}/api/events?limit=${limit}&status=${encodeURIComponent(status)}` : `${API_BASE_URL}/api/events?limit=${limit}`;
    const res = await fetch(url);
    return res.json();
  },

  async updateEventStatus(eventId: number, operatorStatus: string, note?: string): Promise<any> {
    const res = await fetch(`${API_BASE_URL}/api/events/${eventId}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ operator_status: operatorStatus, operator_note: note })
    });
    return res.json();
  },

  async exportEventsCsv(): Promise<void> {
    window.open(`${API_BASE_URL}/api/events/export/csv`, '_blank');
  },

  async getDefaultExperiments(): Promise<ExperimentAnalysisResponse> {
    const res = await fetch(`${API_BASE_URL}/api/experiments/default`);
    return res.json();
  },

  async uploadExperimentCsv(file: File): Promise<ExperimentMetrics> {
    const formData = new FormData();
    formData.append('file', file);
    const res = await fetch(`${API_BASE_URL}/api/experiments/upload`, {
      method: 'POST',
      body: formData
    });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || 'Upload failed');
    }
    return res.json();
  },

  async getSerialPorts(): Promise<SerialPortInfo[]> {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 5000);
    try {
      const res = await fetch(`${API_BASE_URL}/api/settings/ports`, { signal: controller.signal });
      clearTimeout(timer);
      return res.json();
    } catch (e) {
      clearTimeout(timer);
      return [];
    }
  },

  async getSerialStatus(): Promise<any> {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 3000);
    try {
      const res = await fetch(`${API_BASE_URL}/api/settings/status`, { signal: controller.signal });
      clearTimeout(timer);
      return res.json();
    } catch (e) {
      clearTimeout(timer);
      return { port: 'NOT_CONNECTED', connected: false, connection_state: 'DISCONNECTED' };
    }
  },

  async connectSerial(port: string, baudRate: number = 115200): Promise<any> {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 8000);
    try {
      const res = await fetch(`${API_BASE_URL}/api/settings/connect`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ port, baud_rate: baudRate }),
        signal: controller.signal
      });
      clearTimeout(timer);
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || 'Connection failed');
      }
      return res.json();
    } catch (e: any) {
      clearTimeout(timer);
      if (e.name === 'AbortError') {
        throw new Error('Connection request timed out after 8 seconds.');
      }
      throw e;
    }
  },

  async disconnectSerial(): Promise<any> {
    const res = await fetch(`${API_BASE_URL}/api/settings/disconnect`, {
      method: 'POST'
    });
    return res.json();
  },

  async getFirebaseStatus(): Promise<{ initialized: boolean; online: boolean; project_id: string; last_error?: string | null }> {
    try {
      const res = await fetch(`${API_BASE_URL}/api/firebase/status`);
      return res.json();
    } catch (e) {
      return { initialized: false, online: false, project_id: 'aquaguard-pipeline', last_error: 'Backend Unreachable' };
    }
  },

  async getFirestoreWindowReports(limit: number = 50): Promise<any[]> {
    const res = await fetch(`${API_BASE_URL}/api/firebase/window_reports?limit=${limit}`);
    return res.json();
  },

  async getGPSLocation(): Promise<GPSData> {
    const res = await fetch(`${API_BASE_URL}/api/gps/location`);
    return res.json();
  },

  async getGPSDebugInfo(): Promise<any> {
    const res = await fetch(`${API_BASE_URL}/api/debug/gps`);
    return res.json();
  },

  async getFlowTelemetry(): Promise<FlowTelemetry> {
    const res = await fetch(`${API_BASE_URL}/api/serial/flow`);
    return res.json();
  },

  async getWirelessLatest(): Promise<any> {
    const res = await fetch(`${API_BASE_URL}/api/wireless/latest`);
    return res.json();
  },

  async getWirelessHistory(limit: number = 100): Promise<any[]> {
    const res = await fetch(`${API_BASE_URL}/api/wireless/history?limit=${limit}`);
    return res.json();
  }
};

