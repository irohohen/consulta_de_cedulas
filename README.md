# Proyecto de Extracción de Datos PNP

## Descripción General

Este proyecto está diseñado para automatizar la extracción de información desde una fuente de datos específica, presumiblemente relacionada con la Policía Nacional del Perú (PNP), utilizando números de cédula (DNI) como entrada. Su objetivo principal es simplificar el proceso de consulta y recopilación de datos, ofreciendo capacidades para resolver captchas, normalizar entradas y guardar la información obtenida en formatos CSV y JSON.

## Alcance del Proyecto

El alcance de este sistema abarca desde la preparación y validación de las cédulas de identidad hasta la extracción de datos y su almacenamiento persistente. Está enfocado en proporcionar una herramienta eficiente para usuarios que necesitan procesar grandes volúmenes de consultas de manera programática, interactuando con sistemas externos que requieren resolución de captchas.

## Componentes del Sistema

El sistema se compone de varias funciones clave, cada una con una responsabilidad específica:

*   **`normalize_cedula(cedula)`**: Esta función se encarga de estandarizar y limpiar el formato de un número de cédula, asegurando que cumpla con los requisitos esperados por el sistema de consulta.
*   **`parse_datos(datos_string)`**: Procesa una cadena de texto que contiene datos brutos obtenidos del sistema externo, extrayendo la información relevante y estructurándola para su posterior uso.
*   **`save_to_csv(data_list, filename)`**: Permite guardar una lista de diccionarios (cada uno representando un registro de datos) en un archivo CSV, facilitando la exportación y el análisis de la información en hojas de cálculo.
*   **`save_to_json(data_list, filename)`**: Guarda la misma lista de datos en un archivo JSON, un formato ideal para el intercambio de datos entre aplicaciones y el almacenamiento en bases de datos NoSQL.
*   **`solve_pnp_captcha(question)`**: Es responsable de interactuar con un servicio o lógica interna para resolver los captchas que el sistema PNP pueda presentar, permitiendo la automatización de las consultas.
*   **`get_pnp_data(cedula)`**: Esta es la función central que orquesta el proceso. Toma una cédula, resuelve el captcha si es necesario, realiza la consulta al sistema PNP y retorna los datos obtenidos después de ser procesados.

## Requisitos Previos

Para ejecutar este proyecto, necesitará tener instalado:

*   **Python 3.14+**: Se recomienda usar la versión especificada en `.python-version` para asegurar la compatibilidad.
*   **uv**: Un gestor de paquetes y entorno virtual ultrarrápido, utilizado para instalar las dependencias del proyecto.

## Configuración y Ejecución

Siga estos pasos para configurar y ejecutar el programa:

### 1. Clonar el Repositorio

Si aún no lo ha hecho, clone el repositorio del proyecto:

```bash
git clone <URL_DEL_REPOSITORIO>
cd <NOMBRE_DEL_REPOSITORIO>
```

### 2. Configurar el Entorno Virtual con `uv`

`uv` gestiona las dependencias y el entorno virtual de forma eficiente.

```bash
uv venv
```

Esto creará un entorno virtual local en el directorio `.venv`.

### 3. Activar el Entorno Virtual

Active el entorno virtual.

En Linux/macOS:

```bash
source .venv/bin/activate
```

En Windows (CMD):

```bash
.venv\Scripts\activate.bat
```

En Windows (PowerShell):

```bash
.venv\Scripts\Activate.ps1
```

### 4. Instalar Dependencias

Con el entorno virtual activado, instale todas las dependencias listadas en `pyproject.toml` y `uv.lock` usando `uv`:

```bash
uv pip install
```

### 5. Ejecutar el Programa

Una vez que todas las dependencias estén instaladas, puede ejecutar el script principal:

```bash
python main.py
```

Asegúrese de leer la lógica dentro de `main.py` para entender cómo interactuar con las funciones de extracción y guardado de datos. Es posible que necesite modificar `main.py` para adaptar su uso a sus necesidades específicas (por ejemplo, proporcionar una lista de cédulas o especificar los nombres de los archivos de salida).

## Maximizar el Aprovechamiento

Para sacar el máximo provecho de este sistema:

*   **Automatización de Listas de Cédulas**: Modifique `main.py` para leer listas de cédulas desde un archivo (por ejemplo, un CSV) y procesarlas en lote.
*   **Manejo de Errores**: Implemente un manejo de errores robusto para capturar y registrar cédulas que no pudieron ser procesadas o captchas que fallaron.
*   **Configuración de Salida**: Ajuste la lógica para decidir si los datos se guardan en CSV, JSON, o ambos, y personalice los nombres de los archivos de salida.
*   **Configuración del Captcha**: Si la función `solve_pnp_captcha` es un placeholder, integre una solución real de resolución de captchas (ej. un servicio de terceros o un modelo de ML local) para asegurar el funcionamiento.
*   **Programación de Tareas**: Utilice herramientas de programación de tareas del sistema operativo (como `cron` en Linux/macOS o el Programador de Tareas en Windows) para ejecutar el script periódicamente y mantener los datos actualizados.
