"""
Server-Side Acquisition Manager

Manages spectrum acquisition timing independently of the browser.
Provides robust handling for long acquisitions that survive browser throttling,
display sleep, or tab closure.

Author: AlphaHoundGUI
"""

import asyncio
import time
import os
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List
from enum import Enum

from analysis_utils import analyze_spectrum_peaks
from device_calibration import energies_from_device_spectrum, SOURCE_DEVICE, fallback_warning

import logging
logger = logging.getLogger(__name__)


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
    # Exposure during this acquisition, integrated from the instrument's dose-rate readings.
    # Valid regardless of how many sources contributed (unlike isotope identification).
    exposure_uSv: float = 0.0
    exposure_covered_s: float = 0.0
    dose_rate_samples: int = 0
    dose_rate_sum: float = 0.0
    dose_rate_max: Optional[float] = None
    last_dose_rate: Optional[float] = None
    last_dose_time: Optional[float] = None


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
    CHECKPOINT_INTERVAL_S = 5 * 60  # 5 minutes
    
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
        self._instrument: Dict[str, Any] = {}  # e.g. {'instrument_model': 'RadiaCode-110', 'serial_number': ...}
        
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
            "exposure": self.exposure_summary(),
        }
    
    async def start(self, duration_minutes: float, device, source_name: str = "AlphaHound Device",
                    dose_rate_fn=None, instrument: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
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
        self._instrument = {k: v for k, v in (instrument or {}).items() if k != 'source'}
        self._stop_requested = False
        self.state = AcquisitionState(
            status=AcquisitionStatus.ACQUIRING,
            start_time=datetime.now(timezone.utc),
            duration_seconds=duration_minutes * 60,
            elapsed_seconds=0.0
        )
        
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
        last_checkpoint = datetime.now(timezone.utc)
        
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
                time_since_checkpoint = (datetime.now(timezone.utc) - last_checkpoint).total_seconds()
                if time_since_checkpoint >= self.CHECKPOINT_INTERVAL_S:
                    await self._save_checkpoint()
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

    async def _sample_dose_rate(self):
        """Read the instrument's dose rate (off the event loop) and integrate it."""
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
                # A guessed axis is not a calibration (identification is then skipped with a warning)
                self._is_calibrated = (energy_source == SOURCE_DEVICE and
                                       getattr(self._device, "calibration_source", "device") == "device")
                
        except Exception as e:
            logger.error(f"[AcquisitionManager] Poll error: {e}")
    

    
    async def _save_checkpoint(self):
        """Save checkpoint to acquisition_in_progress.n42"""
        if not self.state.last_spectrum_counts:
            return
        
        try:
            from n42_exporter import generate_n42_xml
            
            # Run analysis using common enhanced pipeline
            result = self._analyze()
            
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
                },
                'peaks': result.get('peaks', []),
                'isotopes': result.get('isotopes', [])
            }
            
            # Save to checkpoint file
            save_dir = os.path.join(os.path.dirname(__file__), 'data', 'acquisitions')
            os.makedirs(save_dir, exist_ok=True)
            filepath = os.path.join(save_dir, 'acquisition_in_progress.n42')
            
            n42_content = generate_n42_xml(n42_data)
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(n42_content)
            
            logger.info(f"[AcquisitionManager] Checkpoint saved at {self.state.elapsed_seconds:.0f}s")
            
        except Exception as e:
            logger.error(f"[AcquisitionManager] Checkpoint error: {e}")
    
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
            from n42_exporter import generate_n42_xml
            
            # Run analysis using common enhanced pipeline
            result = self._analyze()
            
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
                },
                'peaks': result.get('peaks', []),
                'isotopes': result.get('isotopes', [])
            }
            
            # Save to timestamped file
            save_dir = os.path.join(os.path.dirname(__file__), 'data', 'acquisitions')
            os.makedirs(save_dir, exist_ok=True)
            
            # Finalize filename
            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            filename = f"spectrum_{timestamp}.n42"
            filepath = os.path.join(save_dir, filename)
            
            n42_content = generate_n42_xml(n42_data)
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(n42_content)
            
            self.state.final_filename = filename
            self.state.status = AcquisitionStatus.COMPLETE if not self._stop_requested else AcquisitionStatus.STOPPED
            
            logger.info(f"[AcquisitionManager] Finalized: {filename} ({self.state.elapsed_seconds:.1f}s)")
            
            # Cleanup checkpoint file
            checkpoint_path = os.path.join(save_dir, 'acquisition_in_progress.n42')
            if os.path.exists(checkpoint_path):
                os.remove(checkpoint_path)
                logger.info("[AcquisitionManager] Checkpoint file cleaned up")
                
        except Exception as e:
            logger.error(f"[AcquisitionManager] Finalize error: {e}")
            self.state.status = AcquisitionStatus.ERROR
            self.state.error_message = str(e)
    
    def _analyze(self) -> Dict[str, Any]:
        """Common analysis of the latest spectrum (source name selects the detector model)."""
        result = {
            'counts': self.state.last_spectrum_counts,
            'energies': self.state.last_spectrum_energies,
            'metadata': {'source': self._source_name, **self._instrument},
        }
        return analyze_spectrum_peaks(result, is_calibrated=self._is_calibrated, live_time=self.state.elapsed_seconds)

    def get_latest_data(self) -> Optional[Dict[str, Any]]:
        """Get latest spectrum data for UI updates"""
        if not self.state.last_spectrum_counts:
            return None
        
        result = self._analyze()
        
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
                'channels': len(self.state.last_spectrum_counts),
                'count_time_minutes': self.state.elapsed_seconds / 60,
                'acquisition_time': self.state.elapsed_seconds,
                'live_time': self.state.elapsed_seconds,
                'real_time': self.state.elapsed_seconds,
                'start_time': self.state.start_time.isoformat() if self.state.start_time else None,
                **self._exposure_metadata(),
            }
        }

    def _exposure_metadata(self) -> Dict[str, Any]:
        e = self.exposure_summary()
        if not e:
            return {}
        return {"exposure_during_acquisition": format_exposure(e)}


def format_exposure(e: Dict[str, Any]) -> str:
    """'0.421 uSv (mean 0.25, max 0.90 uSv/h)' with nSv for small values."""
    def dose(v):
        return f"{v * 1000:.1f} nSv" if v < 1 else f"{v:.3f} \u00b5Sv"
    return (f"{dose(e['exposure_uSv'])} (mean {e['mean_dose_rate_uSv_h']:.3f}, "
            f"max {e['max_dose_rate_uSv_h']:.3f} \u00b5Sv/h)")


# Global singleton instance
acquisition_manager = AcquisitionManager()
