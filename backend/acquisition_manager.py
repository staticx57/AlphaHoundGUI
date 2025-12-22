"""
Server-Side Acquisition Manager

Manages spectrum acquisition timing independently of the browser.
Provides robust handling for long acquisitions that survive browser throttling,
display sleep, or tab closure.

Author: AlphaHoundGUI
"""

import asyncio
import os
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List
from enum import Enum

from analysis_utils import analyze_spectrum_peaks


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
            "final_filename": self.state.final_filename
        }
    
    async def start(self, duration_minutes: float, device) -> Dict[str, Any]:
        """
        Start a managed acquisition.
        
        Args:
            duration_minutes: How long to acquire (in minutes)
            device: AlphaHoundDevice instance
            
        Returns:
            Status dict
        """
        if self.state.status == AcquisitionStatus.ACQUIRING:
            return {"success": False, "error": "Acquisition already in progress"}
        
        if not device.is_connected():
            return {"success": False, "error": "Device not connected"}
        
        # Initialize state
        self._device = device
        self._stop_requested = False
        self.state = AcquisitionState(
            status=AcquisitionStatus.ACQUIRING,
            start_time=datetime.now(timezone.utc),
            duration_seconds=duration_minutes * 60,
            elapsed_seconds=0.0
        )
        
        # Clear device spectrum
        device.clear_spectrum()
        
        # Start background task
        self._task = asyncio.create_task(self._acquisition_loop())
        
        print(f"[AcquisitionManager] Started {duration_minutes} minute acquisition")
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
                print("[AcquisitionManager] Stop timeout, cancelling task")
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
                    print(f"[AcquisitionManager] Duration complete: {self.state.elapsed_seconds:.1f}s")
                    break
                
                # Poll spectrum from device
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
            print("[AcquisitionManager] Acquisition cancelled")
            self.state.status = AcquisitionStatus.STOPPED
        except Exception as e:
            print(f"[AcquisitionManager] Error: {e}")
            self.state.status = AcquisitionStatus.ERROR
            self.state.error_message = str(e)
    
    async def _poll_spectrum(self):
        """Request and store current spectrum from device"""
        if not self._device or not self._device.is_connected():
            return
        
        try:
            # Request spectrum
            self._device.request_spectrum()
            
            # Wait for spectrum to be collected
            await asyncio.sleep(0.5)
            max_wait = 5.0
            waited = 0.0
            while waited < max_wait:
                spectrum = self._device.get_spectrum()
                if len(spectrum) >= 1024:
                    break
                await asyncio.sleep(0.5)
                waited += 0.5
            
            # Store spectrum data
            spectrum = self._device.get_spectrum()
            if spectrum:
                self.state.last_spectrum_counts = [int(count) for count, energy in spectrum]
                # Use forced 3.0 keV/channel calibration (matches device.py)
                self.state.last_spectrum_energies = [i * 3.0 for i in range(len(self.state.last_spectrum_counts))]
                
        except Exception as e:
            print(f"[AcquisitionManager] Poll error: {e}")
    

    
    async def _save_checkpoint(self):
        """Save checkpoint to acquisition_in_progress.n42"""
        if not self.state.last_spectrum_counts:
            return
        
        try:
            from n42_exporter import generate_n42_xml
            
            # Run analysis using common enhanced pipeline
            result = {
                'counts': self.state.last_spectrum_counts,
                'energies': self.state.last_spectrum_energies
            }
            result = analyze_spectrum_peaks(result, is_calibrated=True, live_time=self.state.elapsed_seconds)
            
            # Build N42 data
            n42_data = {
                'counts': self.state.last_spectrum_counts,
                'energies': self.state.last_spectrum_energies,
                'metadata': {
                    'live_time': self.state.elapsed_seconds,
                    'real_time': self.state.elapsed_seconds,
                    'start_time': self.state.start_time.isoformat()
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
            
            print(f"[AcquisitionManager] Checkpoint saved at {self.state.elapsed_seconds:.0f}s")
            
        except Exception as e:
            print(f"[AcquisitionManager] Checkpoint error: {e}")
    
    async def _finalize(self):
        """Finalize acquisition - save final file and cleanup"""
        self.state.status = AcquisitionStatus.FINALIZING
        
        # Final spectrum poll
        await self._poll_spectrum()
        
        if not self.state.last_spectrum_counts:
            self.state.status = AcquisitionStatus.ERROR
            self.state.error_message = "No spectrum data collected"
            return
        
        try:
            from n42_exporter import generate_n42_xml
            
            # Run analysis using common enhanced pipeline
            result = {
                'counts': self.state.last_spectrum_counts,
                'energies': self.state.last_spectrum_energies
            }
            result = analyze_spectrum_peaks(result, is_calibrated=True, live_time=self.state.elapsed_seconds)
            
            # Build N42 data
            n42_data = {
                'counts': self.state.last_spectrum_counts,
                'energies': self.state.last_spectrum_energies,
                'metadata': {
                    'live_time': self.state.elapsed_seconds,
                    'real_time': self.state.elapsed_seconds,
                    'start_time': self.state.start_time.isoformat()
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
            
            print(f"[AcquisitionManager] Finalized: {filename} ({self.state.elapsed_seconds:.1f}s)")
            
            # Cleanup checkpoint file
            checkpoint_path = os.path.join(save_dir, 'acquisition_in_progress.n42')
            if os.path.exists(checkpoint_path):
                os.remove(checkpoint_path)
                print("[AcquisitionManager] Checkpoint file cleaned up")
                
        except Exception as e:
            print(f"[AcquisitionManager] Finalize error: {e}")
            self.state.status = AcquisitionStatus.ERROR
            self.state.error_message = str(e)
    
    def get_latest_data(self) -> Optional[Dict[str, Any]]:
        """Get latest spectrum data for UI updates"""
        if not self.state.last_spectrum_counts:
            return None
        
        # Run analysis using common enhanced pipeline
        result = {
            'counts': self.state.last_spectrum_counts,
            'energies': self.state.last_spectrum_energies
        }
        result = analyze_spectrum_peaks(result, is_calibrated=True, live_time=self.state.elapsed_seconds)
        
        return {
            'counts': result['counts'],
            'energies': result['energies'],
            'peaks': result.get('peaks', []),
            'isotopes': result.get('isotopes', []),
            'decay_chains': result.get('decay_chains', []),
            'metadata': {
                'source': 'AlphaHound Device',
                'channels': len(self.state.last_spectrum_counts),
                'count_time_minutes': self.state.elapsed_seconds / 60,
                'acquisition_time': self.state.elapsed_seconds,
                'live_time': self.state.elapsed_seconds,
                'real_time': self.state.elapsed_seconds,
                'start_time': self.state.start_time.isoformat() if self.state.start_time else None
            }
        }


# Global singleton instance
acquisition_manager = AcquisitionManager()
