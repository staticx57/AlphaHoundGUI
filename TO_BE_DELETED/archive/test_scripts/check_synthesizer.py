"""
Check Synthesizer API
"""
import inspect
from riid.data.synthetic import Synthesizer

print("Synthesizer __init__ signature:")
print(inspect.signature(Synthesizer.__init__))
print()

print("Synthesizer documentation:")
print(Synthesizer.__doc__)
