
from main import solve_pnp_captcha

# Case where it returns None
print(f"Result for '¿Cuánto es 10 / 0?': {solve_pnp_captcha('¿Cuánto es 10 / 0?')}")
print(f"Result for 'invalid': {solve_pnp_captcha('invalid')}")
