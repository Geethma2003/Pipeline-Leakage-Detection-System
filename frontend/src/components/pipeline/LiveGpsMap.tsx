import React, { useEffect, useRef, useState } from 'react';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import { useTelemetry } from '../../context/TelemetryContext';
import { MapPin, Navigation, ExternalLink, Satellite, ShieldCheck, AlertTriangle, RefreshCw, Info, Compass } from 'lucide-react';

// Neutral geographic reference view for the Leaflet container when no live GPS coordinates exist.
// This is strictly a camera center for rendering map tiles and spatial orientation, NEVER the pipeline position.
const REFERENCE_MAP_CENTER: [number, number] = [6.9271, 79.8612]; // Sri Lanka Western Province overview
const REFERENCE_ZOOM = 11;

export const LiveGpsMap: React.FC = () => {
  const { gps, latestTelemetry, demoMode } = useTelemetry();
  const mapContainerRef = useRef<HTMLDivElement | null>(null);
  const mapInstanceRef = useRef<L.Map | null>(null);
  const markerRef = useRef<L.Marker | null>(null);
  const circleRef = useRef<L.Circle | null>(null);

  const [isCentered, setIsCentered] = useState<boolean>(true);

  // Check if real GPS hardware has a valid live fix:
  // - Not running synthetic demo mode
  // - gps object present
  // - latitude and longitude are valid numbers
  // - coordinates are NOT (0, 0)
  // - fix_status is 'FIX'
  // - is_stale is false
  const hasValidHardwareFix = Boolean(
    !demoMode &&
    gps &&
    gps.latitude !== null &&
    gps.longitude !== null &&
    typeof gps.latitude === 'number' &&
    typeof gps.longitude === 'number' &&
    !(gps.latitude === 0 && gps.longitude === 0) &&
    gps.fix_status === 'FIX' &&
    !gps.is_stale
  );

  const isDemoGps = Boolean(
    demoMode &&
    gps &&
    gps.latitude !== null &&
    gps.longitude !== null &&
    !(gps.latitude === 0 && gps.longitude === 0)
  );

  const hasValidFix = hasValidHardwareFix || isDemoGps;

  // Real coordinates — strictly null when hardware GPS fix is unavailable
  const currentLat: number | null = hasValidHardwareFix
    ? gps!.latitude!
    : (isDemoGps ? gps!.latitude! : null);

  const currentLng: number | null = hasValidHardwareFix
    ? gps!.longitude!
    : (isDemoGps ? gps!.longitude! : null);

  const fixStatus = demoMode
    ? 'SIMULATED DEMO'
    : (gps?.fix_status || (hasValidHardwareFix ? 'FIX' : 'NO_FIX'));
  const isStale = (!demoMode && gps?.is_stale) || false;

  // Format last updated time
  const lastUpdatedStr = gps?.last_updated && gps.last_updated > 0
    ? new Date(gps.last_updated * 1000).toLocaleTimeString()
    : null;

  // Initialize Leaflet Map
  useEffect(() => {
    if (!mapContainerRef.current) return;

    if (!mapInstanceRef.current) {
      const initialCenter = (hasValidFix && currentLat !== null && currentLng !== null)
        ? [currentLat, currentLng] as [number, number]
        : REFERENCE_MAP_CENTER;
      const initialZoom = hasValidFix ? 16 : REFERENCE_ZOOM;

      const map = L.map(mapContainerRef.current, {
        center: initialCenter,
        zoom: initialZoom,
        zoomControl: false,
        attributionControl: false
      });

      L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        maxZoom: 19,
        attribution: '&copy; OpenStreetMap contributors'
      }).addTo(map);

      L.control.zoom({ position: 'topright' }).addTo(map);

      mapInstanceRef.current = map;
    }

    return () => {
      if (mapInstanceRef.current) {
        mapInstanceRef.current.remove();
        mapInstanceRef.current = null;
      }
    };
  }, []);

  // Update Marker & Circle position when authentic coordinates arrive, or remove when fix is lost
  useEffect(() => {
    const map = mapInstanceRef.current;
    if (!map) return;

    // RULE: If GPS fix is unavailable, do NOT show a false live marker. Remove any existing marker.
    if (!hasValidFix || currentLat === null || currentLng === null) {
      if (markerRef.current) {
        markerRef.current.remove();
        markerRef.current = null;
      }
      if (circleRef.current) {
        circleRef.current.remove();
        circleRef.current = null;
      }
      return;
    }

    const latLng: [number, number] = [currentLat, currentLng];

    // Create custom SVG DivIcon for authentic station marker
    const iconHtml = `
      <div class="relative flex items-center justify-center w-10 h-10">
        <span class="absolute inline-flex w-full h-full rounded-full ${isDemoGps ? 'bg-purple-400/40' : 'bg-emerald-400/40'} animate-ping"></span>
        <div class="relative w-8 h-8 rounded-full ${isDemoGps ? 'bg-gradient-to-tr from-purple-600 to-indigo-500 border-2 border-purple-200 shadow-purple-500/50' : 'bg-gradient-to-tr from-emerald-600 to-cyan-500 border-2 border-emerald-100 shadow-emerald-500/50'} flex items-center justify-center shadow-lg">
          <svg class="w-4 h-4 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z"/>
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 11a3 3 0 11-6 0 3 3 0 016 0z"/>
          </svg>
        </div>
      </div>
    `;

    const customIcon = L.divIcon({
      html: iconHtml,
      className: 'custom-gps-marker',
      iconSize: [40, 40],
      iconAnchor: [20, 20],
      popupAnchor: [0, -20]
    });

    const popupContent = `
      <div style="font-family: system-ui, sans-serif; min-width: 250px; padding: 4px;">
        <div style="font-weight: 800; color: ${isDemoGps ? '#9333ea' : '#059669'}; font-size: 14px; margin-bottom: 4px;">
          📍 ${isDemoGps ? 'AquaGuard Test Facility (Demo Simulation)' : 'AquaGuard Live Pipeline Station'}
        </div>
        <div style="font-size: 11px; color: #475569; margin-bottom: 8px; line-height: 1.3;">
          ${isDemoGps ? 'Synthetic GPS testbed coordinates' : 'Authentic Arduino Uno NEO-6M Live Telemetry'}
        </div>
        <div style="background-color: #f1f5f9; padding: 8px; border-radius: 6px; font-size: 11px; line-height: 1.6;">
          <div><b>Latitude:</b> ${currentLat.toFixed(6)}°</div>
          <div><b>Longitude:</b> ${currentLng.toFixed(6)}°</div>
          <div><b>Satellites:</b> ${gps ? gps.satellites : 0}</div>
          <div><b>HDOP:</b> ${gps && gps.hdop < 90 ? gps.hdop.toFixed(1) : '--'}</div>
          <div><b>Status:</b> ${fixStatus}</div>
          ${lastUpdatedStr ? `<div><b>Last Updated:</b> ${lastUpdatedStr}</div>` : ''}
          <div style="margin-top: 4px; padding-top: 4px; border-top: 1px solid #cbd5e1;">
            <div><b>Sensor 1 (A0 @ 0.0m):</b> ${latestTelemetry ? latestTelemetry.s1_rms.toFixed(2) : '0.00'} RMS</div>
            <div><b>Sensor 2 (A1 @ 2.0m):</b> ${latestTelemetry ? latestTelemetry.s2_rms.toFixed(2) : '0.00'} RMS</div>
          </div>
        </div>
      </div>
    `;

    if (!markerRef.current) {
      const marker = L.marker(latLng, { icon: customIcon }).addTo(map);
      marker.bindPopup(popupContent);
      markerRef.current = marker;
    } else {
      markerRef.current.setLatLng(latLng);
      markerRef.current.setIcon(customIcon);
      markerRef.current.setPopupContent(popupContent);
    }

    if (!circleRef.current) {
      const circle = L.circle(latLng, {
        radius: 15,
        color: isDemoGps ? '#a855f7' : '#10b981',
        fillColor: isDemoGps ? '#a855f7' : '#10b981',
        fillOpacity: 0.15,
        weight: 1.5
      }).addTo(map);
      circleRef.current = circle;
    } else {
      circleRef.current.setLatLng(latLng);
      circleRef.current.setStyle({
        color: isDemoGps ? '#a855f7' : '#10b981',
        fillColor: isDemoGps ? '#a855f7' : '#10b981'
      });
    }

    if (isCentered) {
      map.setView(latLng, 16);
    }
  }, [currentLat, currentLng, hasValidFix, isDemoGps, fixStatus, latestTelemetry, isCentered, lastUpdatedStr]);

  const handleRecenter = () => {
    if (!mapInstanceRef.current) return;
    if (hasValidFix && currentLat !== null && currentLng !== null) {
      mapInstanceRef.current.setView([currentLat, currentLng], 16);
      setIsCentered(true);
    } else {
      mapInstanceRef.current.setView(REFERENCE_MAP_CENTER, REFERENCE_ZOOM);
      setIsCentered(true);
    }
  };

  const handleOpenGoogleMaps = () => {
    if (hasValidFix && currentLat !== null && currentLng !== null) {
      const url = `https://www.google.com/maps?q=${currentLat},${currentLng}`;
      window.open(url, '_blank');
    }
  };

  return (
    <div className="bg-navy-900/90 border border-slate-800 rounded-2xl p-5 shadow-xl backdrop-blur-md space-y-4">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <div className={`p-2.5 rounded-xl ${
            hasValidHardwareFix
              ? 'bg-emerald-500/10 border border-emerald-500/30 text-emerald-400'
              : isDemoGps
              ? 'bg-purple-500/10 border border-purple-500/30 text-purple-400'
              : 'bg-amber-500/10 border border-amber-500/30 text-amber-400'
          }`}>
            {hasValidFix ? <MapPin className="w-5 h-5" /> : <Compass className="w-5 h-5" />}
          </div>
          <div>
            <h2 className="text-lg font-bold text-slate-100 font-outfit tracking-tight flex items-center gap-2">
              Live GPS & Sensor Location
            </h2>
            <p className="text-xs text-slate-400">
              {hasValidHardwareFix
                ? 'Authentic NEO-6M Hardware GPS Position & Pipeline Station'
                : isDemoGps
                ? 'Simulated Pipeline Testbed Location (Demo Mode Active)'
                : 'Reference Map View (No Live Pipeline Coordinates Available)'}
            </p>
          </div>
        </div>

        {/* Status Badges */}
        <div className="flex flex-wrap items-center gap-2">
          {/* Fix Status Badge */}
          <span
            className={`px-3 py-1 rounded-lg text-xs font-semibold flex items-center gap-1.5 border ${
              demoMode
                ? 'bg-purple-500/10 border-purple-500/30 text-purple-400'
                : hasValidHardwareFix
                ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-400'
                : fixStatus === 'STALE' || isStale
                ? 'bg-amber-500/10 border-amber-500/30 text-amber-400'
                : 'bg-slate-800 border-slate-700 text-slate-400'
            }`}
          >
            {hasValidHardwareFix ? (
              <ShieldCheck className="w-3.5 h-3.5 text-emerald-400" />
            ) : fixStatus === 'STALE' || isStale ? (
              <AlertTriangle className="w-3.5 h-3.5 text-amber-400" />
            ) : demoMode ? (
              <Satellite className="w-3.5 h-3.5 text-purple-400" />
            ) : (
              <RefreshCw className="w-3.5 h-3.5 animate-spin text-amber-400" />
            )}
            {demoMode
              ? 'SIMULATED GPS (DEMO)'
              : isStale
              ? 'STALE GPS FIX'
              : hasValidHardwareFix
              ? '3D HARDWARE FIX'
              : 'NO SATELLITE FIX'}
          </span>

          {/* Satellites Badge */}
          <span className="px-2.5 py-1 rounded-lg bg-slate-800 border border-slate-700 text-xs text-slate-300 font-mono flex items-center gap-1.5">
            <Satellite className="w-3.5 h-3.5 text-cyan-400" />
            {gps ? gps.satellites : 0} Sats
          </span>

          {/* HDOP Badge */}
          <span className="px-2.5 py-1 rounded-lg bg-slate-800 border border-slate-700 text-xs text-slate-300 font-mono">
            HDOP: {gps && gps.hdop < 90 ? gps.hdop.toFixed(1) : '--'}
          </span>

          {/* Last Updated Badge */}
          {lastUpdatedStr && hasValidFix && (
            <span className="px-2.5 py-1 rounded-lg bg-slate-800/80 border border-slate-700/80 text-[11px] text-slate-400 font-mono">
              Updated: {lastUpdatedStr}
            </span>
          )}
        </div>
      </div>

      {/* Map Container */}
      <div className="relative w-full h-[320px] rounded-xl overflow-hidden border border-slate-700/60 shadow-inner group">
        <div ref={mapContainerRef} className="w-full h-full z-10" />

        {/* GPS Unavailable Overlay Banner */}
        {!hasValidFix && (
          <div className="absolute inset-0 z-20 flex flex-col items-center justify-center p-4 bg-navy-950/40 backdrop-blur-[2px] pointer-events-none">
            <div className="bg-navy-950/95 border border-amber-500/40 rounded-2xl p-5 max-w-md shadow-2xl backdrop-blur-md text-center space-y-2.5 pointer-events-auto">
              <div className="flex items-center justify-center gap-2 text-amber-400 font-bold font-mono tracking-wide text-xs uppercase">
                <AlertTriangle className="w-4 h-4 shrink-0 animate-pulse text-amber-400" />
                GPS LOCATION UNAVAILABLE — WAITING FOR SATELLITES
              </div>
              <p className="text-xs text-slate-300 leading-relaxed">
                The transmitter NEO-6M GPS module is currently acquiring satellites. No live pipeline marker is displayed until authentic coordinates arrive from the hardware.
              </p>
              <div className="flex items-center justify-center gap-4 pt-1 text-[11px] text-slate-400 font-mono border-t border-slate-800/80">
                <span>Satellites: <b className="text-slate-200">{gps?.satellites ?? 0}</b></span>
                <span>HDOP: <b className="text-slate-200">{gps && gps.hdop < 90 ? gps.hdop.toFixed(1) : '--'}</b></span>
                <span>Fix Status: <b className="text-amber-400">{gps?.fix_status ?? 'NO_FIX'}</b></span>
              </div>
              <div className="text-[10px] text-slate-500 italic">
                Reference map view rendered for spatial orientation. Never displaying hardcoded fake coordinates.
              </div>
            </div>
          </div>
        )}

        {/* Floating Map Controls overlay */}
        <div className="absolute bottom-3 right-3 z-20 flex items-center gap-2">
          <button
            onClick={handleRecenter}
            className="px-3 py-1.5 rounded-lg bg-navy-950/90 hover:bg-navy-900 border border-cyan-500/30 text-cyan-400 hover:text-cyan-300 text-xs font-semibold flex items-center gap-1.5 shadow-lg transition-all"
          >
            <Navigation className="w-3.5 h-3.5" />
            {hasValidFix ? 'Center Station' : 'Reset View'}
          </button>
          {hasValidFix && (
            <button
              onClick={handleOpenGoogleMaps}
              className="px-3 py-1.5 rounded-lg bg-navy-950/90 hover:bg-navy-900 border border-slate-700 text-slate-300 hover:text-white text-xs font-semibold flex items-center gap-1.5 shadow-lg transition-all"
            >
              <ExternalLink className="w-3.5 h-3.5" />
              Google Maps
            </button>
          )}
        </div>

        {/* Live Coordinates Bar */}
        <div className="absolute top-3 left-3 z-20 px-3 py-1.5 rounded-lg bg-navy-950/90 border border-slate-800 text-xs font-mono text-slate-200 shadow-md flex items-center gap-2">
          {hasValidHardwareFix && currentLat !== null && currentLng !== null ? (
            <span className="text-emerald-300 font-semibold flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
              {currentLat.toFixed(6)}°, {currentLng.toFixed(6)}°
            </span>
          ) : isDemoGps && currentLat !== null && currentLng !== null ? (
            <span className="text-purple-300 font-semibold flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-full bg-purple-400"></span>
              [DEMO] {currentLat.toFixed(6)}°, {currentLng.toFixed(6)}°
            </span>
          ) : isStale ? (
            <span className="text-amber-400 font-semibold flex items-center gap-1.5">
              <AlertTriangle className="w-3.5 h-3.5 text-amber-400 shrink-0" />
              GPS SIGNAL LOST — STALE DATA
            </span>
          ) : (
            <span className="text-amber-400 font-semibold flex items-center gap-1.5">
              <AlertTriangle className="w-3.5 h-3.5 text-amber-400 shrink-0" />
              GPS LOCATION UNAVAILABLE — WAITING FOR SATELLITES
            </span>
          )}
        </div>
      </div>

      {/* Sensor Spacing & GPS Accuracy Notice */}
      <div className="p-3.5 rounded-xl bg-slate-900/60 border border-slate-800 text-xs text-slate-300 flex items-start gap-2.5">
        <Info className="w-4 h-4 text-cyan-400 shrink-0 mt-0.5" />
        <div className="space-y-1">
          <div className="font-semibold text-slate-200">
            Sensor Installation Spacing & Macro GPS Location
          </div>
          <p className="text-slate-400 text-[11px] leading-relaxed">
            Piezoelectric Vibration Sensors Sensor 1 (A0 @ 0.0m) and Sensor 2 (A1 @ 2.0m) are installed 2.0 meters apart on the physical steel pipeline. {hasValidHardwareFix ? 'Consumer GPS precision (~2–5m) associates both sensor nodes with this common live station position.' : 'Live GPS coordinates are currently unavailable. The system does not substitute demo or hardcoded coordinates as the actual pipeline location.'}
          </p>
        </div>
      </div>
    </div>
  );
};
