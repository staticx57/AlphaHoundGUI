"""
Server-Side Acquisition Manager

Manages spectrum acquisition timing independently of the browser.
Provides robust handling for long acquisitions that survive browser throttling,
display sleep, or tab closure.

Author: AlphaHoundGUI
"""

import asyncio
import math
import time
import os
from datetime import datetime, timezone
from dataclasses import dataclass
from typing import Optional, Dict, Any, List
from enum import Enum

from spectroscopy.analysis_utils import analyze_spectrum_peaks
from devices.device_calibration import energies_from_device_spectrum, SOURCE_DEVICE, fallback_warning

import logging
logger = logging.getLogger(__name__)

# Saved spectra. A run writes spectrum_<start>_in_progress.n42 from its first spectrum on and replaces it with the final
# spectrum_<end>.n42 when it ends; a partial file left behind (crash, restart, power loss) is kept as ..._interrupted.n42.
SAVE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'acquisitions')
IN_PROGRESS_SUFFIX = "_in_progress.n42"
INTERRUPTED_SUFFIX = "_interrupted.n42"
LEGACY_CHECKPOINT = "acquisition_in_progress.n42"  # the single shared file of earlier versions
# Older than this, no server is writing the partial file. A run here rewrites it every minute, but another server on the
# same folder may run older code that did so every 5 minutes (a test server once relabelled a live run's file at 3 min).
STALE_CHECKPOINT_S = 15 * 60


def _unused_name(save_dir: str, name: str) -> str:
    """name, or name with _2, _3 ... before the extension when a file of that name already exists."""
    stem, ext = os.path.splitext(name)
    candidate, n = name, 2
    while os.path.exists(os.path.join(save_dir, candidate)):
        candidate, n = f"{stem}_{n}{ext}", n + 1
    return candidate


def recover_interrupted_checkpoints(save_dir: Optional[str] = None, stale_s: float = STALE_CHECKPOINT_S) -> List[str]:
    """Renames partial files no acquisition is writing any more to ..._interrupted.n42 and returns the new names.

    A partial file written in the last stale_s seconds is left alone: another server instance may still own it.
    """
    save_dir = save_dir or SAVE_DIR
    if not os.path.isdir(save_dir):
        return []
    kept, now = [], time.time()
    for name in sorted(os.listdir(save_dir)):
        if not (name == LEGACY_CHECKPOINT or name.endswith(IN_PROGRESS_SUFFIX)):
            continue
        path = os.path.join(save_dir, name)
        try:
            mtime = os.path.getmtime(path)
            if now - mtime < stale_s:
                continue
            if name == LEGACY_CHECKPOINT:
                target = f"spectrum_{datetime.fromtimestamp(mtime).strftime('%Y-%m-%d_%H-%M-%S')}{INTERRUPTED_SUFFIX}"
            else:
                target = name[:-len(IN_PROGRESS_SUFFIX)] + INTERRUPTED_SUFFIX
            target = _unused_name(save_dir, target)
            os.rename(path, os.path.join(save_dir, target))
        except OSError as e:
            logger.error(f"[AcquisitionManager] Could not keep interrupted run {name}: {e}")
            continue
        logger.warning(f"[AcquisitionManager] Kept an interrupted acquisition as {target}")
        kept.append(target)
    return kept


def _write_atomic(path: str, text: str) -> None:
    """Writes text to path through a temporary file, so a crash mid-write cannot leave a truncated spectrum."""
    tmp = path + ".tmp"
    with open(tmp, 'w', encoding='utf-8') as f:
        f.write(text)
    os.replace(tmp, path)


class AcquisitionStatus(str, Enum):
    """Acquisition lifecycle states"""
    IDLE = "idle"
    ACQUIRING = "acquiring"
    FINALIZING = "finalizing"
    COMPLETE = "complete"
    STOPPED = "stopped"
    ERROR = "error"


