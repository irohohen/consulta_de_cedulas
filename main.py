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
    print(f"\n[DEBUG] Iniciando proceso para: {normalized}")
    
    with sync_playwright() as p:
        # 1. Modo VISIBLE para inspección manual
        browser = p.chromium.launch(headless=False, args=[
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox"
        ])
        
        context = browser.new_context(
            user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36"
        )
        page = context.new_page()
        
        try:
            print(f"[DEBUG] Navegando a {PNP_BASE_URL}...")
            # Usamos 'commit' para que apenas el servidor responda, sigamos adelante
            page.goto(f"{PNP_BASE_URL}{PNP_GET_CAPTCHA_URL_PATH}", wait_until="domcontentloaded", timeout=60000)
            print("[DEBUG] Página base cargada.")

            # 2. Esperar al input de la cédula
            page.wait_for_selector(f'input[name="{PNP_FORM_CEDULA_FIELD}"]', timeout=15000)
            print("[DEBUG] Formulario detectado.")

            # 3. Resolver Captcha con log de texto
            body_text = page.inner_text("body")
            captcha_match = re.search(PNP_CAPTCHA_PATTERN, body_text)
            
            if not captcha_match:
                print("[ERROR] No se pudo encontrar el patrón del captcha en el texto de la página.")
                return {"cedula": normalized, "status": "Error: Captcha no encontrado"}
            
            question = captcha_match.group(1)
            solution = solve_pnp_captcha(question)
            print(f"[DEBUG] Pregunta: '{question}' -> Solución: {solution}")

            # 4. Simulación de escritura humana
            page.type(f'input[name="{PNP_FORM_CEDULA_FIELD}"]', normalized, delay=150)
            page.type(f'input[name="{PNP_FORM_CAPTCHA_FIELD}"]', solution, delay=150)
            print("[DEBUG] Campos completados. Haciendo clic en enviar...")

            # 5. Click y monitoreo de respuesta
            page.click("button.btn-primary, button[type='submit']")
            
            # Esperamos a que aparezca algún cambio en el DOM (alerta o resultado)
            print("[DEBUG] Esperando resultados del servidor...")
            page.wait_for_selector("div.alert, div.card-body, table, .container", timeout=20000)
            
            # Capturamos el contenido
            content = page.locator("body > div:nth-of-type(1) > div:nth-of-type(1)").first
            raw_result = content.inner_text().strip()
            
            print(f"[SUCCESS] Datos extraídos para {normalized}")
            return {
                "cedula": normalized, 
                "fuente": "Sistemas PNP", 
                "datos_tarjeta": raw_result
            }

        except Exception as e:
            # En caso de error, guardamos una imagen de lo que veía el bot
            error_img = f"error_{normalized}.png"
            page.screenshot(path=error_img)
            print(f"[ERROR] Falló {normalized}. Captura guardada como {error_img}")
            print(f"[DETALLE] {str(e)}")
            return {"cedula": normalized, "status": f"Error: {type(e).__name__}"}
            
        finally:
            # Dejamos el navegador abierto 2 segundos para que alcances a ver qué pasó
            page.wait_for_timeout(2000)
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
