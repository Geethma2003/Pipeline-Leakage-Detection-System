import React from 'react';
import { SettingsHardwareView } from '../components/settings/SettingsHardwareView';

export const SettingsView: React.FC = () => {
  return (
    <div className="space-y-6 animate-fadeIn">
      <div>
        <h1 className="text-2xl font-extrabold text-slate-100 font-outfit tracking-tight">
          Settings & Hardware Diagnostics
        </h1>
        <p className="text-xs text-slate-400 mt-1">
          ESP32 USB Serial Port connection, baud rate, baseline recalibration ('B' command), and physical pipe specifications
        </p>
      </div>

      <SettingsHardwareView />
    </div>
  );
};
