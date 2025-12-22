"""
Enhanced Spectrum Wrapper Module
=================================

This module provides an `EnhancedSpectrum` class that wraps `becquerel.Spectrum`
for automatic uncertainty tracking and improved spectral operations.

Falls back to numpy arrays if becquerel is not installed.

Usage:
    from spectrum_wrapper import EnhancedSpectrum
    
    # Create from raw counts
    spec = EnhancedSpectrum.from_counts(counts, energies, livetime=300.0)
    
    # Access uncertainty-aware properties
    print(spec.counts)          # numpy array
    print(spec.counts_unc)      # Poisson uncertainties
    print(spec.bin_centers_kev) # Energy axis
    
    # Arithmetic with automatic uncertainty propagation
    net_spec = spec - background_spec
"""

import numpy as np
from typing import Optional, Union, List, Tuple

# Try to import becquerel
try:
    import becquerel as bq
    from becquerel import Spectrum as BqSpectrum
    HAS_BECQUEREL = True
except ImportError:
    HAS_BECQUEREL = False
    BqSpectrum = None

# Try to import uncertainties package
try:
    from uncertainties import ufloat, UFloat
    from uncertainties.unumpy import uarray
    HAS_UNCERTAINTIES = True
except ImportError:
    HAS_UNCERTAINTIES = False
    ufloat = None
    UFloat = None
    uarray = None


