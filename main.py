import requests
import csv
import os
import re
import sys
import time
import urllib3
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

# --- Configuration ---
VERIFIK_API_KEY = os.environ.get("VERIFIK_API_KEY", "YOUR_VERIFIK_API_KEY_HERE")
VERIFIK_API_BASE_URL = "https://api.verifik.co/v1/venezuela/cedula"
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
        print("No data to save.")
        return
    headers = sorted(list(set().union(*(d.keys() for d in data_list))))
    try:
        with open(filename, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=headers, extrasaction='ignore')
            writer.writeheader()
            writer.writerows(data_list)
        print(f"Data saved to '{filename}'")
    except IOError as e:
        print(f"Error saving CSV: {e}")

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

def get_verifik_data(cedula):
    normalized = normalize_cedula(cedula)
    headers = {"Authorization": f"Bearer {VERIFIK_API_KEY}", "Content-Type": "application/json"}
    try:
        resp = requests.get(f"{VERIFIK_API_BASE_URL}/{normalized}", headers=headers, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        return data.get("data") if data.get("success") else None
    except Exception as e:
        print(f"Verifik error for {normalized}: {e}")
        return None

def get_pnp_data(cedula):
    normalized = normalize_cedula(cedula)
    # Según tu captura, el sitio pide solo números
    cedula_numerica = "".join(filter(str.isdigit, normalized))
    
    print(f"\n[DEBUG] >>> INICIANDO CONSULTA: {normalized} <<<")
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        
        try:
            print(f"[DEBUG] [1/5] Navegando a {PNP_BASE_URL}...")
            page.goto(f"{PNP_BASE_URL}{PNP_GET_CAPTCHA_URL_PATH}", wait_until="load", timeout=60000)
            
            # Espera para que los marcos de publicidad no interfieran con la carga del form
            page.wait_for_timeout(4000)
            
            # Localización del frame correcto
            target_frame = None
            print(f"[DEBUG] [2/5] Buscando marco del formulario...")
            
            for i, f in enumerate(page.frames):
                try:
                    # Buscamos el frame que contiene el ID 'form' que vimos en tu captura
                    if f.locator("#form").count() > 0:
                        target_frame = f
                        print(f"[DEBUG] Formulario detectado en Frame index: {i}")
                        break
                except: continue

            if not target_frame:
                print("[ERROR] No se pudo localizar el marco con el formulario.")
                return {"cedula": normalized, "status": "Error: Marco no encontrado"}

            # --- RESOLUCIÓN DE CAPTCHA ---
            print("[DEBUG] [3/5] Localizando texto del Captcha...")
            
            # Intentamos leer específicamente del contenedor de captcha
            captcha_container = target_frame.locator(".captcha-container")
            raw_text = ""
            
            if captcha_container.count() > 0:
                raw_text = captcha_container.inner_text()
                print(f"[DEBUG] Texto leído de .captcha-container: '{raw_text.strip()}'")
            else:
                raw_text = target_frame.inner_text("body")
                print(f"[DEBUG] .captcha-container no hallado, leyendo body: '{raw_text[:50]}...'")

            # Buscamos la operación matemática
            match = re.search(r'(\d+)\s*([+\-*/])\s*(\d+)', raw_text)
            
            if not match:
                print(f"[ERROR] No se pudo encontrar una operación matemática en: '{raw_text}'")
                return {"cedula": normalized, "status": "Error: Captcha no detectado"}
            
            # Extraemos los componentes para el cálculo
            n1, op, n2 = match.group(1), match.group(2), match.group(3)
            print(f"[DEBUG] Operación identificada: {n1} {op} {n2}")
            
            solution = solve_pnp_captcha(f"{n1} {op} {n2}")
            print(f"[DEBUG] RESULTADO CALCULADO: {solution}")

            # --- LLENADO DE CAMPOS ---
            print(f"[DEBUG] [4/5] Llenando formulario...")
            
            # Campo Cédula (Solo números)
            campo_id = target_frame.locator(f'input[name="{PNP_FORM_CEDULA_FIELD}"]')
            print(f"[DEBUG] Escribiendo '{cedula_numerica}' en {PNP_FORM_CEDULA_FIELD}")
            campo_id.fill(cedula_numerica)
            
            # Campo Captcha (Resultado de la operación)
            campo_cap = target_frame.locator(f'input[name="{PNP_FORM_CAPTCHA_FIELD}"]')
            print(f"[DEBUG] Escribiendo '{solution}' en {PNP_FORM_CAPTCHA_FIELD}")
            campo_cap.fill(solution)
            
            # --- ENVÍO ---
            print("[DEBUG] [5/5] Presionando botón Buscar...")
            target_frame.locator("button[type='submit']").click()
            
            # Esperamos a ver el cambio
            page.wait_for_timeout(5000)
            page.screenshot(path=f"debug_resultado_{cedula_numerica}.png")
            
            # Verificación de éxito
            resultado = target_frame.locator(".form-container, .alert").first
            if resultado.is_visible():
                print(f"[SUCCESS] Datos encontrados para {normalized}")
                return {"cedula": normalized, "fuente": "Sistemas PNP", "datos": resultado.inner_text().strip()}
            
            return {"cedula": normalized, "status": "Consulta enviada, esperando respuesta"}

        except Exception as e:
            print(f"[CRITICAL ERROR] {str(e)}")
            return {"cedula": normalized, "status": "Error en proceso"}
        finally:
            browser.close()

# --- Main ---

if __name__ == "__main__":
    print("1. Verifik API\n2. Sistemas PNP (Scraper)")
    choice = input("Choice (1/2): ")
    
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
        if choice == '1':
            res = get_verifik_data(c)
            if res: res['fuente'] = 'Verifik API'
            results.append(res or {"cedula": c, "fuente": "Verifik API", "status": "Error"})
        else:
            results.append(get_pnp_data(c) or {"cedula": c, "fuente": "Sistemas PNP", "status": "Error"})

    save_to_csv(results, OUTPUT_CSV_FILE)
