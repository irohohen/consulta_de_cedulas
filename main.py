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

    print(f"\n[DEBUG] >>> INICIANDO CONSULTA: {normalized} <<<")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()

        try:
            print(f"[DEBUG] [1/5] Navegando a {PNP_BASE_URL}...")
            page.goto(f"{PNP_BASE_URL}{PNP_GET_CAPTCHA_URL_PATH}", wait_until="load", timeout=60000)
            page.wait_for_timeout(4000)

            target_frame = None
            for i, f in enumerate(page.frames):
                # Buscamos el frame que tenga el formulario con ID 'form'
                if f.locator("#form").count() > 0:
                    target_frame = f
                    break

            if not target_frame:
                print("[ERROR] Marco del formulario no hallado.")
                return {"cedula": normalized, "status": "Error: Marco"}

            # --- RESOLUCIÓN DE CAPTCHA (YA FUNCIONA) ---
            captcha_text = target_frame.locator(".captcha-container").inner_text()
            match = re.search(r'(\d+)\s*([+\-*/])\s*(\d+)', captcha_text)

            if not match:
                print(f"[ERROR] No se pudo parsear el captcha en: '{captcha_text}'")
                return {"cedula": normalized, "status": "Error: Captcha"}

            solution = solve_pnp_captcha(match.group(0))
            print(f"[DEBUG] CAPTCHA LEÍDO: {match.group(0)} | SOLUCIÓN: {solution}")

            # --- LLENADO DE CAMPOS (CORREGIDO) ---
            print("[DEBUG] [4/5] Localizando campos con selectores flexibles...")

            # Selector flexible para la Cédula
            selector_cedula = 'input[name*="edula"], input[placeholder*="édula"], #txtCedula'
            input_cedula = target_frame.locator(selector_cedula).first

            # Selector flexible para el Captcha
            selector_captcha = 'input[name*="aptcha"], input[placeholder*="esultado"], #txtCaptcha'
            input_captcha = target_frame.locator(selector_captcha).first

            # Debug de atributos para saber qué nombres tienen realmente
            name_ced = input_cedula.get_attribute("name")
            name_cap = input_captcha.get_attribute("name")
            print(f"[DEBUG] Campo Cédula detectado como: name='{name_ced}'")
            print(f"[DEBUG] Campo Captcha detectado como: name='{name_cap}'")

            # Escribir datos
            print(f"[DEBUG] Escribiendo cédula '{cedula_numerica}'...")
            input_cedula.fill(cedula_numerica)

            print(f"[DEBUG] Escribiendo solución '{solution}'...")
            input_captcha.fill(solution)

            # --- ENVÍO ---
            print("[DEBUG] [5/5] Enviando...")
            target_frame.locator("button[type='submit'], button:has-text('Buscar')").click()

            page.wait_for_timeout(5000)
            page.screenshot(path=f"resultado_{cedula_numerica}.png")

            # Verificación de datos
            resultado = target_frame.locator(".form-container, .alert").first
            if resultado.is_visible():
                print(f"[SUCCESS] Datos obtenidos para {normalized}")
                return {"cedula": normalized, "fuente": "Sistemas PNP", "datos": resultado.inner_text().strip()}

            return {"cedula": normalized, "status": "Enviado - Verifique imagen"}

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
