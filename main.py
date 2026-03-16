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
    cedula_numerica = "".join(filter(str.isdigit, normalized))
    
    print(f"\n[START] Procesando cédula: {normalized}")
    
    with sync_playwright() as p:
        # Mantenemos visible para inspección en Fedora
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        
        try:
            print(f"[1/5] Navegando a: {PNP_BASE_URL}...")
            page.goto(f"{PNP_BASE_URL}{PNP_GET_CAPTCHA_URL_PATH}", wait_until="load", timeout=60000)
            
            # Espera para carga de scripts e iframes
            page.wait_for_timeout(5000)
            
            # Localización del Frame
            target_frame = None
            print(f"[2/5] Buscando marco del formulario entre {len(page.frames)} marcos...")
            for f in page.frames:
                if f.locator('input[name="txtCedula"]').count() > 0:
                    target_frame = f
                    break
            
            if not target_frame:
                print("[ERROR] No se localizó el frame que contiene 'txtCedula'.")
                return {"cedula": normalized, "status": "Error: Frame no hallado"}

            print(f"[DEBUG] Frame identificado: {target_frame.url[:60]}...")

            # --- DEBUGGING DE CAPTCHA ---
            print("[3/5] Intentando extraer Captcha...")
            
            # Extraemos todo el texto visible del frame para ver qué hay dentro
            full_frame_text = target_frame.inner_text("body")
            print("-" * 30)
            print(f"[DEBUG TEXTO ENCONTRADO]:\n{full_frame_text}")
            print("-" * 30)

            # Intentamos el match con el patrón configurado
            captcha_match = re.search(PNP_CAPTCHA_PATTERN, full_frame_text)
            
            if not captcha_match:
                # Si falla el regex, intentamos buscar por palabras clave
                print("[WARN] El regex estricto falló. Buscando patrones alternativos...")
                # Buscamos cualquier cosa que parezca una operación: "¿Cuánto es X + Y?"
                alt_match = re.search(r'¿Cuánto es\s*(\d+)\s*([+\-*/])\s*(\d+)\s*\?', full_frame_text)
                if alt_match:
                    print(f"[DEBUG] Patrón alternativo encontrado: {alt_match.group(0)}")
                    question = alt_match.group(0)
                else:
                    print("[ERROR] No se encontró texto que parezca una operación matemática.")
                    page.screenshot(path=f"debug_captcha_fail_{normalized}.png")
                    return {"cedula": normalized, "status": "Captcha no detectado"}
            else:
                question = captcha_match.group(1)

            solution = solve_pnp_captcha(question)
            print(f"[DEBUG] Pregunta: '{question}' -> Solución calculada: {solution}")

            # --- LLENADO Y ENVÍO ---
            print("[4/5] Llenando campos...")
            target_frame.fill('input[name="txtCedula"]', cedula_numerica)
            target_frame.fill('input[name="txtCaptcha"]', solution)
            
            print("[5/5] Enviando formulario...")
            target_frame.click("button:has-text('Buscar'), button[type='submit']")
            
            # Espera de resultados
            page.wait_for_timeout(6000)
            
            # Captura final para validar éxito visualmente
            page.screenshot(path=f"resultado_{normalized}.png")
            
            # Intento de extracción de datos
            result_box = target_frame.locator("div.alert, .card-body, table").first
            if result_box.is_visible():
                res_text = result_box.inner_text().strip()
                print(f"[SUCCESS] Datos extraídos correctamente.")
                return {"cedula": normalized, "fuente": "Sistemas PNP", "datos": res_text}
            
            print("[WARN] Formulario enviado pero no se detectó caja de resultados.")
            return {"cedula": normalized, "status": "Enviado - Sin respuesta visible"}

        except Exception as e:
            print(f"[CRITICAL ERROR]: {str(e)}")
            return {"cedula": normalized, "status": f"Error: {type(e).__name__}"}
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
