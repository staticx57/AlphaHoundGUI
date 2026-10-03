try:
    import becquerel as bq
    print("Becquerel imported successfully")
except ImportError:
    print("Becquerel NOT found")
    exit(1)

try:
    spec = bq.Spectrum.from_file(r"c:\Users\user\Desktop\N42 viewer\test.n42")
    print(f"Spectrum loaded: {spec}")
    print(f"Live Time: {spec.live_time}")
    print(f"Counts shape: {len(spec.counts)}")
except Exception as e:
    print(f"Error loading file: {e}")