class EnhancedSpectrum:
    """
    Enhanced spectrum class with automatic uncertainty tracking.
    
    Wraps becquerel.Spectrum if available, otherwise provides a lightweight
    numpy-based implementation with manual Poisson uncertainty calculation.
    
    Attributes:
        counts (np.ndarray): Raw counts per bin
        counts_unc (np.ndarray): Poisson uncertainty (sqrt(counts))
        energies (np.ndarray): Energy bin centers (keV)
        bin_edges_kev (np.ndarray): Energy bin edges (keV)
        livetime (float): Live time in seconds
        realtime (float): Real time in seconds
        metadata (dict): Additional metadata
    """
    
    def __init__(
        self,
        counts: np.ndarray,
        energies: Optional[np.ndarray] = None,
        bin_edges_kev: Optional[np.ndarray] = None,
        livetime: float = 1.0,
        realtime: Optional[float] = None,
        metadata: Optional[dict] = None,
        _bq_spectrum: Optional['BqSpectrum'] = None
    ):
        """
        Initialize EnhancedSpectrum.
        
        Args:
            counts: Count data (1D array)
            energies: Energy bin centers (keV). If None, uses channel numbers.
            bin_edges_kev: Energy bin edges (keV). Takes precedence over energies.
            livetime: Live time in seconds
            realtime: Real time in seconds (defaults to livetime)
            metadata: Additional metadata dictionary
            _bq_spectrum: Internal becquerel.Spectrum object (for advanced use)
        """
        self._counts = np.asarray(counts, dtype=float)
        self._livetime = livetime
        self._realtime = realtime if realtime is not None else livetime
        self._metadata = metadata or {}
        self._bq_spectrum = _bq_spectrum
        
        # Handle energy calibration
        if bin_edges_kev is not None:
            self._bin_edges_kev = np.asarray(bin_edges_kev, dtype=float)
            # Calculate bin centers from edges
            self._energies = 0.5 * (self._bin_edges_kev[:-1] + self._bin_edges_kev[1:])
        elif energies is not None:
            self._energies = np.asarray(energies, dtype=float)
            # Estimate bin edges from centers (assume uniform spacing)
            if len(self._energies) > 1:
                dx = self._energies[1] - self._energies[0]
                edges = np.concatenate([
                    [self._energies[0] - dx/2],
                    self._energies[:-1] + dx/2,
                    [self._energies[-1] + dx/2]
                ])
                self._bin_edges_kev = edges
            else:
                self._bin_edges_kev = np.array([0, 1])
        else:
            # Default: channel numbers
            self._energies = np.arange(len(counts), dtype=float)
            self._bin_edges_kev = np.arange(len(counts) + 1, dtype=float)
        
        # Calculate Poisson uncertainties
        self._counts_unc = np.sqrt(np.maximum(self._counts, 1))
    
    # =========================================================================
    # Factory Methods
    # =========================================================================
    
    @classmethod
    def from_counts(
        cls,
        counts: Union[List, np.ndarray],
        energies: Optional[Union[List, np.ndarray]] = None,
        livetime: float = 1.0,
        realtime: Optional[float] = None,
        metadata: Optional[dict] = None
    ) -> 'EnhancedSpectrum':
        """
        Create an EnhancedSpectrum from raw count data.
        
        Args:
            counts: Count data (list or array)
            energies: Energy bin centers in keV (optional)
            livetime: Live time in seconds
            realtime: Real time in seconds (optional)
            metadata: Additional metadata
            
        Returns:
            EnhancedSpectrum instance
        """
        counts_arr = np.asarray(counts, dtype=float)
        energies_arr = np.asarray(energies, dtype=float) if energies is not None else None
        
        # Try to use becquerel if available
        bq_spec = None
        if HAS_BECQUEREL and energies_arr is not None:
            try:
                # becquerel needs bin_edges, not centers
                if len(energies_arr) > 1:
                    dx = energies_arr[1] - energies_arr[0]
                    bin_edges = np.concatenate([
                        [energies_arr[0] - dx/2],
                        energies_arr[:-1] + dx/2,
                        [energies_arr[-1] + dx/2]
                    ])
                else:
                    bin_edges = np.array([0, 1])
                
                bq_spec = BqSpectrum(
                    counts=counts_arr,
                    bin_edges_kev=bin_edges,
                    livetime=livetime
                )
            except Exception as e:
                print(f"[EnhancedSpectrum] Becquerel init failed, using numpy: {e}")
                bq_spec = None
        
        return cls(
            counts=counts_arr,
            energies=energies_arr,
            livetime=livetime,
            realtime=realtime,
            metadata=metadata,
            _bq_spectrum=bq_spec
        )
    
    @classmethod
    def from_n42_data(
        cls,
        n42_dict: dict
    ) -> 'EnhancedSpectrum':
        """
        Create an EnhancedSpectrum from parsed N42 data.
        
        Args:
            n42_dict: Dictionary from parse_n42() with 'counts', 'energies', 'metadata'
            
        Returns:
            EnhancedSpectrum instance
        """
        counts = n42_dict.get('counts', [])
        energies = n42_dict.get('energies', None)
        metadata = n42_dict.get('metadata', {})
        livetime = metadata.get('live_time', 1.0)
        realtime = metadata.get('real_time', livetime)
        
        return cls.from_counts(
            counts=counts,
            energies=energies,
            livetime=livetime,
            realtime=realtime,
            metadata=metadata
        )
    
    # =========================================================================
    # Properties
    # =========================================================================
    
    @property
    def counts(self) -> np.ndarray:
        """Raw counts per bin."""
        if self._bq_spectrum is not None:
            return np.asarray(self._bq_spectrum.counts)
        return self._counts
    
    @property
    def counts_unc(self) -> np.ndarray:
        """Poisson uncertainty per bin (sqrt(counts))."""
        if self._bq_spectrum is not None and hasattr(self._bq_spectrum, 'counts_uncs'):
            return np.asarray(self._bq_spectrum.counts_uncs)
        return self._counts_unc
    
    @property
    def bin_centers_kev(self) -> np.ndarray:
        """Energy bin centers in keV."""
        if self._bq_spectrum is not None:
            return np.asarray(self._bq_spectrum.bin_centers_kev)
        return self._energies
    
    @property
    def bin_edges_kev(self) -> np.ndarray:
        """Energy bin edges in keV."""
        if self._bq_spectrum is not None:
            return np.asarray(self._bq_spectrum.bin_edges_kev)
        return self._bin_edges_kev
    
    @property
    def energies(self) -> np.ndarray:
        """Alias for bin_centers_kev (backward compatibility)."""
        return self.bin_centers_kev
    
    @property
    def livetime(self) -> float:
        """Live time in seconds."""
        if self._bq_spectrum is not None:
            return self._bq_spectrum.livetime
        return self._livetime
    
    @property
    def realtime(self) -> float:
        """Real time in seconds."""
        return self._realtime
    
    @property
    def metadata(self) -> dict:
        """Additional metadata."""
        return self._metadata
    
    @property
    def cps(self) -> np.ndarray:
        """Counts per second (livetime-normalized)."""
        if self.livetime > 0:
            return self.counts / self.livetime
        return self.counts
    
    @property
    def cps_unc(self) -> np.ndarray:
        """CPS uncertainty."""
        if self.livetime > 0:
            return self.counts_unc / self.livetime
        return self.counts_unc
    
    @property
    def total_counts(self) -> float:
        """Sum of all counts."""
        return float(np.sum(self.counts))
    
    @property
    def has_becquerel(self) -> bool:
        """Whether this spectrum is backed by becquerel."""
        return self._bq_spectrum is not None
    
    # =========================================================================
    # Arithmetic Operations (with uncertainty propagation)
    # =========================================================================
    
    def __add__(self, other: 'EnhancedSpectrum') -> 'EnhancedSpectrum':
        """Add two spectra with uncertainty propagation."""
        if not isinstance(other, EnhancedSpectrum):
            raise TypeError("Can only add EnhancedSpectrum to EnhancedSpectrum")
        
        # If both have becquerel, use becquerel arithmetic
        if self._bq_spectrum is not None and other._bq_spectrum is not None:
            try:
                result_bq = self._bq_spectrum + other._bq_spectrum
                return EnhancedSpectrum(
                    counts=np.asarray(result_bq.counts),
                    bin_edges_kev=np.asarray(result_bq.bin_edges_kev),
                    livetime=result_bq.livetime,
                    _bq_spectrum=result_bq
                )
            except Exception:
                pass  # Fall through to manual calculation
        
        # Manual addition with uncertainty propagation
        new_counts = self.counts + other.counts
        new_unc = np.sqrt(self.counts_unc**2 + other.counts_unc**2)
        
        return EnhancedSpectrum(
            counts=new_counts,
            energies=self.energies.copy(),
            livetime=self.livetime + other.livetime
        )
    
    def __sub__(self, other: 'EnhancedSpectrum') -> 'EnhancedSpectrum':
        """Subtract spectra with uncertainty propagation."""
        if not isinstance(other, EnhancedSpectrum):
            raise TypeError("Can only subtract EnhancedSpectrum from EnhancedSpectrum")
        
        # If both have becquerel, use becquerel arithmetic
        if self._bq_spectrum is not None and other._bq_spectrum is not None:
            try:
                result_bq = self._bq_spectrum - other._bq_spectrum
                return EnhancedSpectrum(
                    counts=np.asarray(result_bq.counts),
                    bin_edges_kev=np.asarray(result_bq.bin_edges_kev),
                    livetime=result_bq.livetime,
                    _bq_spectrum=result_bq
                )
            except Exception:
                pass  # Fall through to manual calculation
        
        # Manual subtraction with uncertainty propagation
        new_counts = self.counts - other.counts
        new_unc = np.sqrt(self.counts_unc**2 + other.counts_unc**2)
        
        # Clamp negative values to 0
        new_counts = np.maximum(new_counts, 0)
        
        return EnhancedSpectrum(
            counts=new_counts,
            energies=self.energies.copy(),
            livetime=self.livetime
        )
    
    # =========================================================================
    # Utility Methods
    # =========================================================================
    
    def rebin(self, new_edges: np.ndarray) -> 'EnhancedSpectrum':
        """
        Rebin spectrum to new energy bin edges.
        
        Args:
            new_edges: New bin edges in keV
            
        Returns:
            Rebinned EnhancedSpectrum
        """
        if self._bq_spectrum is not None:
            try:
                rebinned = self._bq_spectrum.rebin(new_edges)
                return EnhancedSpectrum(
                    counts=np.asarray(rebinned.counts),
                    bin_edges_kev=np.asarray(rebinned.bin_edges_kev),
                    livetime=rebinned.livetime,
                    _bq_spectrum=rebinned
                )
            except Exception as e:
                print(f"[EnhancedSpectrum] Becquerel rebin failed: {e}")
        
        # Manual rebinning (simplified - preserves total counts)
        new_edges = np.asarray(new_edges)
        n_new_bins = len(new_edges) - 1
        new_counts = np.zeros(n_new_bins)
        
        for i in range(n_new_bins):
            mask = (self.bin_centers_kev >= new_edges[i]) & (self.bin_centers_kev < new_edges[i+1])
            new_counts[i] = np.sum(self.counts[mask])
        
        return EnhancedSpectrum(
            counts=new_counts,
            bin_edges_kev=new_edges,
            livetime=self.livetime,
            metadata=self.metadata.copy()
        )
    
    def to_dict(self) -> dict:
        """
        Convert to dictionary format (for API responses).
        
        Returns:
            Dictionary with counts, energies, and metadata
        """
        return {
            'counts': self.counts.tolist(),
            'energies': self.energies.tolist(),
            'counts_unc': self.counts_unc.tolist(),
            'livetime': self.livetime,
            'realtime': self.realtime,
            'metadata': self.metadata,
            'total_counts': self.total_counts,
            'has_becquerel': self.has_becquerel
        }
    
    def __repr__(self) -> str:
        backend = "becquerel" if self.has_becquerel else "numpy"
        return f"EnhancedSpectrum({len(self.counts)} bins, {self.total_counts:.0f} counts, {self.livetime:.1f}s, backend={backend})"
    
    def __len__(self) -> int:
        return len(self.counts)


# =============================================================================
# Utility Functions with Uncertainty Support
# =============================================================================

def format_with_uncertainty(value: float, uncertainty: float, precision: int = 2) -> str:
    """
    Format a value with its uncertainty using ± notation.
    
    Args:
        value: Central value
        uncertainty: Uncertainty (1-sigma)
        precision: Number of decimal places
        
    Returns:
        Formatted string like "662.5 ± 0.3"
    """
    if HAS_UNCERTAINTIES:
        u = ufloat(value, uncertainty)
        return f"{u:.{precision}uS}"  # Short format with uncertainties
    else:
        return f"{value:.{precision}f} ± {uncertainty:.{precision}f}"


def counts_with_uncertainty(counts: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """
    Calculate Poisson uncertainty for count data.
    
    Args:
        counts: Count array
        
    Returns:
        Tuple of (counts, uncertainties)
    """
    counts = np.asarray(counts, dtype=float)
    unc = np.sqrt(np.maximum(counts, 1))
    return counts, unc
