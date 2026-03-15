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
    # Extraemos solo los números, ya que la captura dice "* Solo números"
    cedula_numerica = "".join(filter(str.isdigit, normalized))
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False) # Verás la ventana para debug
        page = browser.new_page()
        
        try:
            page.goto(f"{PNP_BASE_URL}{PNP_GET_CAPTCHA_URL_PATH}", wait_until="load")
            page.wait_for_timeout(3000) # Tiempo para que cargue el iframe

            # BUSCAR EL MARCO CORRECTO
            target_frame = None
            for frame in page.frames:
                # Intentamos detectar el marco que contenga ALGÚN input
                if frame.locator("input").count() > 0:
                    target_frame = frame
                    break
            
            if not target_frame:
                print("No se encontró el marco del formulario.")
                return {"cedula": normalized, "status": "No se encontró el marco del formulario."}

            # INTERACTUAR DENTRO DEL MARCO
            # Usamos selectores más genéricos por si 'txtCedula' no es exacto
            input_selector = 'input[name*="Cedula"], input[placeholder*="cédula"]'
            target_frame.wait_for_selector(input_selector, timeout=10000)
            
            # Resolver Captcha y llenar
            content = target_frame.content()
            match = re.search(PNP_CAPTCHA_PATTERN, content)
            if not match:
                return {"cedula": normalized, "status": "Captcha no encontrado"}
            
            sol = solve_pnp_captcha(match.group(1))
            target_frame.fill(input_selector, cedula_numerica)
            target_frame.fill('input[name*="Captcha"]', sol)
            target_frame.click("button[type='submit'], button:has-text('Buscar')")
            
            page.wait_for_timeout(5000)
            
            # Extraer resultado
            results = target_frame.locator("div.alert, .card-body").first
            if results.is_visible():
                return {"cedula": normalized, "fuente": "Sistemas PNP", "datos": results.inner_text().strip()}
            
            return {"cedula": normalized, "status": "Consulta realizada, sin datos visibles"}
            
        except Exception as e:
            return {"cedula": normalized, "status": f"Error: {str(e)}"}
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
