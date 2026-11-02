import { useState, useEffect, useRef } from 'react';
import type { Station } from './FindStations';
import { AccessDenied } from './AccessDenied';
import { OperatorAuth } from './OperatorAuth';

export interface VideoAnalysis {
  id: number;
  station_id: number;
  operator_id: number;
  filename: string;
  file_size_bytes: number;
  status: 'PENDING' | 'PROCESSING' | 'COMPLETED' | 'FAILED' | 'INSUFFICIENT_DATA';
  error_message: string | null;
  roi_config: string | null;
  fps: number;
  total_frames: number;
  processed_frames: number;
  duration_seconds: number;
  model_name: string;
  vehicle_classes_detected: Record<string, number>;
  total_vehicles_detected: number;
  peak_queue_count: number;
  average_queue_count: number;
  average_waiting_time_seconds: number | null;
  estimated_queue_wait_minutes?: number | null;
  waiting_time_display?: string | null;
  analytics_timeline: Array<{
    time_sec: number;
    queue_count_roi: number;
    total_detected: number;
    estimated_queue_wait_minutes?: number;
    waiting_time_display?: string;
    vehicle_classes?: Record<string, number>;
  }>;
  has_processed_video: boolean;
  created_at: string;
  completed_at: string | null;
  analysis_type: string;
  disclaimer: string;
}

export interface LiveCameraStatus {
  station_id: number;
  station_name?: string | null;
  camera_name?: string | null;
  camera_type: string;
  connection_status: 'DISCONNECTED' | 'CONNECTING' | 'CONNECTED' | 'ERROR' | 'RECONNECTING';
  is_streaming: boolean;
  last_error: string | null;
  current_queue_count: number | null;
  current_vehicles_total: number | null;
  queue_level?: 'LOW' | 'MODERATE' | 'HIGH' | 'CRITICAL' | 'UNAVAILABLE';
  queue_capacity?: number | null;
  waiting_time_seconds: number | null;
  estimated_queue_wait_minutes?: number | null;
  waiting_time_display?: string | null;
  waiting_time_status: string;
  last_frame_timestamp: string | null;
  frame_sampling_rate: number;
  measured_fps?: number | null;
  model_name?: string;
  roi_config: string | null;
  measurement_window_seconds: number;
  stream_url_masked: string;
  stream_health?: string;
  active_track_ids?: number[];
  active_queue_track_ids?: number[];
  class_breakdown?: Record<string, number>;
  frame_number?: number | null;
  model_classes?: string[];
  tractor_detected?: boolean;
  model_supports_tractor?: boolean;
  cumulative_queue_vehicles_count?: number | null;
}

export interface LiveQueueSnapshot {
  id: number;
  station_id: number;
  queue_count: number;
  total_vehicles_detected: number;
  waiting_time_seconds: number | null;
  measured_at: string;
}

export interface CameraTestResult {
  success: boolean;
  message: string;
  camera_type: string;
  resolution?: string | null;
  fps?: number | null;
  error_detail?: string | null;
}

interface OperatorPortalProps {
  token: string | null;
  username: string | null;
  role: string | null;
  onAuthSuccess: (token: string, username: string, role: string) => void;
  onLogout: () => void;
  onReturnToUserFlow: () => void;
}

