"""Check MLPClassifier init"""
import inspect
from riid.models import MLPClassifier

print("MLPClassifier.__init__ signature:")
print(inspect.signature(MLPClassifier.__init__))
print()
print("MLPClassifier doc:")
print(MLPClassifier.__doc__)
