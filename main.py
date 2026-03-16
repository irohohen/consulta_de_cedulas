import csv
import os
import re
from playwright.sync_api import sync_playwright

# --- Configuration ---
OUTPUT_CSV_FILE = "cedula_data.csv"
PNP_BASE_URL = "https://www.sistemaspnp.com"
PNP_GET_CAPTCHA_URL_PATH = "/cedula/"
PNP_CAPTCHA_PATTERN = r'(¿Cuánto es \d+\s*[+\-*/]\s*\d+\?)'
PNP_FORM_CEDULA_FIELD = "txtCedula"
PNP_FORM_CAPTCHA_FIELD = "txtCaptcha"

# --- Helpers ---

def normalize_cedula(cedula):
    cedula = str(cedula).strip().upper()
    return cedula if '-' in cedula else f"V-{cedula}"

def save_to_csv(data_list, filename):
    if not data_list:
        return
    headers = sorted(list(set().union(*(d.keys() for d in data_list))))
    with open(filename, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        writer.writerows(data_list)
    print(f"Data saved to '{filename}'")

def solve_pnp_captcha(question):
    match = re.search(r'(\d+)\s*([+\-*/])\s*(\d+)', question)
    if not match: return None
    n1, op, n2 = int(match.group(1)), match.group(2), int(match.group(3))
    try:
        if op == '+': return str(n1 + n2)
        if op == '-': return str(n1 - n2)
        if op == '*': return str(n1 * n2)
        if op == '/': return str(n1 // n2) if n2 != 0 else None
    except: return None
    return None

# --- Data Fetching ---

def get_pnp_data(cedula):
    normalized = normalize_cedula(cedula)
    cedula_numerica = "".join(filter(str.isdigit, normalized))

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        try:
            page.goto(f"{PNP_BASE_URL}{PNP_GET_CAPTCHA_URL_PATH}", wait_until="load", timeout=60000)
            page.wait_for_timeout(3000)

            target_frame = None
            for f in page.frames:
                if f.locator("#form").count() > 0:
                    target_frame = f
                    break

            if not target_frame:
                return {"cedula": normalized, "status": "Error: Frame not found"}

            captcha_text = target_frame.locator(".captcha-container").inner_text()
            match = re.search(r'(\d+)\s*([+\-*/])\s*(\d+)', captcha_text)

            if not match:
                return {"cedula": normalized, "status": "Error: Captcha not found"}

            solution = solve_pnp_captcha(match.group(0))
            
            target_frame.locator('input[name*="edula"]').first.fill(cedula_numerica)
            target_frame.locator('input[name*="aptcha"]').first.fill(solution)
            target_frame.locator("button[type='submit'], button:has-text('Buscar')").click()
            
            page.wait_for_timeout(3000)

            tarjetas = target_frame.locator(".card")
            if tarjetas.count() > 0:
                return {
                    "cedula": normalized,
                    "datos": tarjetas.nth(0).inner_text().strip().replace("\n", " | "),
                    "status": "Success"
                }
            
            return {"cedula": normalized, "status": "No data found"}

        except Exception as e:
            return {"cedula": normalized, "status": f"Error: {str(e)}"}
        finally:
            browser.close()

# --- Main ---

if __name__ == "__main__":
    print("1. Manual\n2. File")
    input_type = input("Input (1/2): ")
    
    cedulas = []
    if input_type == '1':
        while True:
            c = input("Cedula (Enter to finish): ").strip()
            if not c: break
            cedulas.append(c)
    else:
        fname = input("File path: ")
        try:
            with open(fname, 'r', encoding='utf-8') as f:
                cedulas = [line.strip() for line in f if line.strip()]
        except Exception as e: print(f"File error: {e}")

    results = []
    for c in cedulas:
        print(f"Processing: {c}")
        results.append(get_pnp_data(c))

    save_to_csv(results, OUTPUT_CSV_FILE)
