"""
Real Spectrum Data Loader for ML Training

Loads real gamma spectra from N42, SPE, and CSV files to augment
synthetic training data for improved isotope identification.

Sources:
- Local acquisitions (data/acquisitions/*.n42)
- OpenGammaProject database (when downloaded)
- Community shared spectra
"""

import numpy as np
from pathlib import Path
from typing import List, Tuple, Dict, Optional
import xml.etree.ElementTree as ET
import re
import struct


class RealSpectrumLoader:
    """Load and parse real gamma spectra for ML training."""
    
    def __init__(self, base_dir: str = None):
        """Initialize loader with base directory.
        
        Args:
            base_dir: Base directory containing spectrum files.
                     Defaults to backend/data directory.
        """
        if base_dir is None:
            base_dir = Path(__file__).parent / "data"
        self.base_dir = Path(base_dir)
        
    def load_n42_spectrum(self, filepath: Path) -> Tuple[Optional[np.ndarray], Optional[str], Dict]:
        """Load spectrum from N42 XML file.
        
        Returns:
            Tuple of (counts_array, primary_isotope_label, metadata_dict)
        """
        try:
            tree = ET.parse(filepath)
            root = tree.getroot()
            
            # Handle namespace if present
            ns = ''
            if root.tag.startswith('{'):
                ns = root.tag.split('}')[0] + '}'
            
            # Find ChannelData element
            channel_data = None
            for elem in root.iter():
                if 'ChannelData' in elem.tag:
                    channel_data = elem.text
                    break
            
            if not channel_data:
                return None, None, {}
            
            # Parse counts - handle space/newline separated values
            counts_text = channel_data.strip()
            counts = np.array([int(x) for x in counts_text.split()], dtype=float)
            
            # Extract isotope identifications
            isotopes = []
            for elem in root.iter():
                if 'IsotopeIdentification' in elem.tag or 'Nuclide' in elem.tag:
                    isotope_name = None
                    confidence = 0
                    
                    for child in elem:
                        if 'IsotopeName' in child.tag or 'NuclideName' in child.tag:
                            isotope_name = child.text
                        if 'Confidence' in child.tag or 'NuclideIDConfidence' in child.tag:
                            try:
                                confidence = float(child.text)
                            except:
                                confidence = 50
                    
                    if isotope_name:
                        isotopes.append((isotope_name, confidence))
            
            # Sort by confidence, get primary isotope
            isotopes.sort(key=lambda x: x[1], reverse=True)
            primary_isotope = isotopes[0][0] if isotopes else None
            
            # Extract metadata
            metadata = {
                'filename': filepath.name,
                'isotopes': isotopes,
                'channels': len(counts),
                'total_counts': int(counts.sum())
            }
            
            # Try to get live time
            for elem in root.iter():
                if 'LiveTime' in elem.tag or 'RealTime' in elem.tag:
                    try:
                        # Handle PT format (PT600S) or plain seconds
                        time_text = elem.text.strip()
                        if time_text.startswith('PT') and time_text.endswith('S'):
                            metadata['live_time'] = float(time_text[2:-1])
                        else:
                            metadata['live_time'] = float(time_text)
                    except:
                        pass
            
            return counts, primary_isotope, metadata
            
        except Exception as e:
            print(f"[ML Loader] Error loading {filepath}: {e}")
            return None, None, {}
    
    def load_spe_spectrum(self, filepath: Path) -> Tuple[Optional[np.ndarray], Optional[str], Dict]:
        """Load spectrum from Ortec SPE file format.
        
        SPE files have a simple text format:
        $SPEC_ID:
        <description>
        $DATA:
        0 <num_channels-1>
        <count0>
        <count1>
        ...
        """
        try:
            with open(filepath, 'r') as f:
                content = f.read()
            
            # Find $DATA section
            data_match = re.search(r'\$DATA:\s*\n\s*\d+\s+(\d+)\s*\n([\d\s\n]+)', content)
            if not data_match:
                return None, None, {}
            
            counts_text = data_match.group(2).strip()
            counts = np.array([int(x) for x in counts_text.split()], dtype=float)
            
            # Try to extract isotope from filename
            # Common patterns: Cs-137.spe, Co60.spe, Am241_calibration.spe
            filename = filepath.stem
            isotope_patterns = [
                r'(Cs-?137)', r'(Co-?60)', r'(Am-?241)', r'(Ba-?133)',
                r'(Na-?22)', r'(Eu-?152)', r'(U-?238)', r'(Th-?232)',
                r'(Ra-?226)', r'(K-?40)', r'(I-?131)', r'(Sr-?90)'
            ]
            
            primary_isotope = None
            for pattern in isotope_patterns:
                match = re.search(pattern, filename, re.IGNORECASE)
                if match:
                    # Normalize format: add hyphen if missing
                    iso = match.group(1)
                    if '-' not in iso:
                        iso = re.sub(r'(\D+)(\d+)', r'\1-\2', iso)
                    primary_isotope = iso
                    break
            
            metadata = {
                'filename': filepath.name,
                'channels': len(counts),
                'total_counts': int(counts.sum()),
                'format': 'SPE'
            }
            
            return counts, primary_isotope, metadata
            
        except Exception as e:
            print(f"[ML Loader] Error loading SPE {filepath}: {e}")
            return None, None, {}
    
    def load_csv_spectrum(self, filepath: Path) -> Tuple[Optional[np.ndarray], Optional[str], Dict]:
        """Load spectrum from CSV file (energy,counts format)."""
        try:
            counts_list = []
            with open(filepath, 'r') as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue
                    parts = line.split(',')
                    if len(parts) >= 2:
                        try:
                            counts_list.append(float(parts[1]))
                        except:
                            continue
            
            if not counts_list:
                return None, None, {}
            
            counts = np.array(counts_list, dtype=float)
            
            # Extract isotope from filename
            filename = filepath.stem
            primary_isotope = self._extract_isotope_from_filename(filename)
            
            metadata = {
                'filename': filepath.name,
                'channels': len(counts),
                'total_counts': int(counts.sum()),
                'format': 'CSV'
            }
            
            return counts, primary_isotope, metadata
            
        except Exception as e:
            print(f"[ML Loader] Error loading CSV {filepath}: {e}")
            return None, None, {}
    
    def _extract_isotope_from_filename(self, filename: str) -> Optional[str]:
        """Try to extract isotope name from filename."""
        # Common isotope patterns
        patterns = {
            r'uranium|u-?238|u238': 'U-238',
            r'u-?235|u235': 'U-235',
            r'thorium|th-?232|th232': 'Th-232',
            r'cesium|cs-?137|cs137': 'Cs-137',
            r'cobalt|co-?60|co60': 'Co-60',
            r'americium|am-?241|am241': 'Am-241',
            r'barium|ba-?133|ba133': 'Ba-133',
            r'sodium|na-?22|na22': 'Na-22',
            r'potassium|k-?40|k40': 'K-40',
            r'radium|ra-?226|ra226': 'Ra-226',
            r'bismuth|bi-?214|bi214': 'Bi-214',
            r'europium|eu-?152|eu152': 'Eu-152',
            r'iodine|i-?131|i131': 'I-131',
            r'fiesta|vaseline|uranium.?glass': 'UraniumGlass',
            r'mantle|thoriated': 'ThoriumMantle',
            r'radium.?dial|watch': 'RadiumDial',
            r'background|bg': 'Background'
        }
        
        filename_lower = filename.lower()
        for pattern, isotope in patterns.items():
            if re.search(pattern, filename_lower):
                return isotope
        
        return None
    
    def load_all_from_directory(self, directory: Path = None, 
                                 extensions: List[str] = None) -> List[Tuple[np.ndarray, str, Dict]]:
        """Load all spectrum files from a directory.
        
        Args:
            directory: Directory to scan. Defaults to data/acquisitions
            extensions: File extensions to load. Defaults to ['.n42', '.spe', '.csv']
            
        Returns:
            List of (counts, label, metadata) tuples
        """
        if directory is None:
            directory = self.base_dir / "acquisitions"
        
        if extensions is None:
            extensions = ['.n42', '.xml', '.spe', '.csv']
        
        directory = Path(directory)
        if not directory.exists():
            print(f"[ML Loader] Directory not found: {directory}")
            return []
        
        results = []
        
        for ext in extensions:
            for filepath in directory.glob(f"*{ext}"):
                if ext in ['.n42', '.xml']:
                    counts, label, meta = self.load_n42_spectrum(filepath)
                elif ext == '.spe':
                    counts, label, meta = self.load_spe_spectrum(filepath)
                elif ext == '.csv':
                    counts, label, meta = self.load_csv_spectrum(filepath)
                else:
                    continue
                
                if counts is not None and len(counts) > 100:
                    # Only include spectra with labels or enough counts to be useful
                    if label or meta.get('total_counts', 0) > 1000:
                        results.append((counts, label, meta))
        
        print(f"[ML Loader] Loaded {len(results)} spectra from {directory}")
        return results
    
    def prepare_training_data(self, spectra: List[Tuple[np.ndarray, str, Dict]], 
                              target_channels: int = 1024,
                              augment_count: int = 10) -> Tuple[np.ndarray, List[str]]:
        """Prepare loaded spectra for ML training with augmentation.
        
        Args:
            spectra: List of (counts, label, metadata) tuples
            target_channels: Number of channels to normalize to
            augment_count: Number of augmented copies per spectrum
            
        Returns:
            Tuple of (spectra_matrix, labels_list)
        """
        augmented_spectra = []
        augmented_labels = []
        
        for counts, label, meta in spectra:
            if label is None:
                continue  # Skip unlabeled spectra
            
            # Resize to target channel count
            if len(counts) != target_channels:
                # Resample using interpolation
                x_old = np.linspace(0, 1, len(counts))
                x_new = np.linspace(0, 1, target_channels)
                counts = np.interp(x_new, x_old, counts)
            
            # Create augmented copies with noise variation
            for _ in range(augment_count):
                # Add Poisson-like noise variation
                noise_factor = np.random.uniform(0.95, 1.05)
                augmented = counts * noise_factor
                
                # Add small random noise
                noise = np.random.poisson(np.maximum(1, augmented * 0.02))
                augmented = augmented + noise
                
                # Randomly scale intensity (simulates different acquisition times)
                scale = np.random.uniform(0.5, 2.0)
                augmented = augmented * scale
                
                augmented_spectra.append(augmented)
                augmented_labels.append(label)
        
        if not augmented_spectra:
            return np.array([]), []
        
        spectra_matrix = np.array(augmented_spectra)
        
        print(f"[ML Loader] Prepared {len(augmented_labels)} augmented training samples")
        return spectra_matrix, augmented_labels


# Module-level convenience function
def load_real_training_data(data_dir: str = None, 
                            target_channels: int = 1024,
                            augment_count: int = 10) -> Tuple[np.ndarray, List[str]]:
    """Load and prepare real spectra for ML training.
    
    Args:
        data_dir: Directory containing spectrum files
        target_channels: Number of channels to normalize to
        augment_count: Augmentation multiplier per spectrum
        
    Returns:
        Tuple of (spectra_matrix, labels_list)
    """
    loader = RealSpectrumLoader(data_dir)
    spectra = loader.load_all_from_directory()
    return loader.prepare_training_data(spectra, target_channels, augment_count)


if __name__ == "__main__":
    # Test the loader
    loader = RealSpectrumLoader()
    
    # Load from acquisitions directory
    spectra = loader.load_all_from_directory()
    
    print(f"\nLoaded {len(spectra)} spectra:")
    for counts, label, meta in spectra[:5]:
        print(f"  - {meta['filename']}: {len(counts)} channels, label={label}")
    
    # Prepare for training
    if spectra:
        X, y = loader.prepare_training_data(spectra, target_channels=1024, augment_count=10)
        print(f"\nTraining data shape: {X.shape}")
        print(f"Labels: {set(y)}")