@dataclass
class AcquisitionState:
    """Current state of an acquisition"""
    status: AcquisitionStatus = AcquisitionStatus.IDLE
    start_time: Optional[datetime] = None
    duration_seconds: float = 0.0
    elapsed_seconds: float = 0.0
    last_checkpoint_time: Optional[datetime] = None
    last_spectrum_counts: Optional[List[int]] = None
    last_spectrum_energies: Optional[List[float]] = None
    error_message: Optional[str] = None
    final_filename: Optional[str] = None
    checkpoint_filename: Optional[str] = None  # this run's partial file, named by its start time
    # Exposure during this acquisition, integrated from the instrument's dose-rate readings.
    # Valid regardless of how many sources contributed (unlike isotope identification).
    exposure_uSv: float = 0.0
    exposure_covered_s: float = 0.0
    dose_rate_samples: int = 0
    dose_rate_sum: float = 0.0
    dose_rate_max: Optional[float] = None
    last_dose_rate: Optional[float] = None
    last_dose_time: Optional[float] = None
    device_duration_s: Optional[float] = None  # accumulation time as reported by the instrument
    # Instrument temperature (deg C) and its own temperature compensation factor, as last reported (the AlphaHound sends them with a spectrum)
    temperature_c: Optional[float] = None
    temperature_min_c: Optional[float] = None
    temperature_max_c: Optional[float] = None
    compensation_factor: Optional[float] = None
    # Per-channel count rates seen during this acquisition (AlphaHound AB+G: gamma / beta / alpha)
    cps_samples: int = 0
    cps_sum_gamma: float = 0.0
    cps_sum_beta: float = 0.0
    cps_sum_alpha: float = 0.0
    cps_max_total: Optional[float] = None


