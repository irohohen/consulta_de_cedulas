import csv
import os
import re
import time
import json
from playwright.sync_api import sync_playwright

# --- Configuration ---
OUTPUT_CSV_FILE = "cedula_data.csv"
OUTPUT_JSON_FILE = "cedula_data.json"
PNP_BASE_URL = "https://www.sistemaspnp.com"
PNP_GET_CAPTCHA_URL_PATH = "/cedula/"
PNP_CAPTCHA_PATTERN = r'(¿Cuánto es \d+\s*[+\-*/]\s*\d+\?)'
PNP_FORM_CEDULA_FIELD = "txtCedula"
PNP_FORM_CAPTCHA_FIELD = "txtCaptcha"

# --- Helpers ---

def normalize_cedula(cedula):
    cedula = str(cedula).strip().upper()
    return cedula if '-' in cedula else f"V-{cedula}"

def parse_datos(datos_string):
    # Extract fields using regex
    primer_apellido = re.search(r'Primer Apellido:\s*([^|]+)', datos_string)
    segundo_apellido = re.search(r'Segundo Apellido:\s*([^|]+)', datos_string)
    nombres = re.search(r'Nombres:\s*([^|]+)', datos_string)
    cedula = re.search(r'Cédula:\s*(\d+)', datos_string)
    
    p_ap = primer_apellido.group(1).strip() if primer_apellido else ""
    s_ap = segundo_apellido.group(1).strip() if segundo_apellido else ""
    nom = nombres.group(1).strip() if nombres else ""
    ced = cedula.group(1).strip() if cedula else ""
    
    return {
        "nombre y apellidos": f"{nom} {p_ap} {s_ap}".strip(),
        "cedula": ced
    }

def save_to_csv(data_list, filename):
    if not data_list:
        return
    
    # Filter only successful results
    success_data = [d for d in data_list if d.get("status") == "Success"]
    
    with open(filename, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=["numero correlativo", "nombre y apellidos", "cedula"])
        writer.writeheader()
        for i, item in enumerate(success_data, 1):
            writer.writerow({
                "numero correlativo": i,
                "nombre y apellidos": item.get("nombre y apellidos", ""),
                "cedula": item.get("cedula", "")
            })
    print(f"CSV saved to '{filename}'")

def save_to_json(data_list, filename):
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(data_list, f, indent=4, ensure_ascii=False)
    print(f"JSON saved to '{filename}'")

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
            #page.wait_for_timeout(3000)

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
                datos_raw = tarjetas.nth(0).inner_text().strip().replace("\n", " | ")
                parsed = parse_datos(datos_raw)
                return {
                    "nombre y apellidos": parsed["nombre y apellidos"],
                    "cedula": parsed["cedula"],
                    "status": "Success"
                }
            
            return {"cedula": normalized, "status": "No data found"}

        except Exception as e:
            return {"cedula": normalized, "status": f"Error: {str(e)}"}
        finally:
            browser.close()

def limpiar(): os.system('clear')
# --- Main ---

if __name__ == "__main__":
    limpiar()
    while True:
        print("Bienvenido")
        print("\n1. Manual\n2. File\n3. Salir (o presionar enter)")
        input_type = input("\nInput (1/2/3): ")
        print("")
    
        cedulas = []

        if input_type == '1':
            while True:
                c = input("Cedula (Enter to finish): ").strip()
                if not c: break
                cedulas.append(c)
        elif input_type == '2':
            fname = input("File path: ")
            try:
                with open(fname, 'r', encoding='utf-8') as f:
                    cedulas = [line.strip() for line in f if line.strip()]
            except Exception as e: print(f"\nFile error: {e}")
        elif input_type == '3' or not input_type:
            print("\nGracias por usar el programa")
            break
        else:
            print("\nError, intente de nuevo")

        results = []
        start_total = time.time()
        for c in cedulas:
            print(f"\nProcessing: {c}")
            start_id = time.time()
            res = get_pnp_data(c)
            results.append(res)
            end_id = time.time()
            print(f"Esta cedula {c} le pertence a {res.get('nombre y apellidos')}")
            print(f"Result for {c}: {res.get('status')} (Time: {end_id - start_id:.2f}s)")
    
        end_total = time.time()
        print(f"\nTotal time: {end_total - start_total:.2f} seconds\n")

        save_to_csv(results, OUTPUT_CSV_FILE)
        save_to_json(results, OUTPUT_JSON_FILE)
        input("\nEnter para continuar...")
        limpiar()