export function OperatorPortal({
  token,
  username,
  role,
  onAuthSuccess,
  onLogout,
  onReturnToUserFlow,
}: OperatorPortalProps) {
  // Navigation State
  const [operatorTab, setOperatorTab] = useState<'stations' | 'cctv' | 'slots'>('stations');
  const [cctvMode, setCctvMode] = useState<'live' | 'recorded'>('live');

  // Station Form
  const [stationName, setStationName] = useState('');
  const [stationAddress, setStationAddress] = useState('');
  const [stationLat, setStationLat] = useState('18.5204');
  const [stationLng, setStationLng] = useState('73.8567');
  const [queueCapacity, setQueueCapacity] = useState('20');
  const [pumpCount, setPumpCount] = useState('4');
  const [slotDuration, setSlotDuration] = useState('15');
  const [maxPerSlot, setMaxPerSlot] = useState('4');
  const [stationMsg, setStationMsg] = useState<string | null>(null);

  // Managed Station Selection
  const [stations, setStations] = useState<Station[]>([]);
  const [selectedStationId, setSelectedStationId] = useState<number | null>(null);
  const selectedStation = stations.find((s) => s.id === selectedStationId);

  // Phase 4 Live Camera State
  const [cameraName, setCameraName] = useState('Main Forecourt Camera');
  const [cameraType, setCameraType] = useState('rtsp');
  const [cameraStreamUrl, setCameraStreamUrl] = useState('');
  const [cameraMsg, setCameraMsg] = useState<string | null>(null);
  const [liveStatus, setLiveStatus] = useState<LiveCameraStatus | null>(null);
  const [liveHistory, setLiveHistory] = useState<LiveQueueSnapshot[]>([]);
  const [isConnecting, setIsConnecting] = useState(false);
  const [isDisconnecting, setIsDisconnecting] = useState(false);
  const [isTestingStream, setIsTestingStream] = useState(false);
  const [testResult, setTestResult] = useState<CameraTestResult | null>(null);
  const [frameSamplingRate, setFrameSamplingRate] = useState<number>(5);
  const [liveRoiX1, setLiveRoiX1] = useState(10);
  const [liveRoiY1, setLiveRoiY1] = useState(20);
  const [liveRoiX2, setLiveRoiX2] = useState(90);
  const [liveRoiY2, setLiveRoiY2] = useState(90);
  const [feedTimestamp, setFeedTimestamp] = useState<number>(Date.now());
  const [imageError, setImageError] = useState(false);
  const [streamDisplayMode, setStreamDisplayMode] = useState<'mjpeg' | 'snapshot'>('mjpeg');

  // Phase 3 Recorded Video Analysis State
  const [analyses, setAnalyses] = useState<VideoAnalysis[]>([]);
  const [selectedAnalysisId, setSelectedAnalysisId] = useState<number | null>(null);
  const [videoFile, setVideoFile] = useState<File | null>(null);
  const [uploadingVideo, setUploadingVideo] = useState(false);
  const [videoUploadMsg, setVideoUploadMsg] = useState<string | null>(null);
  const [videoError, setVideoError] = useState<string | null>(null);
  const [recordedRoiX1, setRecordedRoiX1] = useState(10);
  const [recordedRoiY1, setRecordedRoiY1] = useState(20);
  const [recordedRoiX2, setRecordedRoiX2] = useState(90);
  const [recordedRoiY2, setRecordedRoiY2] = useState(90);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Synchronized Video Analysis Playback State
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const animFrameRef = useRef<number | null>(null);
  const [playbackTime, setPlaybackTime] = useState<number>(0);
  const [isPlaying, setIsPlaying] = useState<boolean>(false);
  const [hasStarted, setHasStarted] = useState<boolean>(false);

  // Slots Form
  const [slotStartTime, setSlotStartTime] = useState('');
  const [slotEndTime, setSlotEndTime] = useState('');
  const [slotCapacity, setSlotCapacity] = useState('4');
  const [slotMsg, setSlotMsg] = useState<string | null>(null);

  // Load registered stations
  const loadStations = () => {
    fetch('http://127.0.0.1:8000/api/stations')
      .then((res) => res.json())
      .then((data: Station[]) => {
        setStations(data);
        if (data.length > 0 && selectedStationId === null) {
          setSelectedStationId(data[0].id);
        }
      })
      .catch(() => setStations([]));
  };

  // Load camera configuration
  const loadCameraConfig = async (stId: number) => {
    if (!token) return;
    try {
      const res = await fetch(`http://127.0.0.1:8000/api/stations/${stId}/camera`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        const data = await res.json();
        if (data.camera_name) setCameraName(data.camera_name);
        setCameraType(data.camera_type || 'rtsp');
        setFrameSamplingRate(data.frame_sampling_rate || 5);
        if (data.detection_roi) {
          try {
            const parsed = JSON.parse(data.detection_roi);
            if (parsed.x1 !== undefined) setLiveRoiX1(Math.round(parsed.x1 * 100));
            if (parsed.y1 !== undefined) setLiveRoiY1(Math.round(parsed.y1 * 100));
            if (parsed.x2 !== undefined) setLiveRoiX2(Math.round(parsed.x2 * 100));
            if (parsed.y2 !== undefined) setLiveRoiY2(Math.round(parsed.y2 * 100));
          } catch {
            // ignore JSON parse error
          }
        }
      }
    } catch {
      // ignore
    }
  };

  // Load live camera telemetry
  const loadLiveStatus = async (stId: number) => {
    if (!token) return;
    try {
      const res = await fetch(`http://127.0.0.1:8000/api/stations/${stId}/camera/live-status`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        const data = await res.json();
        setLiveStatus(data);
      }
    } catch {
      // ignore
    }
  };

  // Load recent live queue snapshots
  const loadLiveHistory = async (stId: number) => {
    try {
      const res = await fetch(`http://127.0.0.1:8000/api/stations/${stId}/queue-history?limit=15`);
      if (res.ok) {
        const data = await res.json();
        setLiveHistory(data);
      }
    } catch {
      setLiveHistory([]);
    }
  };

  // Load Phase 3 recorded analyses
  const loadAnalyses = (stId: number) => {
    if (!token) return;
    fetch(`http://127.0.0.1:8000/api/stations/${stId}/video-analyses`, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then((res) => (res.ok ? res.json() : []))
      .then((data: VideoAnalysis[]) => {
        setAnalyses(data);
        if (data.length > 0 && selectedAnalysisId === null) {
          setSelectedAnalysisId(data[0].id);
        }
      })
      .catch(() => setAnalyses([]));
  };

  useEffect(() => {
    if (token && role && role !== 'user') {
      loadStations();
    }
  }, [token, role]);

  useEffect(() => {
    if (selectedStationId && token && role !== 'user') {
      loadCameraConfig(selectedStationId);
      loadLiveStatus(selectedStationId);
      loadLiveHistory(selectedStationId);
      loadAnalyses(selectedStationId);
    }
  }, [selectedStationId, token, role]);

  // Periodic fast polling for live stream telemetry and processing jobs
  useEffect(() => {
    if (!selectedStationId || !token || role === 'user') return;

    const interval = setInterval(() => {
      loadLiveStatus(selectedStationId);

      // Refresh history if camera connected
      if (liveStatus?.connection_status === 'CONNECTED') {
        loadLiveHistory(selectedStationId);
        // In snapshot polling mode, refresh feedTimestamp every cycle to pull fresh frame
        if (streamDisplayMode === 'snapshot') {
          setFeedTimestamp(Date.now());
        }
      }

      // Check if recorded analysis is pending
      const hasActiveRecorded = analyses.some(
        (a) => a.status === 'PENDING' || a.status === 'PROCESSING'
      );
      if (hasActiveRecorded) {
        loadAnalyses(selectedStationId);
      }
    }, 1000);

    return () => clearInterval(interval);
  }, [selectedStationId, token, role, liveStatus?.connection_status, streamDisplayMode, analyses]);

  // Auto-recovery: If camera is reported CONNECTED but image experienced a transport drop, auto-retry after 2s
  useEffect(() => {
    if (imageError && liveStatus?.connection_status === 'CONNECTED') {
      const retryTimer = setTimeout(() => {
        setImageError(false);
        setFeedTimestamp(Date.now());
      }, 2000);
      return () => clearTimeout(retryTimer);
    }
  }, [imageError, liveStatus?.connection_status]);

  // Access Control: Block standard customers
  if (role === 'user') {
    return (
      <AccessDenied
        username={username}
        role={role}
        onReturnToUserFlow={onReturnToUserFlow}
      />
    );
  }

  // Not signed in as operator
  if (!token) {
    return (
      <OperatorAuth
        onAuthSuccess={onAuthSuccess}
        onSwitchToUserLogin={onReturnToUserFlow}
      />
    );
  }

  // --- Handlers ---

  const handleCreateStation = async (e: React.FormEvent) => {
    e.preventDefault();
    setStationMsg(null);
    try {
      const res = await fetch('http://127.0.0.1:8000/api/stations', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          name: stationName,
          address: stationAddress,
          latitude: parseFloat(stationLat),
          longitude: parseFloat(stationLng),
          queue_capacity: parseInt(queueCapacity, 10),
          pump_count: parseInt(pumpCount, 10),
          slot_duration_minutes: parseInt(slotDuration, 10),
          booking_window_hours: 24,
          max_vehicles_per_slot: parseInt(maxPerSlot, 10),
        }),
      });

      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Failed to create station');

      setStationMsg(`Station "${data.name}" registered successfully.`);
      setStationName('');
      setStationAddress('');
      loadStations();
    } catch (err: any) {
      setStationMsg(`Error: ${err.message}`);
    }
  };

  const handleSaveCameraConfig = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedStationId || !token) return;
    setCameraMsg(null);
    setTestResult(null);

    try {
      const roiPayload = JSON.stringify({
        x1: liveRoiX1 / 100,
        y1: liveRoiY1 / 100,
        x2: liveRoiX2 / 100,
        y2: liveRoiY2 / 100,
      });

      const res = await fetch(`http://127.0.0.1:8000/api/stations/${selectedStationId}/camera`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          camera_name: cameraName,
          camera_type: cameraType,
          stream_url: cameraStreamUrl,
          is_active: true,
          detection_roi: roiPayload,
          frame_sampling_rate: frameSamplingRate,
        }),
      });

      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Failed to save camera configuration');

      setCameraMsg(`Camera configuration saved. Masked Stream: ${data.stream_url_masked}`);
      loadLiveStatus(selectedStationId);
    } catch (err: any) {
      setCameraMsg(`Error: ${err.message}`);
    }
  };

  const handleTestCameraStream = async () => {
    if (!selectedStationId || !token || !cameraStreamUrl.trim()) {
      setCameraMsg('Please enter a stream URL or device index to test.');
      return;
    }
    setIsTestingStream(true);
    setTestResult(null);
    try {
      const res = await fetch(`http://127.0.0.1:8000/api/stations/${selectedStationId}/camera/test`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          camera_type: cameraType,
          stream_url: cameraStreamUrl,
        }),
      });
      const data = await res.json();
      setTestResult(data);
    } catch (err: any) {
      setTestResult({
        success: false,
        message: `Network error probing camera: ${err.message}`,
        camera_type: cameraType,
      });
    } finally {
      setIsTestingStream(false);
    }
  };

  const handleConnectCamera = async () => {
    if (!selectedStationId || !token) return;
    setIsConnecting(true);
    setCameraMsg(null);
    try {
      const res = await fetch(`http://127.0.0.1:8000/api/stations/${selectedStationId}/camera/connect`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          frame_sampling_rate: frameSamplingRate,
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Failed to connect camera');
      setLiveStatus(data);
      setFeedTimestamp(Date.now());
      setCameraMsg('Live camera connected. YOLO detection & tracking active.');
      loadLiveHistory(selectedStationId);
    } catch (err: any) {
      setCameraMsg(`Connection Error: ${err.message}`);
    } finally {
      setIsConnecting(false);
    }
  };

  const handleDisconnectCamera = async () => {
    if (!selectedStationId || !token) return;
    setIsDisconnecting(true);
    try {
      const res = await fetch(`http://127.0.0.1:8000/api/stations/${selectedStationId}/camera/disconnect`, {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${token}`,
        },
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Failed to disconnect camera');
      setLiveStatus(data);
      setCameraMsg('Camera disconnected. Live stream capture stopped.');
      loadLiveHistory(selectedStationId);
    } catch (err: any) {
      setCameraMsg(`Disconnect Error: ${err.message}`);
    } finally {
      setIsDisconnecting(false);
    }
  };

  const handleUploadVideo = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedStationId || !videoFile) return;

    setUploadingVideo(true);
    setVideoUploadMsg(null);

    try {
      const formData = new FormData();
      formData.append('file', videoFile);
      const roiPayload = JSON.stringify({
        x1: recordedRoiX1 / 100,
        y1: recordedRoiY1 / 100,
        x2: recordedRoiX2 / 100,
        y2: recordedRoiY2 / 100,
      });
      formData.append('roi_config', roiPayload);

      const res = await fetch(`http://127.0.0.1:8000/api/stations/${selectedStationId}/video-analyses`, {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${token}`,
        },
        body: formData,
      });

      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Upload failed');

      setVideoUploadMsg(`Video "${data.filename}" uploaded. YOLO analysis initiated.`);
      setVideoFile(null);
      if (fileInputRef.current) fileInputRef.current.value = '';
      loadAnalyses(selectedStationId);
      setSelectedAnalysisId(data.id);
    } catch (err: any) {
      setVideoUploadMsg(`Upload Error: ${err.message}`);
    } finally {
      setUploadingVideo(false);
    }
  };

  const handleCreateSlot = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedStationId) return;
    setSlotMsg(null);

    try {
      const res = await fetch(`http://127.0.0.1:8000/api/stations/${selectedStationId}/slots`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          start_time: new Date(slotStartTime).toISOString(),
          end_time: new Date(slotEndTime).toISOString(),
          max_capacity: parseInt(slotCapacity, 10),
        }),
      });

      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Failed to create slot');

      setSlotMsg(`Slot created (Capacity: ${data.max_capacity} vehicles).`);
      setSlotStartTime('');
      setSlotEndTime('');
    } catch (err: any) {
      setSlotMsg(`Error: ${err.message}`);
    }
  };

  const handleReprocessVideo = async (analysisId: number) => {
    if (!selectedStationId || !token) return;
    try {
      setVideoUploadMsg('Re-running YOLO detection with updated color palette...');
      const res = await fetch(`http://127.0.0.1:8000/api/stations/${selectedStationId}/video-analyses/${analysisId}/reprocess`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`
        }
      });
      if (res.ok) {
        setVideoUploadMsg('YOLO analysis re-initiated. Refreshing in a few moments...');
        setFeedTimestamp(Date.now());
        loadAnalyses(selectedStationId);
      } else {
        const err = await res.json().catch(() => ({}));
        setVideoUploadMsg(`Error: ${err.detail || 'Failed to reprocess video.'}`);
      }
    } catch (e: any) {
      setVideoUploadMsg(`Network error: ${e.message}`);
    }
  };

  const selectedAnalysis =
    analyses.find((a) => a.id === selectedAnalysisId) ||
    (analyses.length > 0 ? analyses[0] : null);

  // Reset playback synchronization state when switching recordings
  useEffect(() => {
    if (animFrameRef.current) {
      cancelAnimationFrame(animFrameRef.current);
      animFrameRef.current = null;
    }
    setPlaybackTime(0);
    setIsPlaying(false);
    setHasStarted(false);
    if (videoRef.current) {
      videoRef.current.currentTime = 0;
    }
  }, [selectedAnalysisId]);

  useEffect(() => {
    return () => {
      if (animFrameRef.current) {
        cancelAnimationFrame(animFrameRef.current);
      }
    };
  }, []);

  const handleVideoPlay = () => {
    setIsPlaying(true);
    setHasStarted(true);

    const tick = () => {
      if (videoRef.current && !videoRef.current.paused && !videoRef.current.ended) {
        setPlaybackTime(videoRef.current.currentTime);
        animFrameRef.current = requestAnimationFrame(tick);
      }
    };
    animFrameRef.current = requestAnimationFrame(tick);
  };

  const handleVideoPause = () => {
    setIsPlaying(false);
    if (animFrameRef.current) {
      cancelAnimationFrame(animFrameRef.current);
      animFrameRef.current = null;
    }
    if (videoRef.current) {
      setPlaybackTime(videoRef.current.currentTime);
    }
  };

  const handleVideoEnded = () => {
    setIsPlaying(false);
    if (animFrameRef.current) {
      cancelAnimationFrame(animFrameRef.current);
      animFrameRef.current = null;
    }
    if (videoRef.current) {
      setPlaybackTime(videoRef.current.duration || videoRef.current.currentTime);
    }
  };

  const handleVideoTimeUpdate = () => {
    if (videoRef.current) {
      setPlaybackTime(videoRef.current.currentTime);
    }
  };

  const handleVideoSeeked = () => {
    if (videoRef.current) {
      const t = videoRef.current.currentTime;
      setPlaybackTime(t);
      if (t === 0) {
        setHasStarted(false);
      }
    }
  };

  const handleRestartVideo = () => {
    if (videoRef.current) {
      videoRef.current.currentTime = 0;
      setPlaybackTime(0);
      setHasStarted(false);
      videoRef.current.play().catch(() => {});
    }
  };

  // Derive dynamically synchronized live metrics from YOLO analysis timeline for current playback timestamp
  const liveVideoMetrics = (() => {
    if (!selectedAnalysis) return null;
    const timeline = selectedAnalysis.analytics_timeline;
    if (!timeline || timeline.length === 0) {
      return {
        peakQueue: selectedAnalysis.peak_queue_count,
        avgQueue: selectedAnalysis.average_queue_count !== undefined && selectedAnalysis.average_queue_count !== null
          ? Math.round(Number(selectedAnalysis.average_queue_count))
          : 0,
        currentQueue: selectedAnalysis.peak_queue_count,
        totalDetected: selectedAnalysis.total_vehicles_detected,
        estimatedWaitMinutes: selectedAnalysis.estimated_queue_wait_minutes ?? 0,
        waitingTimeDisplay: selectedAnalysis.waiting_time_display ||
          (selectedAnalysis.average_waiting_time_seconds !== null && selectedAnalysis.average_waiting_time_seconds !== undefined
            ? `${Math.ceil(selectedAnalysis.average_waiting_time_seconds / 60)} min`
            : '0 min'),
        vehicleClasses: selectedAnalysis.vehicle_classes_detected,
      };
    }

    // Sort timeline chronologically
    const sorted = [...timeline].sort((a, b) => a.time_sec - b.time_sec);

    // Find the latest timeline entry that has time_sec <= playbackTime (with 0.05s tolerance)
    let activeIdx = 0;
    for (let i = 0; i < sorted.length; i++) {
      if (sorted[i].time_sec <= playbackTime + 0.05) {
        activeIdx = i;
      } else {
        break;
      }
    }

    const currentEntry = sorted[activeIdx];
    // History includes all timeline events from start of video up to current playback timestamp
    const history = sorted.slice(0, activeIdx + 1);

    const peak = history.reduce((max, e) => Math.max(max, e.queue_count_roi), 0);
    const sumQueue = history.reduce((sum, e) => sum + e.queue_count_roi, 0);
    const avg = history.length > 0 ? Math.round(sumQueue / history.length) : 0;

    const waitMins = currentEntry.estimated_queue_wait_minutes !== undefined
      ? currentEntry.estimated_queue_wait_minutes
      : 0;
    const waitDisplay = currentEntry.waiting_time_display || `${waitMins} min`;

    return {
      peakQueue: peak,
      avgQueue: avg,
      currentQueue: currentEntry.queue_count_roi,
      totalDetected: currentEntry.total_detected,
      estimatedWaitMinutes: waitMins,
      waitingTimeDisplay: waitDisplay,
      vehicleClasses: currentEntry.vehicle_classes || selectedAnalysis.vehicle_classes_detected,
    };
  })();

  return (
    <div>
      {/* Operator Authentication Banner */}
      <div className="card" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <span className="tag-badge">Operator Authenticated</span>
          <div style={{ fontSize: '15px', fontWeight: 700, marginTop: '4px' }}>
            {username} ({role})
          </div>
          <div style={{ fontSize: '12px' }}>Role-based server authorization active.</div>
        </div>
        <div style={{ display: 'flex', gap: '8px' }}>
          <button type="button" className="btn-secondary" onClick={onReturnToUserFlow}>
            ← User Flow
          </button>
          <button type="button" className="btn-secondary" onClick={onLogout}>
            Log Out
          </button>
        </div>
      </div>

      {/* Operator Sub-Navigation Bar */}
      <div style={{ display: 'flex', gap: '8px', marginBottom: '16px', flexWrap: 'wrap' }}>
        <button
          type="button"
          className={`nav-btn ${operatorTab === 'stations' ? 'active' : ''}`}
          onClick={() => setOperatorTab('stations')}
        >
          1. Assigned Stations
        </button>
        <button
          type="button"
          className={`nav-btn ${operatorTab === 'cctv' ? 'active' : ''}`}
          onClick={() => setOperatorTab('cctv')}
        >
          2. CCTV & Queue Analytics
        </button>
        <button
          type="button"
          className={`nav-btn ${operatorTab === 'slots' ? 'active' : ''}`}
          onClick={() => setOperatorTab('slots')}
        >
          3. Slot Management
        </button>
      </div>

      {/* 1. Stations Registration & List View */}
      {operatorTab === 'stations' && (
        <div>
          <div className="card">
            <h3 style={{ fontSize: '15px', fontWeight: 700, marginBottom: '6px' }}>
              Register Fuel Station
            </h3>
            <p style={{ fontSize: '13px', marginBottom: '12px' }}>
              Set pump dispensers, physical queue space, and booking parameters.
            </p>

            <form onSubmit={handleCreateStation} style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px' }}>
                <div>
                  <label style={{ display: 'block', fontSize: '13px', fontWeight: 600 }}>Station Name:</label>
                  <input
                    type="text"
                    required
                    className="input-field"
                    value={stationName}
                    onChange={(e) => setStationName(e.target.value)}
                    placeholder="e.g. Shell City Center"
                  />
                </div>
                <div>
                  <label style={{ display: 'block', fontSize: '13px', fontWeight: 600 }}>Address:</label>
                  <input
                    type="text"
                    required
                    className="input-field"
                    value={stationAddress}
                    onChange={(e) => setStationAddress(e.target.value)}
                    placeholder="e.g. 104 Ring Road"
                  />
                </div>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px' }}>
                <div>
                  <label style={{ display: 'block', fontSize: '13px', fontWeight: 600 }}>Latitude:</label>
                  <input
                    type="text"
                    required
                    className="input-field"
                    value={stationLat}
                    onChange={(e) => setStationLat(e.target.value)}
                  />
                </div>
                <div>
                  <label style={{ display: 'block', fontSize: '13px', fontWeight: 600 }}>Longitude:</label>
                  <input
                    type="text"
                    required
                    className="input-field"
                    value={stationLng}
                    onChange={(e) => setStationLng(e.target.value)}
                  />
                </div>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '10px' }}>
                <div>
                  <label style={{ display: 'block', fontSize: '13px', fontWeight: 600 }}>Queue Cap:</label>
                  <input
                    type="number"
                    min={1}
                    max={200}
                    className="input-field"
                    value={queueCapacity}
                    onChange={(e) => setQueueCapacity(e.target.value)}
                  />
                </div>
                <div>
                  <label style={{ display: 'block', fontSize: '13px', fontWeight: 600 }}>Pumps:</label>
                  <input
                    type="number"
                    min={1}
                    max={50}
                    className="input-field"
                    value={pumpCount}
                    onChange={(e) => setPumpCount(e.target.value)}
                  />
                </div>
                <div>
                  <label style={{ display: 'block', fontSize: '13px', fontWeight: 600 }}>Slot (min):</label>
                  <input
                    type="number"
                    min={5}
                    max={120}
                    className="input-field"
                    value={slotDuration}
                    onChange={(e) => setSlotDuration(e.target.value)}
                  />
                </div>
                <div>
                  <label style={{ display: 'block', fontSize: '13px', fontWeight: 600 }}>Max/Slot:</label>
                  <input
                    type="number"
                    min={1}
                    max={50}
                    className="input-field"
                    value={maxPerSlot}
                    onChange={(e) => setMaxPerSlot(e.target.value)}
                  />
                </div>
              </div>

              {stationMsg && <div className="notice-box">{stationMsg}</div>}

              <button type="submit" className="btn-primary" style={{ marginTop: '6px' }}>
                Save Station
              </button>
            </form>
          </div>

          {/* Assigned Stations Table */}
          <div className="card">
            <h3 style={{ fontSize: '15px', fontWeight: 700, marginBottom: '10px' }}>
              Your Authorized Fuel Stations ({stations.length})
            </h3>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
              {stations.map((st) => (
                <div
                  key={st.id}
                  style={{
                    border: '1px solid var(--border-subtle)',
                    padding: '12px 14px',
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                  }}
                >
                  <div>
                    <div style={{ fontWeight: 700, fontSize: '14px' }}>
                      {st.name} <span style={{ fontSize: '12px', opacity: 0.8 }}>(ID: {st.id})</span>
                    </div>
                    <div style={{ fontSize: '12px' }}>{st.address}</div>
                    <div style={{ fontSize: '11px', marginTop: '2px' }}>
                      Dispensers: {st.pump_count} | Queue Limit: {st.queue_capacity} | Slot Duration: {st.slot_duration_minutes}m
                    </div>
                  </div>
                  <button
                    type="button"
                    className="btn-secondary"
                    onClick={() => {
                      setSelectedStationId(st.id);
                      setOperatorTab('cctv');
                    }}
                    style={{ fontSize: '12px', padding: '6px 10px' }}
                  >
                    Open CCTV & Analytics →
                  </button>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Station Selector Bar for CCTV & Slot Management */}
      {operatorTab !== 'stations' && stations.length > 0 && (
        <div className="card" style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '16px' }}>
          <span style={{ fontWeight: 700, fontSize: '14px' }}>Managing Station:</span>
          <select
            className="input-field"
            style={{ width: 'auto', flex: 1, marginTop: 0 }}
            value={selectedStationId ?? ''}
            onChange={(e) => setSelectedStationId(Number(e.target.value))}
          >
            {stations.map((st) => (
              <option key={st.id} value={st.id}>
                {st.name} — {st.address} (ID: {st.id})
              </option>
            ))}
          </select>
        </div>
      )}

      {/* 2. CCTV & Queue Analytics View */}
      {operatorTab === 'cctv' && selectedStationId && (
        <div>
          {/* Mode Selector: Live CCTV vs Recorded Video */}
          <div style={{ display: 'flex', gap: '8px', marginBottom: '14px' }}>
            <button
              type="button"
              className="btn-secondary"
              style={{
                fontWeight: 700,
                fontSize: '13px',
                padding: '10px 18px',
                border: '1px solid var(--border-strong)',
                backgroundColor: cctvMode === 'live' ? 'var(--color-charcoal)' : 'var(--color-white)',
                color: cctvMode === 'live' ? 'var(--color-white)' : 'var(--color-charcoal)',
              }}
              onClick={() => setCctvMode('live')}
            >
              ● Live CCTV
            </button>
            <button
              type="button"
              className="btn-secondary"
              style={{
                fontWeight: 700,
                fontSize: '13px',
                padding: '10px 18px',
                border: '1px solid var(--border-strong)',
                backgroundColor: cctvMode === 'recorded' ? 'var(--color-charcoal)' : 'var(--color-white)',
                color: cctvMode === 'recorded' ? 'var(--color-white)' : 'var(--color-charcoal)',
              }}
              onClick={() => setCctvMode('recorded')}
            >
              📁 Recorded Video
            </button>
          </div>

          {/* ================= MODE A: LIVE CCTV ================= */}
          {cctvMode === 'live' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
              {/* Live Camera Connection & Control Bar */}
              <div className="card">
                {/* Header with Station Name & Connection Status */}
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '10px', marginBottom: '14px' }}>
                  <div>
                    <h3 style={{ fontSize: '17px', fontWeight: 700, margin: 0, display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <span>Live CCTV & Real-Time Queue Analytics</span>
                      <span
                        style={{
                          fontSize: '11px',
                          fontWeight: 700,
                          padding: '2px 8px',
                          border: '1px solid var(--border-strong)',
                          backgroundColor: 'var(--color-light-grey)',
                          color: 'var(--color-charcoal)',
                        }}
                      >
                        Station #{selectedStationId} • {liveStatus?.station_name || selectedStation?.name || 'Fuel Station'}
                      </span>
                    </h3>
                  </div>

                  {/* Real Camera State Badge & Action Controls */}
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    {/* Live Camera State Badge */}
                    <span
                      style={{
                        display: 'inline-flex',
                        alignItems: 'center',
                        gap: '6px',
                        fontSize: '12px',
                        fontWeight: 700,
                        padding: '4px 10px',
                        border: '1px solid var(--border-strong)',
                        backgroundColor:
                          liveStatus?.connection_status === 'CONNECTED'
                            ? 'var(--color-charcoal)'
                            : liveStatus?.connection_status === 'ERROR'
                            ? '#fef2f2'
                            : 'var(--color-light-grey)',
                        color:
                          liveStatus?.connection_status === 'CONNECTED'
                            ? 'var(--color-white)'
                            : liveStatus?.connection_status === 'ERROR'
                            ? '#991b1b'
                            : 'var(--color-charcoal)',
                      }}
                    >
                      <span
                        style={{
                          width: '8px',
                          height: '8px',
                          borderRadius: '50%',
                          backgroundColor:
                            liveStatus?.connection_status === 'CONNECTED'
                              ? '#22c55e'
                              : liveStatus?.connection_status === 'CONNECTING' || liveStatus?.connection_status === 'RECONNECTING'
                              ? '#eab308'
                              : liveStatus?.connection_status === 'ERROR'
                              ? '#ef4444'
                              : '#737373',
                          display: 'inline-block',
                        }}
                      />
                      {liveStatus?.connection_status === 'CONNECTED'
                        ? 'LIVE'
                        : liveStatus?.connection_status === 'CONNECTING' || liveStatus?.connection_status === 'RECONNECTING'
                        ? 'CONNECTING'
                        : liveStatus?.connection_status === 'ERROR'
                        ? 'ERROR'
                        : 'DISCONNECTED'}
                    </span>

                    {/* Connect / Disconnect Buttons */}
                    {liveStatus?.connection_status === 'CONNECTED' || liveStatus?.connection_status === 'CONNECTING' ? (
                      <button
                        type="button"
                        className="btn-secondary"
                        onClick={handleDisconnectCamera}
                        disabled={isDisconnecting}
                        style={{ fontSize: '12px', padding: '5px 12px' }}
                      >
                        {isDisconnecting ? 'Stopping...' : '⏹ Disconnect'}
                      </button>
                    ) : (
                      <button
                        type="button"
                        className="btn-primary"
                        onClick={handleConnectCamera}
                        disabled={isConnecting}
                        style={{ fontSize: '12px', padding: '5px 12px' }}
                      >
                        {isConnecting ? 'Connecting...' : '▶ Connect Camera'}
                      </button>
                    )}

                    <button
                      type="button"
                      className="btn-secondary"
                      onClick={() => {
                        loadLiveStatus(selectedStationId);
                        setFeedTimestamp(Date.now());
                      }}
                      style={{ fontSize: '12px', padding: '5px 10px' }}
                      title="Refresh camera status and video stream"
                    >
                      ↻ Refresh
                    </button>
                  </div>
                </div>

                {cameraMsg && <div className="notice-box" style={{ marginBottom: '14px' }}>{cameraMsg}</div>}

                {/* Professional Split-Screen Layout */}
                <div
                  style={{
                    display: 'grid',
                    gridTemplateColumns: 'minmax(380px, 1.45fr) minmax(310px, 1fr)',
                    gap: '16px',
                    alignItems: 'start',
                  }}
                >
                  {/* LEFT COLUMN: Prominent CCTV Video Stream Container */}
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '6px' }}>
                      <div style={{ fontSize: '13px', fontWeight: 700, display: 'flex', alignItems: 'center', gap: '6px' }}>
                        <span>CCTV Video Feed</span>
                        <span
                          style={{
                            fontSize: '10px',
                            fontWeight: 700,
                            padding: '1px 6px',
                            border: '1px solid var(--border-strong)',
                            backgroundColor: 'var(--color-white)',
                            textTransform: 'uppercase',
                          }}
                        >
                          {liveStatus?.camera_type || 'RTSP'}
                        </span>
                        {/* Stream Mode Switcher */}
                        <div style={{ display: 'inline-flex', gap: '4px', marginLeft: '6px' }}>
                          <button
                            type="button"
                            onClick={() => {
                              setStreamDisplayMode('mjpeg');
                              setFeedTimestamp(Date.now());
                            }}
                            style={{
                              fontSize: '10px',
                              fontWeight: 700,
                              padding: '2px 6px',
                              border: '1px solid var(--border-subtle)',
                              backgroundColor: streamDisplayMode === 'mjpeg' ? 'var(--color-charcoal)' : 'var(--color-white)',
                              color: streamDisplayMode === 'mjpeg' ? '#FFFFFF' : 'var(--color-charcoal)',
                              cursor: 'pointer',
                            }}
                            title="Continuous multipart MJPEG stream"
                          >
                            ● MJPEG
                          </button>
                          <button
                            type="button"
                            onClick={() => {
                              setStreamDisplayMode('snapshot');
                              setFeedTimestamp(Date.now());
                            }}
                            style={{
                              fontSize: '10px',
                              fontWeight: 700,
                              padding: '2px 6px',
                              border: '1px solid var(--border-subtle)',
                              backgroundColor: streamDisplayMode === 'snapshot' ? 'var(--color-charcoal)' : 'var(--color-white)',
                              color: streamDisplayMode === 'snapshot' ? '#FFFFFF' : 'var(--color-charcoal)',
                              cursor: 'pointer',
                            }}
                            title="Direct 1-second fresh frame snapshot polling (firewall & proxy friendly)"
                          >
                            📷 Snapshot
                          </button>
                        </div>
                      </div>
                      <span className="tag-badge" style={{ margin: 0 }}>LIVE CCTV</span>
                    </div>

                    {/* Stream Window */}
                    <div
                      style={{
                        border: '1px solid var(--border-strong)',
                        backgroundColor: '#181818',
                        minHeight: '380px',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        overflow: 'hidden',
                        position: 'relative',
                        boxShadow: '0 4px 12px rgba(0, 0, 0, 0.15)',
                      }}
                    >
                      {liveStatus?.connection_status === 'CONNECTED' ? (
                        <div style={{ position: 'relative', width: '100%', height: '100%', minHeight: '380px', display: 'flex', alignItems: 'center', justifyContent: 'center', backgroundColor: '#111111' }}>
                          <img
                            key={`${selectedStationId}-${feedTimestamp}-${streamDisplayMode}`}
                            src={
                              streamDisplayMode === 'mjpeg'
                                ? `http://127.0.0.1:8000/api/stations/${selectedStationId}/camera/live-feed?t=${feedTimestamp}`
                                : `http://127.0.0.1:8000/api/stations/${selectedStationId}/camera/live-snapshot?t=${feedTimestamp}`
                            }
                            alt="Live CCTV Stream with YOLOv8 Overlays"
                            style={{
                              width: '100%',
                              maxHeight: '480px',
                              objectFit: 'contain',
                              display: imageError ? 'none' : 'block',
                              backgroundColor: '#111111',
                            }}
                            onError={() => setImageError(true)}
                            onLoad={() => setImageError(false)}
                          />

                          {imageError ? (
                            <div style={{ padding: '36px 20px', textAlign: 'center', color: '#FFFFFF', backgroundColor: '#181818', width: '100%' }}>
                              <div style={{ fontSize: '15px', fontWeight: 700, marginBottom: '6px' }}>
                                Awaiting Camera Video Stream...
                              </div>
                              <p style={{ fontSize: '12px', opacity: 0.8, maxWidth: '400px', margin: '0 auto 14px', lineHeight: '1.5' }}>
                                Camera is connected. Stream feed re-negotiating frame pipeline...
                              </p>
                              <div style={{ display: 'flex', gap: '8px', justifyContent: 'center' }}>
                                <button
                                  type="button"
                                  className="btn-secondary"
                                  onClick={() => {
                                    setImageError(false);
                                    setFeedTimestamp(Date.now());
                                    loadLiveStatus(selectedStationId);
                                  }}
                                  style={{ fontSize: '12px', padding: '5px 14px', backgroundColor: 'var(--color-charcoal)', color: '#FFFFFF' }}
                                >
                                  ↻ Reconnect Feed
                                </button>
                                <button
                                  type="button"
                                  className="btn-secondary"
                                  onClick={() => {
                                    setImageError(false);
                                    setStreamDisplayMode('snapshot');
                                    setFeedTimestamp(Date.now());
                                  }}
                                  style={{ fontSize: '12px', padding: '5px 14px', backgroundColor: '#303030', color: '#FFFFFF' }}
                                >
                                  Switch to Snapshot Mode
                                </button>
                              </div>
                            </div>
                          ) : (
                            /* Floating HUD overlay on active video */
                            <div
                              style={{
                                position: 'absolute',
                                top: '10px',
                                right: '10px',
                                display: 'flex',
                                gap: '6px',
                                alignItems: 'center',
                                pointerEvents: 'none',
                                zIndex: 5,
                                flexWrap: 'wrap',
                                justifyContent: 'flex-end',
                              }}
                            >
                              {liveStatus?.tractor_detected && (
                                <span
                                  style={{
                                    backgroundColor: '#ea580c',
                                    color: '#FFFFFF',
                                    fontSize: '10px',
                                    fontWeight: 900,
                                    letterSpacing: '0.6px',
                                    padding: '2px 8px',
                                    borderRadius: '2px',
                                    boxShadow: '0 2px 6px rgba(0,0,0,0.5)',
                                    display: 'flex',
                                    alignItems: 'center',
                                    gap: '4px',
                                  }}
                                >
                                  🚜 TRACTOR DETECTED
                                </span>
                              )}
                              <span
                                style={{
                                  backgroundColor: 'rgba(22, 163, 74, 0.92)',
                                  color: '#FFFFFF',
                                  fontSize: '10px',
                                  fontWeight: 800,
                                  letterSpacing: '0.6px',
                                  padding: '2px 8px',
                                  borderRadius: '2px',
                                  display: 'flex',
                                  alignItems: 'center',
                                  gap: '5px',
                                  boxShadow: '0 2px 6px rgba(0,0,0,0.5)',
                                }}
                              >
                                <span
                                  style={{
                                    width: '6px',
                                    height: '6px',
                                    borderRadius: '50%',
                                    backgroundColor: '#FFFFFF',
                                    display: 'inline-block',
                                  }}
                                />
                                LIVE
                              </span>
                              {liveStatus?.frame_number !== null && liveStatus?.frame_number !== undefined && (
                                <span
                                  style={{
                                    backgroundColor: 'rgba(30, 30, 30, 0.88)',
                                    color: '#FFFFFF',
                                    fontSize: '10px',
                                    fontWeight: 700,
                                    padding: '2px 6px',
                                    borderRadius: '2px',
                                    fontFamily: 'monospace',
                                    boxShadow: '0 2px 6px rgba(0,0,0,0.5)',
                                  }}
                                >
                                  Frame #{liveStatus.frame_number}
                                </span>
                              )}
                              {liveStatus?.measured_fps !== null && liveStatus?.measured_fps !== undefined && (
                                <span
                                  style={{
                                    backgroundColor: 'rgba(30, 30, 30, 0.88)',
                                    color: '#FFFFFF',
                                    fontSize: '10px',
                                    fontWeight: 700,
                                    padding: '2px 7px',
                                    borderRadius: '2px',
                                    fontFamily: 'monospace',
                                    boxShadow: '0 2px 6px rgba(0,0,0,0.5)',
                                  }}
                                >
                                  {liveStatus.measured_fps.toFixed(1)} FPS
                                </span>
                              )}
                            </div>
                          )}
                        </div>
                      ) : (
                        <div
                          style={{
                            padding: '40px 24px',
                            textAlign: 'center',
                            color: '#FFFFFF',
                            backgroundColor: '#181818',
                            width: '100%',
                          }}
                        >
                          <div style={{ fontSize: '16px', fontWeight: 700, marginBottom: '8px', letterSpacing: '-0.2px' }}>
                            {liveStatus?.connection_status === 'CONNECTING' || liveStatus?.connection_status === 'RECONNECTING'
                              ? 'Connecting to CCTV Stream...'
                              : liveStatus?.connection_status === 'ERROR'
                              ? 'Camera Connection Error'
                              : 'CCTV Camera Offline / Disconnected'}
                          </div>
                          <p style={{ fontSize: '12px', opacity: 0.85, maxWidth: '420px', margin: '0 auto', lineHeight: '1.5' }}>
                            {liveStatus?.connection_status === 'CONNECTING' || liveStatus?.connection_status === 'RECONNECTING'
                              ? 'Initiating stream connection and launching real-time YOLO vehicle detection & ByteTrack tracking pipeline. Please wait...'
                              : liveStatus?.connection_status === 'ERROR'
                              ? liveStatus.last_error || 'Failed to establish connection with the camera stream. Please check configuration.'
                              : 'No active stream running for this station. Configure camera source or webcam index below, then click Connect Camera.'}
                          </p>

                          {liveStatus?.stream_url_masked && (
                            <div style={{ marginTop: '12px', fontSize: '11px', opacity: 0.75, fontFamily: 'monospace' }}>
                              Target Source: <code>{liveStatus.stream_url_masked}</code>
                            </div>
                          )}

                          {liveStatus?.connection_status !== 'CONNECTING' && liveStatus?.connection_status !== 'RECONNECTING' && (
                            <div style={{ marginTop: '18px' }}>
                              <button
                                type="button"
                                className="btn-primary"
                                onClick={handleConnectCamera}
                                disabled={isConnecting}
                                style={{ fontSize: '12px', padding: '6px 18px', backgroundColor: '#FFFFFF', color: '#181818', fontWeight: 700 }}
                              >
                                {isConnecting ? 'Connecting...' : '▶ Connect Now'}
                              </button>
                            </div>
                          )}
                        </div>
                      )}
                    </div>

                    {/* Detection Class Legend Bar */}
                    <div
                      style={{
                        border: '1px solid var(--border-subtle)',
                        padding: '8px 12px',
                        backgroundColor: 'var(--color-white)',
                        fontSize: '11px',
                        display: 'flex',
                        flexDirection: 'column',
                        gap: '6px',
                      }}
                    >
                      <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap', alignItems: 'center' }}>
                        <span style={{ fontWeight: 700 }}>Color Classes:</span>
                        <span style={{ color: '#16a34a', fontWeight: 700 }}>● Car (Green)</span>
                        <span style={{ color: '#0284c7', fontWeight: 700 }}>● Motorcycle (Blue)</span>
                        <span style={{ color: '#ca8a04', fontWeight: 700 }}>● Bus (Yellow)</span>
                        <span style={{ color: '#9333ea', fontWeight: 700 }}>● Truck (Magenta)</span>
                        <span style={{ color: '#ea580c', fontWeight: 700 }}>● Tractor (Orange)</span>
                        <span style={{ color: '#0891b2', fontWeight: 700 }}>● Auto (Cyan)</span>
                        <span style={{ color: '#ea580c', fontWeight: 700 }}>■ Queue ROI (Orange)</span>
                      </div>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '6px', fontSize: '10px' }}>
                        <span style={{ opacity: 0.75 }}>
                          ByteTrack tracking maintains persistent vehicle IDs across frames.
                        </span>
                        {liveStatus?.model_supports_tractor ? (
                          <span style={{ color: '#166534', backgroundColor: '#dcfce7', padding: '1px 6px', fontWeight: 700, border: '1px solid #bbf7d0' }}>
                            ✓ Tractor-Capable Model Active
                          </span>
                        ) : (
                          <span style={{ color: '#854d0e', backgroundColor: '#fef9c3', padding: '1px 6px', fontWeight: 600, border: '1px solid #fef08a' }}>
                            ℹ COCO 80 Weights (No dedicated tractor class in standard COCO)
                          </span>
                        )}
                      </div>
                    </div>
                  </div>

                  {/* RIGHT COLUMN: Real-Time Analytics Cards */}
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                    {/* 1. Camera & Station Configuration Card */}
                    <div style={{ border: '1px solid var(--border-strong)', padding: '12px', backgroundColor: 'var(--color-white)' }}>
                      <div style={{ fontSize: '11px', textTransform: 'uppercase', fontWeight: 700, letterSpacing: '0.5px', marginBottom: '8px' }}>
                        Camera & Vision Model
                      </div>
                      <div style={{ display: 'grid', gridTemplateColumns: '1fr', gap: '6px', fontSize: '12px' }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                          <span style={{ fontWeight: 600 }}>Station:</span>
                          <span style={{ fontWeight: 700 }}>
                            {liveStatus?.station_name || selectedStation?.name || `Station #${selectedStationId}`}
                          </span>
                        </div>
                        <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                          <span style={{ fontWeight: 600 }}>Camera Name:</span>
                          <span style={{ fontWeight: 700 }}>
                            {liveStatus?.camera_name || cameraName || 'Main Forecourt Camera'}
                          </span>
                        </div>
                        <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                          <span style={{ fontWeight: 600 }}>Camera Source:</span>
                          <span style={{ fontFamily: 'monospace', fontSize: '11px' }}>
                            {liveStatus?.stream_url_masked || (cameraStreamUrl ? `${cameraType.toUpperCase()} Stream` : 'Not configured')}
                          </span>
                        </div>
                        <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                          <span style={{ fontWeight: 600 }}>Model Info:</span>
                          <span style={{ fontSize: '11px', fontWeight: 600 }}>{liveStatus?.model_name || 'YOLO (ByteTrack)'}</span>
                        </div>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                          <span style={{ fontWeight: 600 }}>Tractor Class:</span>
                          <span
                            style={{
                              fontSize: '11px',
                              fontWeight: 700,
                              color: liveStatus?.model_supports_tractor ? '#166534' : '#854d0e',
                            }}
                          >
                            {liveStatus?.model_supports_tractor ? 'Supported (Dedicated class)' : 'Not in COCO weights'}
                          </span>
                        </div>
                        {liveStatus?.model_classes && liveStatus.model_classes.length > 0 && (
                          <div style={{ marginTop: '4px', borderTop: '1px dashed var(--border-subtle)', paddingTop: '4px' }}>
                            <div style={{ fontSize: '10px', fontWeight: 600, marginBottom: '3px' }}>Detected Classes:</div>
                            <div style={{ display: 'flex', gap: '4px', flexWrap: 'wrap' }}>
                              {liveStatus.model_classes.map((cls) => (
                                <span
                                  key={cls}
                                  style={{
                                    fontSize: '10px',
                                    padding: '1px 5px',
                                    backgroundColor: cls === 'tractor' ? '#ffedd5' : 'var(--color-light-grey)',
                                    color: cls === 'tractor' ? '#9a3412' : 'var(--color-charcoal)',
                                    border: '1px solid var(--border-subtle)',
                                    fontWeight: cls === 'tractor' ? 800 : 500,
                                  }}
                                >
                                  {cls}
                                </span>
                              ))}
                            </div>
                          </div>
                        )}
                      </div>
                    </div>

                    {/* 2. Queue Length Card (Inside ROI) */}
                    <div style={{ border: '1px solid var(--border-strong)', padding: '14px', backgroundColor: 'var(--color-white)' }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <div style={{ fontSize: '11px', textTransform: 'uppercase', fontWeight: 700, letterSpacing: '0.5px' }}>
                          Queue Length (ROI)
                        </div>
                        <span title="Vehicles strictly detected inside the configured Queue Region (ROI)" style={{ cursor: 'help', fontSize: '12px', opacity: 0.7 }}>ℹ</span>
                      </div>
                      <div style={{ fontSize: '26px', fontWeight: 800, marginTop: '4px', letterSpacing: '-0.5px' }}>
                        {liveStatus?.connection_status === 'CONNECTED' && liveStatus?.current_queue_count !== null && liveStatus?.current_queue_count !== undefined
                          ? `${liveStatus.current_queue_count} vehicles`
                          : 'Unavailable'}
                      </div>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '4px', fontSize: '11px', opacity: 0.85 }}>
                        <span>Inside configured queue region</span>
                        <span>
                          Capacity: {liveStatus?.connection_status === 'CONNECTED' ? liveStatus?.current_queue_count ?? 0 : '—'} / {liveStatus?.queue_capacity || selectedStation?.queue_capacity || 20}
                        </span>
                      </div>
                      {liveStatus?.active_queue_track_ids && liveStatus.active_queue_track_ids.length > 0 && (
                        <div style={{ marginTop: '8px', paddingTop: '6px', borderTop: '1px solid var(--border-subtle)', display: 'flex', alignItems: 'center', gap: '4px', flexWrap: 'wrap' }}>
                          <span style={{ fontSize: '10px', fontWeight: 700, color: '#ea580c' }}>In Queue IDs:</span>
                          {liveStatus.active_queue_track_ids.map((id) => (
                            <span
                              key={id}
                              style={{
                                fontSize: '10px',
                                fontWeight: 800,
                                padding: '1px 5px',
                                backgroundColor: '#ffedd5',
                                color: '#9a3412',
                                border: '1px solid #fed7aa',
                              }}
                            >
                              #{id}
                            </span>
                          ))}
                        </div>
                      )}
                    </div>

                    {/* 3. Detected Vehicles Card (FOV) & Breakdown */}
                    <div style={{ border: '1px solid var(--border-subtle)', padding: '12px', backgroundColor: 'var(--color-white)' }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <div style={{ fontSize: '11px', textTransform: 'uppercase', fontWeight: 700, letterSpacing: '0.5px' }}>
                          Vehicles Detected (FOV)
                        </div>
                        <span title="Total vehicles across entire camera frame" style={{ cursor: 'help', fontSize: '12px', opacity: 0.7 }}>ℹ</span>
                      </div>
                      <div style={{ fontSize: '22px', fontWeight: 700, marginTop: '3px' }}>
                        {liveStatus?.connection_status === 'CONNECTED' && liveStatus?.current_vehicles_total !== null && liveStatus?.current_vehicles_total !== undefined
                          ? `${liveStatus.current_vehicles_total} vehicles`
                          : 'Unavailable'}
                      </div>
                      {/* Vehicle Breakdown Pills */}
                      {liveStatus?.class_breakdown && Object.keys(liveStatus.class_breakdown).length > 0 && (
                        <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap', marginTop: '6px' }}>
                          {Object.entries(liveStatus.class_breakdown).map(([cls, cnt]) => (
                            <span
                              key={cls}
                              style={{
                                fontSize: '10px',
                                fontWeight: 700,
                                padding: '1px 6px',
                                backgroundColor: cls === 'tractor' ? '#ffedd5' : 'var(--color-light-grey)',
                                color: cls === 'tractor' ? '#ea580c' : 'var(--color-charcoal)',
                                border: '1px solid var(--border-subtle)',
                              }}
                            >
                              {cls.toUpperCase()}: {cnt}
                            </span>
                          ))}
                        </div>
                      )}
                      <div style={{ fontSize: '11px', marginTop: '4px', opacity: 0.8 }}>
                        {liveStatus?.cumulative_queue_vehicles_count
                          ? `Total distinct served in ROI: ${liveStatus.cumulative_queue_vehicles_count}`
                          : 'Full camera field of view'}
                      </div>
                    </div>

                    {/* 4. Queue Level Card */}
                    <div style={{ border: '1px solid var(--border-subtle)', padding: '12px', backgroundColor: 'var(--color-white)' }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '4px' }}>
                        <div style={{ fontSize: '11px', textTransform: 'uppercase', fontWeight: 700, letterSpacing: '0.5px' }}>
                          Queue Level
                        </div>
                        <span
                          style={{
                            fontSize: '11px',
                            fontWeight: 700,
                            padding: '2px 8px',
                            border: '1px solid',
                            borderColor:
                              liveStatus?.connection_status !== 'CONNECTED' || !liveStatus?.queue_level || liveStatus.queue_level === 'UNAVAILABLE'
                                ? 'var(--border-subtle)'
                                : liveStatus.queue_level === 'LOW'
                                ? '#86efac'
                                : liveStatus.queue_level === 'MODERATE'
                                ? '#fde047'
                                : liveStatus.queue_level === 'HIGH'
                                ? '#fdba74'
                                : '#fca5a5',
                            backgroundColor:
                              liveStatus?.connection_status !== 'CONNECTED' || !liveStatus?.queue_level || liveStatus.queue_level === 'UNAVAILABLE'
                                ? 'var(--color-light-grey)'
                                : liveStatus.queue_level === 'LOW'
                                ? '#dcfce7'
                                : liveStatus.queue_level === 'MODERATE'
                                ? '#fef9c3'
                                : liveStatus.queue_level === 'HIGH'
                                ? '#ffedd5'
                                : '#fee2e2',
                            color:
                              liveStatus?.connection_status !== 'CONNECTED' || !liveStatus?.queue_level || liveStatus.queue_level === 'UNAVAILABLE'
                                ? 'var(--color-charcoal)'
                                : liveStatus.queue_level === 'LOW'
                                ? '#166534'
                                : liveStatus.queue_level === 'MODERATE'
                                ? '#854d0e'
                                : liveStatus.queue_level === 'HIGH'
                                ? '#9a3412'
                                : '#991b1b',
                          }}
                        >
                          {liveStatus?.connection_status === 'CONNECTED' && liveStatus?.queue_level
                            ? liveStatus.queue_level
                            : 'UNAVAILABLE'}
                        </span>
                      </div>
                      {/* Queue Level Progress Bar */}
                      <div
                        style={{
                          height: '6px',
                          backgroundColor: 'var(--color-light-grey)',
                          border: '1px solid var(--border-subtle)',
                          marginTop: '6px',
                          overflow: 'hidden',
                        }}
                      >
                        <div
                          style={{
                            height: '100%',
                            width: `${
                              liveStatus?.connection_status === 'CONNECTED' && liveStatus?.current_queue_count !== null && liveStatus?.current_queue_count !== undefined
                                ? Math.min(100, Math.round((liveStatus.current_queue_count / (liveStatus?.queue_capacity || selectedStation?.queue_capacity || 20)) * 100))
                                : 0
                            }%`,
                            backgroundColor:
                              liveStatus?.queue_level === 'CRITICAL'
                                ? '#ef4444'
                                : liveStatus?.queue_level === 'HIGH'
                                ? '#f97316'
                                : liveStatus?.queue_level === 'MODERATE'
                                ? '#eab308'
                                : 'var(--color-charcoal)',
                            transition: 'width 0.4s ease',
                          }}
                        />
                      </div>
                    </div>

                    {/* 5. Estimated Queue Wait Card */}
                    <div style={{ border: '1px solid var(--border-subtle)', padding: '12px', backgroundColor: 'var(--color-white)' }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <div style={{ fontSize: '11px', textTransform: 'uppercase', fontWeight: 700, letterSpacing: '0.5px' }}>
                          Estimated Queue Wait
                        </div>
                        <span title="Sum of waiting vehicles inside queue ROI × vehicle service time (rounded up to whole minutes)" style={{ cursor: 'help', fontSize: '12px', opacity: 0.7 }}>ℹ</span>
                      </div>
                      <div style={{ fontSize: '18px', fontWeight: 700, marginTop: '3px' }}>
                        {liveStatus?.connection_status === 'CONNECTED' &&
                        liveStatus?.waiting_time_seconds !== null &&
                        liveStatus?.waiting_time_seconds !== undefined
                          ? (liveStatus.waiting_time_display || `${Math.ceil(liveStatus.waiting_time_seconds / 60)} min`)
                          : 'Unavailable'}
                      </div>
                      <div style={{ fontSize: '11px', marginTop: '2px', opacity: 0.8 }}>
                        {liveStatus?.connection_status === 'CONNECTED'
                          ? 'Sum of waiting vehicles × service time'
                          : 'Live camera disconnected'}
                      </div>
                    </div>

                    {/* 6. Diagnostics & Timestamps */}
                    <div style={{ border: '1px solid var(--border-subtle)', padding: '12px', backgroundColor: 'var(--color-white)', fontSize: '12px' }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
                        <span style={{ fontWeight: 600 }}>Last Updated:</span>
                        <span style={{ fontFamily: 'monospace' }}>
                          {liveStatus?.connection_status === 'CONNECTED' && liveStatus?.last_frame_timestamp
                            ? new Date(liveStatus.last_frame_timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
                            : 'Unavailable'}
                        </span>
                      </div>
                      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
                        <span style={{ fontWeight: 600 }}>Processing FPS:</span>
                        <span>
                          {liveStatus?.measured_fps !== null && liveStatus?.measured_fps !== undefined
                            ? `${liveStatus.measured_fps.toFixed(1)} FPS`
                            : liveStatus?.connection_status === 'CONNECTED'
                            ? 'Measuring...'
                            : 'Offline'}
                        </span>
                      </div>
                      {liveStatus?.frame_number !== null && liveStatus?.frame_number !== undefined && (
                        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
                          <span style={{ fontWeight: 600 }}>Frame Counter:</span>
                          <span style={{ fontFamily: 'monospace', fontWeight: 700 }}>
                            #{liveStatus.frame_number}
                          </span>
                        </div>
                      )}
                      <div style={{ fontSize: '11px', opacity: 0.75, marginTop: '4px', borderTop: '1px dashed var(--border-subtle)', paddingTop: '4px' }}>
                        Sampling: 1 in {liveStatus?.frame_sampling_rate ?? frameSamplingRate} frames • Mode: {streamDisplayMode.toUpperCase()}
                      </div>
                    </div>
                  </div>
                </div>
              </div>

              {/* Camera Connection & Queue Region (ROI) Settings */}
              <div className="card">
                <h3 style={{ fontSize: '15px', fontWeight: 700, marginBottom: '6px' }}>
                  Camera Source & Queue Region (ROI) Settings
                </h3>
                <p style={{ fontSize: '13px', marginBottom: '14px' }}>
                  Configure your genuine RTSP stream or camera index. Camera passwords are encrypted and never exposed in responses or logs.
                </p>

                <form onSubmit={handleSaveCameraConfig} style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '10px' }}>
                    <div>
                      <label style={{ display: 'block', fontSize: '12px', fontWeight: 700 }}>
                        Camera Name:
                      </label>
                      <input
                        type="text"
                        required
                        className="input-field"
                        value={cameraName}
                        onChange={(e) => setCameraName(e.target.value)}
                        placeholder="e.g. Forecourt Cam 1, Dispenser Cam"
                      />
                      <div style={{ fontSize: '10px', marginTop: '2px' }}>Actual configured display name</div>
                    </div>

                    <div>
                      <label style={{ display: 'block', fontSize: '12px', fontWeight: 700 }}>Protocol:</label>
                      <select
                        className="input-field"
                        value={cameraType}
                        onChange={(e) => setCameraType(e.target.value)}
                      >
                        <option value="rtsp">RTSP (rtsp://...)</option>
                        <option value="http">HTTP / MJPEG</option>
                        <option value="webcam">Webcam Device Index</option>
                        <option value="file">Local Video / File Stream (.mp4)</option>
                      </select>
                      <div style={{ fontSize: '10px', marginTop: '2px' }}>Hardware / Network protocol</div>
                    </div>

                    <div>
                      <label style={{ display: 'block', fontSize: '12px', fontWeight: 700 }}>
                        Stream URL or Device Index:
                      </label>
                      <input
                        type="text"
                        required
                        className="input-field"
                        value={cameraStreamUrl}
                        onChange={(e) => setCameraStreamUrl(e.target.value)}
                        placeholder={
                          cameraType === 'webcam'
                            ? '0 (numeric camera index)'
                            : cameraType === 'file'
                            ? 'C:/path/to/traffic_feed.mp4'
                            : cameraType === 'http'
                            ? 'http://192.168.1.100:8080/video.mjpg'
                            : 'rtsp://operator:password@192.168.1.100:554/live'
                        }
                      />
                      {liveStatus?.stream_url_masked ? (
                        <div style={{ fontSize: '11px', marginTop: '2px', fontFamily: 'monospace' }}>
                          Active: <code>{liveStatus.stream_url_masked}</code>
                        </div>
                      ) : (
                        <div style={{ fontSize: '10px', marginTop: '2px' }}>Credentials masked on save</div>
                      )}
                    </div>

                    <div>
                      <label style={{ display: 'block', fontSize: '12px', fontWeight: 700 }}>
                        Frame Sampling Rate:
                      </label>
                      <input
                        type="number"
                        min={1}
                        max={30}
                        className="input-field"
                        value={frameSamplingRate}
                        onChange={(e) => setFrameSamplingRate(Math.max(1, Math.min(30, Number(e.target.value))))}
                      />
                      <div style={{ fontSize: '10px', marginTop: '2px' }}>Process every Nth frame</div>
                    </div>
                  </div>

                  {/* Configurable Queue Region (ROI) */}
                  <div style={{ borderTop: '1px dashed var(--border-subtle)', paddingTop: '10px' }}>
                    <div style={{ fontSize: '13px', fontWeight: 700, marginBottom: '2px' }}>
                      Queue Region (ROI) Percentage Coordinates:
                    </div>
                    <div style={{ fontSize: '12px', marginBottom: '8px' }}>
                      Vehicles outside this rectangle are detected in the forecourt but strictly excluded from queue count.
                    </div>

                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '10px' }}>
                      <div>
                        <label style={{ display: 'block', fontSize: '11px', fontWeight: 600 }}>X1 (Left %):</label>
                        <input
                          type="number"
                          min={0}
                          max={90}
                          className="input-field"
                          value={liveRoiX1}
                          onChange={(e) => setLiveRoiX1(Math.max(0, Math.min(90, Number(e.target.value))))}
                        />
                      </div>
                      <div>
                        <label style={{ display: 'block', fontSize: '11px', fontWeight: 600 }}>Y1 (Top %):</label>
                        <input
                          type="number"
                          min={0}
                          max={90}
                          className="input-field"
                          value={liveRoiY1}
                          onChange={(e) => setLiveRoiY1(Math.max(0, Math.min(90, Number(e.target.value))))}
                        />
                      </div>
                      <div>
                        <label style={{ display: 'block', fontSize: '11px', fontWeight: 600 }}>X2 (Right %):</label>
                        <input
                          type="number"
                          min={10}
                          max={100}
                          className="input-field"
                          value={liveRoiX2}
                          onChange={(e) => setLiveRoiX2(Math.max(10, Math.min(100, Number(e.target.value))))}
                        />
                      </div>
                      <div>
                        <label style={{ display: 'block', fontSize: '11px', fontWeight: 600 }}>Y2 (Bottom %):</label>
                        <input
                          type="number"
                          min={10}
                          max={100}
                          className="input-field"
                          value={liveRoiY2}
                          onChange={(e) => setLiveRoiY2(Math.max(10, Math.min(100, Number(e.target.value))))}
                        />
                      </div>
                    </div>
                  </div>

                  {/* Action Buttons */}
                  <div style={{ display: 'flex', gap: '10px', marginTop: '6px' }}>
                    <button type="submit" className="btn-primary" style={{ padding: '8px 16px' }}>
                      Save Camera Config
                    </button>
                    <button
                      type="button"
                      className="btn-secondary"
                      onClick={handleTestCameraStream}
                      disabled={isTestingStream || !cameraStreamUrl.trim()}
                      style={{ padding: '8px 16px' }}
                    >
                      {isTestingStream ? 'Probing Stream...' : 'Test Stream Connection'}
                    </button>
                  </div>

                  {/* Test Stream Probe Results */}
                  {testResult && (
                    <div
                      style={{
                        padding: '10px 14px',
                        marginTop: '4px',
                        border: '1px solid var(--border-strong)',
                        backgroundColor: testResult.success ? 'var(--color-white)' : 'var(--color-light-grey)',
                        fontSize: '12px',
                      }}
                    >
                      <strong>Stream Check Result:</strong> {testResult.message}
                      {testResult.resolution && (
                        <span style={{ display: 'block', marginTop: '2px' }}>
                          Decoded Resolution: {testResult.resolution} @ {testResult.fps?.toFixed(1)} FPS
                        </span>
                      )}
                      {testResult.error_detail && (
                        <span style={{ display: 'block', marginTop: '2px', color: '#880000' }}>
                          Diagnostic Detail: {testResult.error_detail}
                        </span>
                      )}
                    </div>
                  )}
                </form>
              </div>

              {/* Recent Live Queue Snapshots History */}
              <div className="card">
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                  <h3 style={{ fontSize: '15px', fontWeight: 700 }}>
                    Recent Live Queue History ({liveHistory.length})
                  </h3>
                  <button
                    type="button"
                    className="btn-secondary"
                    onClick={() => loadLiveHistory(selectedStationId)}
                    style={{ fontSize: '12px', padding: '4px 8px' }}
                  >
                    Refresh History
                  </button>
                </div>
                <p style={{ fontSize: '12px', marginBottom: '10px' }}>
                  Stored queue observations recorded periodically from the live video stream.
                </p>

                {liveHistory.length === 0 ? (
                  <div className="status-box">No live measurements recorded yet for this station.</div>
                ) : (
                  <div style={{ maxHeight: '200px', overflowY: 'auto', border: '1px solid var(--border-subtle)' }}>
                    <table style={{ width: '100%', fontSize: '12px', borderCollapse: 'collapse', textAlign: 'left' }}>
                      <thead>
                        <tr style={{ backgroundColor: 'var(--color-light-grey)', borderBottom: '1px solid var(--border-strong)' }}>
                          <th style={{ padding: '6px 10px' }}>Timestamp</th>
                          <th style={{ padding: '6px 10px' }}>Vehicles in Queue (ROI)</th>
                          <th style={{ padding: '6px 10px' }}>Total in Frame</th>
                          <th style={{ padding: '6px 10px' }}>Estimated Queue Wait</th>
                        </tr>
                      </thead>
                      <tbody>
                        {liveHistory.map((s) => (
                          <tr key={s.id} style={{ borderBottom: '1px solid var(--border-subtle)' }}>
                            <td style={{ padding: '6px 10px' }}>
                              {new Date(s.measured_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
                            </td>
                            <td style={{ padding: '6px 10px', fontWeight: 700 }}>{s.queue_count}</td>
                            <td style={{ padding: '6px 10px' }}>{s.total_vehicles_detected}</td>
                            <td style={{ padding: '6px 10px' }}>
                              {s.waiting_time_seconds !== null
                                ? `${Math.ceil(s.waiting_time_seconds / 60)} min`
                                : 'Unavailable'}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* ================= MODE B: RECORDED VIDEO ANALYSIS ================= */}
          {cctvMode === 'recorded' && (
            <div className="card">
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '8px' }}>
                <div>
                  <span className="tag-badge">RECORDED VIDEO</span>
                  <h3 style={{ fontSize: '16px', fontWeight: 700, marginTop: '4px' }}>
                    Video Analysis
                  </h3>
                </div>
              </div>

              <p style={{ fontSize: '13px', marginBottom: '14px', lineHeight: '1.5' }}>
                Upload video footage (.mp4, .avi, .mov, .mkv up to 100MB) for YOLO vehicle detection and queue measurement.
                Outputs are derived strictly from recorded footage and never simulate live queue.
              </p>

              {/* Video Upload Form */}
              <form onSubmit={handleUploadVideo} style={{ border: '1px solid var(--border-subtle)', padding: '16px', marginBottom: '16px' }}>
                <div style={{ marginBottom: '12px' }}>
                  <label style={{ display: 'block', fontSize: '13px', fontWeight: 700, marginBottom: '4px' }}>
                    Select Video File:
                  </label>
                  <input
                    type="file"
                    ref={fileInputRef}
                    required
                    accept=".mp4,.avi,.mov,.mkv"
                    onChange={(e) => setVideoFile(e.target.files?.[0] || null)}
                    style={{ fontSize: '13px' }}
                  />
                  <div style={{ fontSize: '11px', marginTop: '4px' }}>
                    Accepted extensions: .mp4, .avi, .mov, .mkv (Max 100MB).
                  </div>
                </div>

                {/* Configurable Queue Region (ROI) */}
                <div style={{ marginBottom: '14px', borderTop: '1px dashed var(--border-subtle)', paddingTop: '12px' }}>
                  <div style={{ fontSize: '13px', fontWeight: 700, marginBottom: '4px' }}>
                    Configurable Queue Region (ROI) Boundary:
                  </div>
                  <div style={{ fontSize: '12px', marginBottom: '10px' }}>
                    Vehicles detected outside these percentages will be tracked but excluded from station queue metrics.
                  </div>

                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '10px' }}>
                    <div>
                      <label style={{ display: 'block', fontSize: '12px', fontWeight: 600 }}>Left (X1 %):</label>
                      <input
                        type="number"
                        min={0}
                        max={90}
                        className="input-field"
                        value={recordedRoiX1}
                        onChange={(e) => setRecordedRoiX1(Math.max(0, Math.min(90, Number(e.target.value))))}
                      />
                    </div>
                    <div>
                      <label style={{ display: 'block', fontSize: '12px', fontWeight: 600 }}>Top (Y1 %):</label>
                      <input
                        type="number"
                        min={0}
                        max={90}
                        className="input-field"
                        value={recordedRoiY1}
                        onChange={(e) => setRecordedRoiY1(Math.max(0, Math.min(90, Number(e.target.value))))}
                      />
                    </div>
                    <div>
                      <label style={{ display: 'block', fontSize: '12px', fontWeight: 600 }}>Right (X2 %):</label>
                      <input
                        type="number"
                        min={10}
                        max={100}
                        className="input-field"
                        value={recordedRoiX2}
                        onChange={(e) => setRecordedRoiX2(Math.max(10, Math.min(100, Number(e.target.value))))}
                      />
                    </div>
                    <div>
                      <label style={{ display: 'block', fontSize: '12px', fontWeight: 600 }}>Bottom (Y2 %):</label>
                      <input
                        type="number"
                        min={10}
                        max={100}
                        className="input-field"
                        value={recordedRoiY2}
                        onChange={(e) => setRecordedRoiY2(Math.max(10, Math.min(100, Number(e.target.value))))}
                      />
                    </div>
                  </div>
                </div>

                {videoUploadMsg && <div className="notice-box">{videoUploadMsg}</div>}

                <button
                  type="submit"
                  className="btn-primary"
                  disabled={uploadingVideo || !videoFile}
                  style={{ opacity: uploadingVideo || !videoFile ? 0.6 : 1 }}
                >
                  {uploadingVideo ? 'Processing video...' : 'Upload & Run Video Analysis'}
                </button>
              </form>

              {/* List of Analyzed Recordings */}
              <div>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                  <h4 style={{ fontSize: '14px', fontWeight: 700 }}>
                    Video Analyses ({analyses.length})
                  </h4>
                  <button
                    type="button"
                    className="btn-secondary"
                    onClick={() => loadAnalyses(selectedStationId)}
                    style={{ fontSize: '11px', padding: '4px 8px' }}
                  >
                    Refresh
                  </button>
                </div>

                {analyses.length === 0 ? (
                  <div className="status-box">No recorded video analyses found for this station.</div>
                ) : (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                    <div style={{ display: 'flex', gap: '8px', overflowX: 'auto', paddingBottom: '6px' }}>
                      {analyses.map((a) => (
                        <button
                          key={a.id}
                          type="button"
                          onClick={() => {
                            setSelectedAnalysisId(a.id);
                            setVideoError(null);
                            setFeedTimestamp(Date.now());
                          }}
                          style={{
                            padding: '8px 12px',
                            fontSize: '12px',
                            textAlign: 'left',
                            whiteSpace: 'nowrap',
                            border: a.id === selectedAnalysisId ? '2px solid var(--color-charcoal)' : '1px solid var(--border-subtle)',
                            backgroundColor: a.id === selectedAnalysisId ? 'var(--color-light-grey)' : 'var(--color-white)',
                            cursor: 'pointer',
                          }}
                        >
                          <div style={{ fontWeight: 700 }}>#{a.id}: {a.filename}</div>
                          <div style={{ fontSize: '11px' }}>Status: {a.status}</div>
                        </button>
                      ))}
                    </div>

                    {/* Selected Analysis Full Details */}
                    {selectedAnalysis && (
                      <div style={{ border: '1px solid var(--border-strong)', padding: '16px' }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px' }}>
                          <div>
                            <span className="tag-badge">Analysis #{selectedAnalysis.id}</span>
                            <h4 style={{ fontSize: '15px', fontWeight: 700, marginTop: '2px' }}>
                              {selectedAnalysis.filename}
                            </h4>
                          </div>
                          <span
                            style={{
                              fontSize: '12px',
                              fontWeight: 700,
                              padding: '2px 8px',
                              border: '1px solid var(--border-strong)',
                              backgroundColor: selectedAnalysis.status === 'COMPLETED' ? 'var(--color-charcoal)' : 'var(--color-white)',
                              color: selectedAnalysis.status === 'COMPLETED' ? 'var(--color-white)' : 'var(--color-charcoal)',
                            }}
                          >
                            {selectedAnalysis.status}
                          </span>
                        </div>

                        {/* Explicit Disclaimer */}
                        <div className="notice-box" style={{ marginBottom: '14px' }}>
                          <strong>Recorded video analysis using YOLO detection. Not a live reading.</strong>
                        </div>

                        {/* Summary Metrics Grid - Dynamically Synchronized with Playback */}
                        <div
                          style={{
                            display: 'grid',
                            gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))',
                            gap: '10px',
                            marginBottom: '16px',
                          }}
                        >
                          <div style={{ border: '1px solid var(--border-subtle)', padding: '12px' }}>
                            <div style={{ fontSize: '11px', textTransform: 'uppercase', fontWeight: 600 }}>Queue length (peak)</div>
                            <div style={{ fontSize: '18px', fontWeight: 800, marginTop: '2px' }}>
                              {liveVideoMetrics ? liveVideoMetrics.peakQueue : selectedAnalysis.peak_queue_count} vehicles
                            </div>
                            <div style={{ fontSize: '11px', opacity: 0.8 }}>
                              Inside queue region {liveVideoMetrics ? `(Current: ${liveVideoMetrics.currentQueue})` : ''}
                            </div>
                          </div>

                          <div style={{ border: '1px solid var(--border-subtle)', padding: '12px' }}>
                            <div style={{ fontSize: '11px', textTransform: 'uppercase', fontWeight: 600 }}>Queue length (avg)</div>
                            <div style={{ fontSize: '18px', fontWeight: 800, marginTop: '2px' }}>
                              {liveVideoMetrics
                                ? `${liveVideoMetrics.avgQueue} vehicles`
                                : (selectedAnalysis.average_queue_count !== undefined && selectedAnalysis.average_queue_count !== null
                                  ? `${Math.round(Number(selectedAnalysis.average_queue_count))} vehicles`
                                  : '—')}
                            </div>
                            <div style={{ fontSize: '11px', opacity: 0.8 }}>Across clip duration</div>
                          </div>

                          <div style={{ border: '1px solid var(--border-subtle)', padding: '12px' }}>
                            <div style={{ fontSize: '11px', textTransform: 'uppercase', fontWeight: 600 }}>Vehicles detected</div>
                            <div style={{ fontSize: '18px', fontWeight: 800, marginTop: '2px' }}>
                              {liveVideoMetrics ? liveVideoMetrics.totalDetected : selectedAnalysis.total_vehicles_detected} vehicles
                            </div>
                            <div style={{ fontSize: '11px', opacity: 0.8 }}>Boxed by YOLO</div>
                          </div>

                          <div style={{ border: '1px solid var(--border-strong)', padding: '12px' }}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                              <div style={{ fontSize: '11px', textTransform: 'uppercase', fontWeight: 600 }}>Estimated Queue Wait</div>
                              <span title="Sum of waiting vehicles inside queue ROI × vehicle service time (rounded up to whole minutes)" style={{ cursor: 'help', fontSize: '12px', opacity: 0.7 }}>ℹ</span>
                            </div>
                            <div style={{ fontSize: '16px', fontWeight: 700, marginTop: '2px' }}>
                              {liveVideoMetrics
                                ? liveVideoMetrics.waitingTimeDisplay
                                : (selectedAnalysis.waiting_time_display ||
                                  (selectedAnalysis.average_waiting_time_seconds !== null && selectedAnalysis.average_waiting_time_seconds !== undefined
                                    ? `${Math.ceil(selectedAnalysis.average_waiting_time_seconds / 60)} min`
                                    : '0 min'))}
                            </div>
                            <div style={{ fontSize: '11px', opacity: 0.8 }}>
                              Whole minutes only
                            </div>
                          </div>
                        </div>

                        {/* Vehicle Breakdown */}
                        <div style={{ border: '1px solid var(--border-subtle)', padding: '12px', marginBottom: '16px' }}>
                          <div style={{ fontSize: '13px', fontWeight: 700, marginBottom: '6px' }}>
                            Vehicles Detected (Boxed): {liveVideoMetrics ? liveVideoMetrics.totalDetected : selectedAnalysis.total_vehicles_detected}
                          </div>
                          <div style={{ display: 'flex', gap: '16px', fontSize: '12px' }}>
                            {(() => {
                              const activeClasses = (liveVideoMetrics && liveVideoMetrics.vehicleClasses && Object.keys(liveVideoMetrics.vehicleClasses).length > 0)
                                ? liveVideoMetrics.vehicleClasses
                                : selectedAnalysis.vehicle_classes_detected;
                              return Object.keys(activeClasses).length === 0 ? (
                                <span>No vehicle classes detected in this footage.</span>
                              ) : (
                                Object.entries(activeClasses).map(([cls, cnt]) => (
                                  <span key={cls}>
                                    <strong>{cls.toUpperCase()}:</strong> {cnt}
                                  </span>
                                ))
                              );
                            })()}
                          </div>
                        </div>

                        {/* Processed Video Stream Player */}
                        {selectedAnalysis.has_processed_video && (
                          <div style={{ marginBottom: '16px' }}>
                            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '6px' }}>
                              <div style={{ fontSize: '13px', fontWeight: 700, display: 'flex', alignItems: 'center', gap: '8px' }}>
                                <span>Processed Video</span>
                                {isPlaying && (
                                  <span style={{ fontSize: '11px', color: '#16a34a', fontWeight: 700, display: 'inline-flex', alignItems: 'center', gap: '4px' }}>
                                    <span style={{ width: '8px', height: '8px', borderRadius: '50%', backgroundColor: '#16a34a', display: 'inline-block' }}></span>
                                    PLAYING ({playbackTime.toFixed(1)}s)
                                  </span>
                                )}
                                {!isPlaying && hasStarted && (
                                  <span style={{ fontSize: '11px', color: '#f59e0b', fontWeight: 700 }}>
                                    PAUSED ({playbackTime.toFixed(1)}s)
                                  </span>
                                )}
                              </div>
                              <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                                <button
                                  type="button"
                                  className="btn btn-secondary"
                                  style={{ padding: '2px 8px', fontSize: '11px', cursor: 'pointer' }}
                                  onClick={handleRestartVideo}
                                  title="Restart video playback from beginning and reset statistics"
                                >
                                  ⏮ Restart Video
                                </button>
                                <button
                                  type="button"
                                  className="btn btn-secondary"
                                  style={{ padding: '2px 8px', fontSize: '11px', cursor: 'pointer' }}
                                  onClick={() => handleReprocessVideo(selectedAnalysis.id)}
                                >
                                  🔄 Re-analyze Video
                                </button>
                                <span className="tag-badge" style={{ margin: 0 }}>RECORDED VIDEO</span>
                              </div>
                            </div>
                            <div style={{ border: '1px solid var(--border-strong)', backgroundColor: 'var(--color-charcoal)' }}>
                              <video
                                ref={videoRef}
                                key={`${selectedAnalysis.id}-${feedTimestamp}`}
                                controls
                                playsInline
                                style={{ width: '100%', maxHeight: '440px', display: 'block' }}
                                src={`http://127.0.0.1:8000/api/stations/${selectedStationId}/video-analyses/${selectedAnalysis.id}/video?token=${encodeURIComponent(token || '')}&t=${feedTimestamp}`}
                                onPlay={handleVideoPlay}
                                onPause={handleVideoPause}
                                onEnded={handleVideoEnded}
                                onTimeUpdate={handleVideoTimeUpdate}
                                onSeeked={handleVideoSeeked}
                                onError={() => {
                                  setVideoError("Unable to load processed video. The file may be missing, incomplete, or unsupported by your browser.");
                                }}
                                onLoadedData={() => {
                                  setVideoError(null);
                                }}
                              />
                            </div>
                            {videoError && (
                              <div className="notice-box" style={{ marginTop: '8px', color: '#ffaaaa', backgroundColor: 'var(--color-charcoal)' }}>
                                ⚠ {videoError}
                              </div>
                            )}
                            <div style={{ fontSize: '11px', marginTop: '6px', opacity: 0.9, display: 'flex', gap: '10px', flexWrap: 'wrap', alignItems: 'center' }}>
                              <span style={{ fontWeight: 700 }}>Vehicle Boxes:</span>
                              <span style={{ color: '#22c55e', fontWeight: 600 }}>● Car (Green)</span>
                              <span style={{ color: '#0ea5e9', fontWeight: 600 }}>● Motorcycle (Blue)</span>
                              <span style={{ color: '#eab308', fontWeight: 600 }}>● Bus (Yellow)</span>
                              <span style={{ color: '#c084fc', fontWeight: 600 }}>● Truck (Purple)</span>
                              <span style={{ color: '#f97316', fontWeight: 600 }}>■ Orange = Queue ROI</span>
                            </div>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      )}

      {/* 3. Time Slot Generation View */}
      {operatorTab === 'slots' && selectedStationId && (
        <div className="card">
          <h3 style={{ fontSize: '15px', fontWeight: 700, marginBottom: '6px' }}>
            Create Booking Slot
          </h3>
          <p style={{ fontSize: '13px', marginBottom: '10px' }}>
            Define time windows with maximum capacity to enforce overbooking prevention.
          </p>
          <form onSubmit={handleCreateSlot} style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '10px' }}>
              <div>
                <label style={{ display: 'block', fontSize: '13px', fontWeight: 600 }}>Start Time:</label>
                <input
                  type="datetime-local"
                  required
                  className="input-field"
                  value={slotStartTime}
                  onChange={(e) => setSlotStartTime(e.target.value)}
                />
              </div>
              <div>
                <label style={{ display: 'block', fontSize: '13px', fontWeight: 600 }}>End Time:</label>
                <input
                  type="datetime-local"
                  required
                  className="input-field"
                  value={slotEndTime}
                  onChange={(e) => setSlotEndTime(e.target.value)}
                />
              </div>
              <div>
                <label style={{ display: 'block', fontSize: '13px', fontWeight: 600 }}>Max Capacity:</label>
                <input
                  type="number"
                  min={1}
                  max={50}
                  className="input-field"
                  value={slotCapacity}
                  onChange={(e) => setSlotCapacity(e.target.value)}
                />
              </div>
            </div>

            {slotMsg && <div className="notice-box">{slotMsg}</div>}

            <button type="submit" className="btn-primary">
              Add Slot
            </button>
          </form>
        </div>
      )}
    </div>
  );
}
