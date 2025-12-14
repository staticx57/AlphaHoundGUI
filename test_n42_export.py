"""
Test N42 export in isolation to debug serialization error
"""
import sys
sys.path.insert(0, 'backend')

from n42_exporter import generate_n42_xml

# Test data
test_data = {
    'counts': [10, 20, 30, 40, 50],
    'energies': [0.0, 10.0, 20.0, 30.0, 40.0],
    'metadata': {
        'live_time': 60.0,
        'real_time': 60.0,
        'start_time': '2024-12-14T14:00:00Z'
    }
}

print("Testing N42 export...")
try:
    xml = generate_n42_xml(test_data)
    print(f"✓ XML generated: {len(xml)} characters")
    print("\nFirst 500 chars:")
    print(xml[:500])
    
    # Test encoding
    xml_bytes = xml.encode('utf-8')
    print(f"\n✓ Encoded to {len(xml_bytes)} bytes")
    
    # Save to file
    with open('test_export.n42', 'w', encoding='utf-8') as f:
        f.write(xml)
    print("\n✓ Saved to test_export.n42")
    
except Exception as e:
    print(f"\n✗ Error: {e}")
    import traceback
    traceback.print_exc()