class AcquisitionManager:
    """
    Singleton manager for server-side acquisition timing.
    
    Runs an asyncio background task that:
    - Polls the device every 2 seconds
    - Saves checkpoints every 5 minutes
    - Auto-finalizes when duration expires
    - Handles stop requests gracefully
    """
    
    _instance: Optional['AcquisitionManager'] = None
    
    # Configuration
    POLL_INTERVAL_S = 2.0
    CHECKPOINT_INTERVAL_S = 60  # at most a minute of counts is lost if the server stops mid-run
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        
        self.state = AcquisitionState()
        self._task: Optional[asyncio.Task] = None
        self._stop_requested = False
        self._device = None  # Will be set when acquisition starts
        self._source_name = "AlphaHound Device"
        self._is_calibrated = True
        self._dose_rate_fn = None  # callable -> dose rate in uSv/h (or None)
        self._cps_fn = None  # callable -> {'gamma', 'beta', 'alpha'} counts per second (or None)
        self._instrument: Dict[str, Any] = {}  # e.g. {'instrument_model': 'RadiaCode-110', 'serial_number': ...}
        # (counts, energies, is_calibrated, result) of the last analysis: polls of an unchanged spectrum reuse it
        self._analysis_cache = None
        self._analysis_lock: Optional[asyncio.Lock] = None
        self._analysis_lock_loop = None
        
    def get_state(self) -> Dict[str, Any]:
        """Get current acquisition state as dict for API response"""
        return {
            "status": self.state.status.value,
            "is_active": self.state.status == AcquisitionStatus.ACQUIRING,
            "start_time": self.state.start_time.isoformat() if self.state.start_time else None,
            "duration_seconds": self.state.duration_seconds,
            "elapsed_seconds": self.state.elapsed_seconds,
            "remaining_seconds": max(0, self.state.duration_seconds - self.state.elapsed_seconds),
            "progress_percent": (self.state.elapsed_seconds / self.state.duration_seconds * 100) if self.state.duration_seconds > 0 else 0,
            "last_checkpoint": self.state.last_checkpoint_time.isoformat() if self.state.last_checkpoint_time else None,
            "error": self.state.error_message,
            "final_filename": self.state.final_filename,
            "checkpoint_file": self.state.checkpoint_filename,
            "exposure": self.exposure_summary(),
            "channels": self.channel_summary(),
        }
    
    async def start(self, duration_minutes: float, device, source_name: str = "AlphaHound Device",
                    dose_rate_fn=None, instrument: Optional[Dict[str, Any]] = None,
                    cps_fn=None) -> Dict[str, Any]:
        """
        Start a managed acquisition.
        
        Args:
            duration_minutes: How long to acquire (in minutes)
            device: object with is_connected / clear_spectrum / request_spectrum /
                    get_spectrum() -> [(count, energy_keV), ...] (AlphaHound driver or an adapter)
            source_name: label used in results (also selects the detector model for analysis)
            dose_rate_fn: optional callable returning the current dose rate in uSv/h; sampled
                          every poll and integrated into the exposure for this acquisition
            
        Returns:
            Status dict
        """
        if self.state.status == AcquisitionStatus.ACQUIRING:
            return {"success": False, "error": "Acquisition already in progress"}
        
        if not device.is_connected():
            return {"success": False, "error": "Device not connected"}
        
        # Initialize state
        self._device = device
        self._source_name = source_name
        self._is_calibrated = True
        self._dose_rate_fn = dose_rate_fn
        self._cps_fn = cps_fn
        self._instrument = {k: v for k, v in (instrument or {}).items() if k != 'source'}
        self._stop_requested = False
        self.state = AcquisitionState(
            status=AcquisitionStatus.ACQUIRING,
            start_time=datetime.now(timezone.utc),
            duration_seconds=duration_minutes * 60,
            elapsed_seconds=0.0
        )
        
        await asyncio.to_thread(recover_interrupted_checkpoints)
        self._record_device_readings()    # what the instrument last reported, before the run
        # Clear device spectrum (device I/O can block, e.g. Bluetooth: keep it off the event loop)
        await asyncio.to_thread(device.clear_spectrum)
        
        # Start background task
        self._task = asyncio.create_task(self._acquisition_loop())
        
        logger.info(f"[AcquisitionManager] Started {duration_minutes} minute acquisition")
        return {"success": True, "message": f"Acquisition started for {duration_minutes} minutes"}
    
    async def stop(self) -> Dict[str, Any]:
        """
        Stop current acquisition and finalize.
        
        Returns:
            Status dict with final filename
        """
        if self.state.status != AcquisitionStatus.ACQUIRING:
            return {"success": False, "error": "No acquisition in progress"}
        
        self._stop_requested = True
        
        # Wait for task to finish (with timeout)
        if self._task:
            try:
                await asyncio.wait_for(self._task, timeout=10.0)
            except asyncio.TimeoutError:
                logger.info("[AcquisitionManager] Stop timeout, cancelling task")
                self._task.cancel()
        
        return {
            "success": True,
            "status": self.state.status.value,
            "final_filename": self.state.final_filename,
            "elapsed_seconds": self.state.elapsed_seconds
        }
    
    async def _acquisition_loop(self):
        """Main acquisition loop - runs as background task"""
        last_checkpoint = None  # the first spectrum is saved at once: a run cut short early still leaves a file
        
        try:
            while not self._stop_requested:
                # Update elapsed time
                self.state.elapsed_seconds = (datetime.now(timezone.utc) - self.state.start_time).total_seconds()
                
                # Check if duration expired
                if self.state.elapsed_seconds >= self.state.duration_seconds:
                    logger.info(f"[AcquisitionManager] Duration complete: {self.state.elapsed_seconds:.1f}s")
                    break
                
                # Sample dose rate (exposure) and poll spectrum from device
                await self._sample_dose_rate()
                await self._poll_spectrum()
                
                # Checkpoint save
                due = last_checkpoint is None or \
                    (datetime.now(timezone.utc) - last_checkpoint).total_seconds() >= self.CHECKPOINT_INTERVAL_S
                if due and await self._save_checkpoint():
                    last_checkpoint = datetime.now(timezone.utc)
                    self.state.last_checkpoint_time = last_checkpoint
                
                # Wait for next poll
                await asyncio.sleep(self.POLL_INTERVAL_S)
            
            # Finalize
            await self._finalize()
            
        except asyncio.CancelledError:
            logger.info("[AcquisitionManager] Acquisition cancelled")
            self.state.status = AcquisitionStatus.STOPPED
        except Exception as e:
            logger.error(f"[AcquisitionManager] Error: {e}")
            self.state.status = AcquisitionStatus.ERROR
            self.state.error_message = str(e)
    
    MAX_DOSE_GAP_S = 10.0  # don't integrate across longer gaps in dose-rate readings

    async def _sample_cps(self):
        """Read the per-channel count rates, when the device has them, and accumulate their statistics."""
        if not self._cps_fn:
            return
        try:
            cps = await asyncio.to_thread(self._cps_fn)
        except Exception as e:
            logger.warning(f"[AcquisitionManager] CPS read failed: {e}")
            return
        self.record_cps(cps)

    def record_cps(self, cps: Optional[Dict[str, float]]):
        st = self.state
        try:
            g, b, a = float(cps['gamma']), float(cps['beta']), float(cps['alpha'])
        except (TypeError, KeyError, ValueError):
            return
        if not all(v >= 0 and v != float("inf") for v in (g, b, a)):
            return
        st.cps_samples += 1
        st.cps_sum_gamma += g
        st.cps_sum_beta += b
        st.cps_sum_alpha += a
        total = g + b + a
        st.cps_max_total = total if st.cps_max_total is None else max(st.cps_max_total, total)

    def channel_summary(self) -> Optional[Dict[str, Any]]:
        st = self.state
        if not self._cps_fn or st.cps_samples == 0:
            return None
        n = st.cps_samples
        return {
            "mean_cps_gamma": round(st.cps_sum_gamma / n, 3),
            "mean_cps_beta": round(st.cps_sum_beta / n, 3),
            "mean_cps_alpha": round(st.cps_sum_alpha / n, 3),
            "max_cps_total": round(st.cps_max_total or 0.0, 3),
            "samples": n,
        }

    async def _sample_dose_rate(self):
        """Read the instrument's dose rate (off the event loop) and integrate it."""
        await self._sample_cps()
        if not self._dose_rate_fn:
            return
        try:
            rate = await asyncio.to_thread(self._dose_rate_fn)
        except Exception as e:
            logger.warning(f"[AcquisitionManager] Dose-rate read failed: {e}")
            return
        self.record_dose_rate(rate, time.monotonic())

    def record_dose_rate(self, rate_uSv_h: Optional[float], now_s: float):
        """Trapezoid-integrate dose rate (uSv/h) between consecutive readings <= MAX_DOSE_GAP_S apart."""
        st = self.state
        if rate_uSv_h is None or not (rate_uSv_h >= 0) or rate_uSv_h == float("inf"):
            return
        if st.last_dose_rate is not None and st.last_dose_time is not None:
            dt = now_s - st.last_dose_time
            if 0 < dt <= self.MAX_DOSE_GAP_S:
                st.exposure_uSv += 0.5 * (st.last_dose_rate + rate_uSv_h) * dt / 3600.0
                st.exposure_covered_s += dt
        st.last_dose_rate, st.last_dose_time = rate_uSv_h, now_s
        st.dose_rate_samples += 1
        st.dose_rate_sum += rate_uSv_h
        st.dose_rate_max = rate_uSv_h if st.dose_rate_max is None else max(st.dose_rate_max, rate_uSv_h)

    def exposure_summary(self) -> Optional[Dict[str, Any]]:
        st = self.state
        if not self._dose_rate_fn or st.dose_rate_samples == 0:
            return None
        return {
            "exposure_uSv": round(st.exposure_uSv, 6),
            "mean_dose_rate_uSv_h": round(st.dose_rate_sum / st.dose_rate_samples, 6),
            "max_dose_rate_uSv_h": round(st.dose_rate_max or 0.0, 6),
            "covered_seconds": round(st.exposure_covered_s, 1),
            "samples": st.dose_rate_samples,
            "method": "integrated instrument dose rate",
        }

    async def _poll_spectrum(self):
        """Request and store current spectrum from device"""
        if not self._device or not self._device.is_connected():
            return
        
        try:
            # Request spectrum
            await asyncio.to_thread(self._device.request_spectrum)
            
            # Wait for spectrum to be collected
            await asyncio.sleep(0.5)
            max_wait = 5.0
            waited = 0.0
            while waited < max_wait:
                spectrum = await asyncio.to_thread(self._device.get_spectrum)
                if len(spectrum) >= 1024:
                    break
                await asyncio.sleep(0.5)
                waited += 0.5
            
            # Store spectrum data
            spectrum = await asyncio.to_thread(self._device.get_spectrum)
            if spectrum:
                self.state.last_spectrum_counts = [int(count) for count, energy in spectrum]
                # Use the device's own (nonlinear) energy axis; linear fallback only if unusable
                self.state.last_spectrum_energies, energy_source = energies_from_device_spectrum(spectrum)
                if energy_source != SOURCE_DEVICE:
                    logger.warning("[AcquisitionManager] " + fallback_warning())
                self._record_device_readings()
                dur = getattr(self._device, 'device_duration_s', None)
                if isinstance(dur, (int, float)) and dur >= 0:
                    self.state.device_duration_s = float(dur)
                # A guessed axis is not a calibration (identification is then skipped with a warning)
                self._is_calibrated = (energy_source == SOURCE_DEVICE and
                                       getattr(self._device, "calibration_source", "device") == "device")
                
        except Exception as e:
            logger.error(f"[AcquisitionManager] Poll error: {e}")
    

    
    def _checkpoint_name(self) -> str:
        start = self.state.start_time or datetime.now(timezone.utc)
        return f"spectrum_{start.astimezone().strftime('%Y-%m-%d_%H-%M-%S')}{IN_PROGRESS_SUFFIX}"

    async def _save_checkpoint(self) -> bool:
        """Saves the spectrum so far to this run's partial file. Returns whether it was written."""
        if not self.state.last_spectrum_counts:
            return False
        
        try:
            from formats.n42_exporter import generate_n42_xml
            
            # Run analysis using common enhanced pipeline
            result = await self._analyze_off_loop()
            
            # Build N42 data
            n42_data = {
                'counts': self.state.last_spectrum_counts,
                'energies': self.state.last_spectrum_energies,
                'metadata': {
                    'live_time': self.state.elapsed_seconds,
                    'real_time': self.state.elapsed_seconds,
                    'start_time': self.state.start_time.isoformat(),
                    'source': self._source_name,
                    **self._instrument,
                    **self._exposure_metadata(),
                    **self._device_metadata(),
                },
                'peaks': result.get('peaks', []),
                'isotopes': result.get('isotopes', [])
            }
            
            # Save to this run's partial file
            os.makedirs(SAVE_DIR, exist_ok=True)
            name = self._checkpoint_name()
            n42_content = generate_n42_xml(n42_data)
            await asyncio.to_thread(_write_atomic, os.path.join(SAVE_DIR, name), n42_content)
            self.state.checkpoint_filename = name

            logger.info(f"[AcquisitionManager] Checkpoint saved at {self.state.elapsed_seconds:.0f}s: {name}")
            return True

        except Exception as e:
            logger.error(f"[AcquisitionManager] Checkpoint error: {e}")
            return False
    
    async def _finalize(self):
        """Finalize acquisition - save final file and cleanup"""
        self.state.status = AcquisitionStatus.FINALIZING
        
        # Final dose-rate sample and spectrum poll
        await self._sample_dose_rate()
        await self._poll_spectrum()
        
        if not self.state.last_spectrum_counts:
            self.state.status = AcquisitionStatus.ERROR
            self.state.error_message = "No spectrum data collected"
            return
        
        try:
            from formats.n42_exporter import generate_n42_xml
            
            # Run analysis using common enhanced pipeline
            result = await self._analyze_off_loop()
            
            # Build N42 data
            n42_data = {
                'counts': self.state.last_spectrum_counts,
                'energies': self.state.last_spectrum_energies,
                'metadata': {
                    'live_time': self.state.elapsed_seconds,
                    'real_time': self.state.elapsed_seconds,
                    'start_time': self.state.start_time.isoformat(),
                    'source': self._source_name,
                    **self._instrument,
                    **self._exposure_metadata(),
                    **self._device_metadata(),
                },
                'peaks': result.get('peaks', []),
                'isotopes': result.get('isotopes', [])
            }
            
            # Save to timestamped file
            save_dir = SAVE_DIR
            os.makedirs(save_dir, exist_ok=True)
            
            # Finalize filename
            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            filename = f"spectrum_{timestamp}.n42"
            filepath = os.path.join(save_dir, filename)
            
            n42_content = generate_n42_xml(n42_data)
            await asyncio.to_thread(_write_atomic, filepath, n42_content)

            self.state.final_filename = filename
            self.state.status = AcquisitionStatus.COMPLETE if not self._stop_requested else AcquisitionStatus.STOPPED
            
            logger.info(f"[AcquisitionManager] Finalized: {filename} ({self.state.elapsed_seconds:.1f}s)")
            
            # The final file is written: the partial one is no longer needed (kept if anything above failed)
            if self.state.checkpoint_filename:
                checkpoint_path = os.path.join(save_dir, self.state.checkpoint_filename)
                if os.path.exists(checkpoint_path):
                    os.remove(checkpoint_path)
                    logger.info(f"[AcquisitionManager] Partial file {self.state.checkpoint_filename} replaced by {filename}")
                
        except Exception as e:
            logger.error(f"[AcquisitionManager] Finalize error: {e}")
            self.state.status = AcquisitionStatus.ERROR
            self.state.error_message = str(e)
    
    def _analyze(self) -> Dict[str, Any]:
        """Common analysis of the latest spectrum (source name selects the detector model).

        Cached per spectrum: each poll stores new lists, so an unchanged spectrum is analysed once.
        """
        counts, energies, calibrated = self.state.last_spectrum_counts, self.state.last_spectrum_energies, self._is_calibrated
        cached = self._analysis_cache
        if cached and cached[0] is counts and cached[1] is energies and cached[2] == calibrated:
            return cached[3]
        result = {
            'counts': counts,
            'energies': energies,
            'metadata': {'source': self._source_name, **self._instrument},
        }
        result = analyze_spectrum_peaks(result, is_calibrated=calibrated, live_time=self.state.elapsed_seconds)
        self._analysis_cache = (counts, energies, calibrated, result)
        return result

    async def _analyze_off_loop(self) -> Dict[str, Any]:
        """_analyze in a worker thread, one at a time. A long acquisition's analysis takes seconds
        (2 s at 600k counts), which on the event loop starved the acquisition and every request."""
        loop = asyncio.get_running_loop()
        if self._analysis_lock_loop is not loop:
            self._analysis_lock, self._analysis_lock_loop = asyncio.Lock(), loop
        async with self._analysis_lock:
            return await asyncio.to_thread(self._analyze)

    def get_latest_data(self) -> Optional[Dict[str, Any]]:
        """Get latest spectrum data for UI updates (analyses on the calling thread)"""
        if not self.state.last_spectrum_counts:
            return None
        return self._latest_data(self._analyze())

    async def latest_data(self) -> Optional[Dict[str, Any]]:
        """get_latest_data for request handlers: the analysis runs off the event loop"""
        if not self.state.last_spectrum_counts:
            return None
        return self._latest_data(await self._analyze_off_loop())

    def _latest_data(self, result: Dict[str, Any]) -> Dict[str, Any]:
        return {
            'counts': result['counts'],
            'energies': result['energies'],
            'peaks': result.get('peaks', []),
            'isotopes': result.get('isotopes', []),
            'decay_chains': result.get('decay_chains', []),
            'is_calibrated': self._is_calibrated,
            'warnings': result.get('warnings', []),
            'exposure': self.exposure_summary(),
            'display_min_keV': result.get('display_min_keV'),
            'metadata': {
                'source': self._source_name,
                **self._instrument,
                **self._device_metadata(),
                'channels': len(self.state.last_spectrum_counts),
                'count_time_minutes': self.state.elapsed_seconds / 60,
                'acquisition_time': self.state.elapsed_seconds,
                'live_time': self.state.elapsed_seconds,
                'real_time': self.state.elapsed_seconds,
                'start_time': self.state.start_time.isoformat() if self.state.start_time else None,
                **self._exposure_metadata(),
                **self._time_metadata(),
            }
        }

    TIME_NOTES = (
        "Real time is the wall-clock time since the acquisition started. Live time is the time the "
        "detector could count (real time minus dead time); neither supported instrument reports dead "
        "time, so live time is taken to equal real time. Device duration is the accumulation time "
        "reported by the instrument itself, shown as an independent check."
    )

    def _time_metadata(self) -> Dict[str, Any]:
        """Explains the time fields and adds the instrument-reported duration when available."""
        out = {"time_notes": self.TIME_NOTES}
        if self.state.device_duration_s is not None:
            out["device_duration_s"] = round(self.state.device_duration_s, 1)
        return out

    def _channel_metadata(self) -> Dict[str, Any]:
        c = self.channel_summary()
        if not c:
            return {}
        return {k: c[k] for k in ("mean_cps_gamma", "mean_cps_beta", "mean_cps_alpha", "max_cps_total")}

    def record_device_readings(self, temperature_c, compensation_factor=None) -> None:
        """Keep the instrument's temperature (latest, lowest, highest) and compensation factor; unusable readings are ignored."""
        st = self.state
        if _is_reading(temperature_c):
            t = float(temperature_c)
            st.temperature_c = t
            st.temperature_min_c = t if st.temperature_min_c is None else min(st.temperature_min_c, t)
            st.temperature_max_c = t if st.temperature_max_c is None else max(st.temperature_max_c, t)
        if _is_reading(compensation_factor):
            st.compensation_factor = float(compensation_factor)

    def _record_device_readings(self) -> None:
        """From the device object, when it has them (the AlphaHound driver does; the Radiacode adapter does not)."""
        self.record_device_readings(getattr(self._device, 'temperature', None), getattr(self._device, 'comp_factor', None))

    def _device_metadata(self) -> Dict[str, Any]:
        """The readings seen during this run, for the spectrum's metadata: how far the axis can be trusted depends on them."""
        st = self.state
        out = {'temperature_c': st.temperature_c, 'temperature_min_c': st.temperature_min_c,
               'temperature_max_c': st.temperature_max_c, 'compensation_factor': st.compensation_factor}
        return {k: round(v, 4) for k, v in out.items() if v is not None}

    def _exposure_metadata(self) -> Dict[str, Any]:
        e = self.exposure_summary()
        if not e:
            return self._channel_metadata()
        return {
            **self._channel_metadata(),
            "exposure_during_acquisition": format_exposure(e),
            "exposure_uSv": e["exposure_uSv"],
            "mean_dose_rate_uSv_h": e["mean_dose_rate_uSv_h"],
            "max_dose_rate_uSv_h": e["max_dose_rate_uSv_h"],
            "exposure_covered_s": e["covered_seconds"],
            "exposure_method": e["method"],
        }


def _is_reading(value) -> bool:
    """A finite number (a bool is an int to Python but never a reading)."""
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def format_exposure(e: Dict[str, Any]) -> str:
    """'0.421 uSv (mean 0.25, max 0.90 uSv/h)' with nSv for small values."""
    def dose(v):
        return f"{v * 1000:.1f} nSv" if v < 1 else f"{v:.3f} \u00b5Sv"
    return (f"{dose(e['exposure_uSv'])} (mean {e['mean_dose_rate_uSv_h']:.3f}, "
            f"max {e['max_dose_rate_uSv_h']:.3f} \u00b5Sv/h)")


# Global singleton instance
acquisition_manager = AcquisitionManager()
