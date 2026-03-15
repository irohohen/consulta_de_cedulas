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
    # Limpiamos la cédula para que sea solo números si el sitio así lo requiere
    # según el placeholder "Solo números" de tu captura
    cedula_numerica = re.sub(r'\D', '', normalized)
    
    print(f"\n[DEBUG] Iniciando proceso para: {normalized}")
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False) # Mantenlo visible para validar
        context = browser.new_context(viewport={'width': 1280, 'height': 720})
        page = context.new_page()
        
        try:
            print(f"[DEBUG] Navegando a {PNP_BASE_URL}...")
            page.goto(f"{PNP_BASE_URL}{PNP_GET_CAPTCHA_URL_PATH}", wait_until="load")
            
            # --- NUEVA LÓGICA DE IFRAMES ---
            print("[DEBUG] Buscando el marco del formulario...")
            # Esperamos un poco a que los iframes carguen
            page.wait_for_timeout(3000)
            
            # Intentamos encontrar el frame que contiene el input 'txtCedula'
            frame = None
            for f in page.frames:
                if "cedula" in f.url or f.name == "frame_nombre_aqui": # Ajustar si conocemos el nombre
                    frame = f
                    break
            
            # Si no lo encontramos por URL/Nombre, usamos el que tenga el input
            if not frame:
                for f in page.frames:
                    try:
                        if f.locator(f'input[name="{PNP_FORM_CEDULA_FIELD}"]').count() > 0:
                            frame = f
                            print(f"[DEBUG] Frame encontrado por contenido: {f.url}")
                            break
                    except: continue

            if not frame:
                # Si falla lo anterior, trabajamos sobre la página principal (por si no era iframe)
                frame = page
                print("[WARN] No se detectó iframe, usando página principal.")

            # --- INTERACCIÓN CON EL FRAME ---
            input_cedula = frame.locator(f'input[name="{PNP_FORM_CEDULA_FIELD}"]')
            input_cedula.wait_for(state="visible", timeout=10000)
            
            # Resolver Captcha
            body_text = frame.inner_text("body")
            captcha_match = re.search(PNP_CAPTCHA_PATTERN, body_text)
            
            if not captcha_match:
                return {"cedula": normalized, "status": "Captcha no hallado en frame"}
            
            question = captcha_match.group(1)
            solution = solve_pnp_captcha(question)
            print(f"[DEBUG] Pregunta: {question} -> Solución: {solution}")

            # Llenar datos
            input_cedula.fill(cedula_numerica) # Usamos solo números según tu captura
            frame.fill(f'input[name="{PNP_FORM_CAPTCHA_FIELD}"]', solution)
            
            print("[DEBUG] Enviando formulario...")
            frame.click("button:has-text('Buscar'), button[type='submit']")
            
            # Esperar resultado dentro del frame
            page.wait_for_timeout(5000)
            
            # Extraer resultado (ajustar selector si es necesario)
            # Usamos evaluate para obtener el HTML del frame
            soup = BeautifulSoup(frame.evaluate("document.documentElement.outerHTML"), 'html.parser')
            # Buscamos el texto que aparezca después del click
            results = frame.locator("div.alert, .card-body").first
            
            if results.is_visible():
                return {"cedula": normalized, "fuente": "Sistemas PNP", "datos": results.inner_text().strip()}
            
            return {"cedula": normalized, "status": "Consulta realizada, sin datos visibles"}

        except Exception as e:
            page.screenshot(path=f"debug_frame_{normalized}.png")
            print(f"[ERROR] {str(e)}")
            return {"cedula": normalized, "status": f"Error de Frame"}
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
