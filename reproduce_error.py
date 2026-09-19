
import sys
from io import StringIO
from unittest.mock import patch
from main import get_pnp_data

# Simulate the loop behavior
cedulas = ["12345678", "87654321"]
results = []

for c in cedulas:
    print(f"\nProcessing: {c}")
    try:
        res = get_pnp_data(c)
        results.append(res)
        # The line that might cause an issue
        name = res.get('nombre y apellidos')
        print(f"Esta cedula {c} le pertence a {name}")
        print(f"Result for {c}: {res.get('status')}")
    except Exception as e:
        print(f"Error processing {c}: {e}")

print("\nResults:", results)
