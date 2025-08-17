
# app.py (con descarga de reporte y mensajes de avance)

import os
import gradio as gr
import google.generativeai as genai
import pypdf
import io
import time
import json
import html
import tempfile # <--- CAMBIO 1: Asegurarnos de importar la librería

# --- LISTA DE VERIFICACIÓN (CONSTANTE) ---
CHECKLIST_ITEMS = [
    "Objeto Contractual", "Contenido presupuestario", "Garantía de cumplimiento",
    "Especies fiscales y timbres (específicamente el Timbre de la Asociación Ciudad de las Niñas)",
    "Términos de pago (Verificar si existe adelanto de pago)", "Vigencia de la oferta",
    "Plazo de adjudicación", "Plazo de entrega de los bienes o servicios",
    "Requisitos de admisibilidad", "Criterios de evaluación", "Cláusulas penales y de multas",
    "Vigencia del contrato y posibilidad de prórrogas",
    "Traducción de documentación técnica si es en idioma extranjero",
    "Apostillado de documentos públicos emitidos en el extranjero"
]

# --- (Las funciones de procesamiento como extract_text, analyze_requirement, etc. no cambian) ---
def extract_text_from_pdf_bytes(pdf_file):
    try:
        pdf_reader = pypdf.PdfReader(pdf_file.name)
        text = ""
        for page in pdf_reader.pages:
            text += page.extract_text()
        return text
    except Exception as e:
        return f"Error al leer el archivo PDF: {e}"

def analyze_requirement(model, requirement, consolidated_text, filename1, filename2):
    prompt = f"""
    Eres un asistente experto en la revisión de pliegos de condiciones de contratación administrativa en Costa Rica.
    Tu tarea es analizar el texto de dos documentos para verificar un requisito.
    Los documentos son '{filename1}' y '{filename2}'.

    **Requisito a verificar:** "{requirement}"

    **Texto completo:**
    --- INICIO TEXTO ---
    {consolidated_text}
    --- FIN TEXTO ---

    **Instrucciones:** Responde EXCLUSIVAMENTE con un objeto JSON con la siguiente estructura:
    {{
        "encontrado": "Sí" o "No",
        "archivo": "Nombre del archivo donde se encontró la información",
        "clausula": "Nombre exacto de la cláusula o sección",
        "texto_relevante": "Cita textual que cumple con el requisito."
    }}
    Si no encuentras información relevante para un campo, responde con un valor null.
    """
    try:
        response = model.generate_content(prompt)
        json_response_text = response.text.strip()
        start_index = json_response_text.find('{')
        end_index = json_response_text.rfind('}') + 1
        if start_index != -1 and end_index != -1:
            json_response_text = json_response_text[start_index:end_index]
        return json.loads(json_response_text)
    except Exception as e:
        return {"encontrado": "Error", "archivo": "N/A", "clausula": "Error en API", "texto_relevante": str(e)}

def generate_summary(model, consolidated_text):
    prompt = f"""
    Eres un asistente experto en contratación administrativa. Basado en el texto proporcionado,
    genera un resumen conciso que incluya: Objeto, Plazo y prórrogas, Presupuesto,
    Plazo de entrega, Vigencia de la oferta, Plazo de adjudicación y Multas/Cláusula Penal.
    Cada punto debe estar en una nueva línea, comenzando con un guion. Ejemplo: "- Objeto: Compra de equipo."
    """
    try:
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"No se pudo generar el resumen debido a un error: {e}"

def create_html_report(summary, checklist_results):
    summary_html = ""
    for line in summary.split('\n'):
        if line.strip().startswith('-'):
            parts = line.strip().lstrip('- ').split(':', 1)
            if len(parts) == 2:
                summary_html += f"<p><strong>{html.escape(parts[0].strip())}:</strong> {html.escape(parts[1].strip())}</p>\n"
            else:
                summary_html += f"<p>{html.escape(line)}</p>\n"

    table_rows_html = ""
    for item in checklist_results:
        result = item.get('resultado', {})
        requirement = html.escape(str(item.get('requisito') or 'N/A'))
        found = html.escape(str(result.get('encontrado') or 'No'))
        found_style = "color: green; font-weight: bold;" if found == "Sí" else "color: red;"
        
        file = html.escape(str(result.get('archivo') or 'N/A'))
        clause = html.escape(str(result.get('clausula') or 'N/A'))
        text = html.escape(str(result.get('texto_relevante') or 'No se encontró información.'))
        observations = f"<strong>Archivo:</strong> {file}<br><strong>Cláusula:</strong> {clause}<br><strong>Texto:</strong> {text}"

        table_rows_html += f"""
        <tr>
            <td>{requirement}</td>
            <td style="{found_style}">{found}</td>
            <td>{observations}</td>
        </tr>
        """
    return f"""
    <!DOCTYPE html>
    <html lang="es">
    <head>
        <meta charset="UTF-8">
        <title>Reporte de Verificación</title>
        <style>
            body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
            .container {{ max-width: 1000px; margin: auto; background: #fff; padding: 30px; border-radius: 8px; box-shadow: 0 0 15px rgba(0,0,0,0.1); }}
            h1, h2 {{ color: #003366; border-bottom: 2px solid #ddd; padding-bottom: 10px; }}
            table {{ width: 100%; border-collapse: collapse; margin-top: 20px; }}
            th, td {{ border: 1px solid #ddd; padding: 12px; text-align: left; vertical-align: top; }}
            th {{ background-color: #003366; color: white; }}
            tr:nth-child(even) {{ background-color: #f9f9f9; }}
            p strong {{ color: #003366; }}
            td:nth-child(2) {{ text-align: center; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>Reporte de Verificación de Contratación</h1>
            <h2>Resumen Ejecutivo</h2>
            {summary_html}
            <h2>Tabla de Verificación del Pliego de Condiciones</h2>
            <table>
                <thead>
                    <tr>
                        <th>Requisito</th>
                        <th>Cumple</th>
                        <th>Observaciones</th>
                    </tr>
                </thead>
                <tbody>
                    {table_rows_html}
                </tbody>
            </table>
        </div>
    </body>
    </html>
    """


# --- FUNCIÓN PRINCIPAL (GENERADOR) ---
def process_documents(api_key, file1, file2):
    # Valores iniciales para los componentes de salida
    no_report = " "
    no_file = None
    
    yield no_report, no_file, "Iniciando proceso..."

    if not api_key:
        raise gr.Error("Error de Autenticación", "Por favor, ingresa tu Google API Key.")
    if file1 is None or file2 is None:
        raise gr.Error("Faltan Archivos", "Por favor, sube ambos documentos PDF para continuar.")

    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-1.5-pro-latest')
    except Exception as e:
        raise gr.Error("Error de API", f"No se pudo configurar la API de Gemini. Verifica tu clave. Error: {e}")

    yield no_report, no_file, "Extrayendo texto del primer archivo..."
    filename1 = os.path.basename(file1.name)
    text1 = extract_text_from_pdf_bytes(file1)
    if text1.startswith("Error"): raise gr.Error("Error de Lectura", text1)

    yield no_report, no_file, "Extrayendo texto del segundo archivo..."
    filename2 = os.path.basename(file2.name)
    text2 = extract_text_from_pdf_bytes(file2)
    if text2.startswith("Error"): raise gr.Error("Error de Lectura", text2)
    
    consolidated_text = f"--- INICIO: {filename1} ---\n{text1}\n--- FIN: {filename1} ---\n\n--- INICIO: {filename2} ---\n{text2}\n--- FIN: {filename2} ---"

    yield no_report, no_file, "Generando resumen ejecutivo con IA..."
    summary = generate_summary(model, consolidated_text)

    final_results = []
    total_items = len(CHECKLIST_ITEMS)
    for i, requirement in enumerate(CHECKLIST_ITEMS):
        yield no_report, no_file, f"Analizando requisito {i+1}/{total_items}: {requirement}..."
        analysis_result = analyze_requirement(model, requirement, consolidated_text, filename1, filename2)
        final_results.append({"requisito": requirement, "resultado": analysis_result})
        time.sleep(1)

    yield no_report, no_file, "Generando reporte final..."
    html_report = create_html_report(summary, final_results)
    
    # <--- CAMBIO 2: Guardar el reporte en un archivo temporal ---
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.html', encoding='utf-8') as temp_file:
        temp_file.write(html_report)
        temp_filepath = temp_file.name

    # El "return" final se convierte en el último "yield" con todos los resultados
    yield html_report, temp_filepath, "✅ ¡Proceso completado!"

# --- INTERFAZ DE GRADIO ---
with gr.Blocks(theme=gr.themes.Soft(primary_hue="blue", secondary_hue="neutral"), title="Revisor CGR") as demo:
    gr.Markdown(
        """
        # 🏛️ Revisor Inteligente de Documentos de Contratación
        **Demo para la Contraloría General de la República de Costa Rica**
        
        Sube ambos archivos PDF, ingresa tu clave de API de Google y la aplicación generará un reporte de verificación.
        """
    )

    with gr.Row():
        with gr.Column(scale=1):
            gr.Markdown("### ⚙️ Configuración y Archivos")
            api_key_input = gr.Textbox(
                label="Google AI API Key", type="password", placeholder="Pega tu clave de API aquí...",
                info="Puedes obtener tu clave en Google AI Studio."
            )
            file_input1 = gr.File(label="1. Resumen del Sistema (SICOP)", file_types=[".pdf"])
            file_input2 = gr.File(label="2. Pliego de Condiciones (Cartel)", file_types=[".pdf"])
            submit_btn = gr.Button("Analizar Documentos", variant="primary")
            status_textbox = gr.Textbox(label="Estado del Proceso", interactive=False)
            
        with gr.Column(scale=3):
            gr.Markdown("### 📋 Reporte Generado")
            output_html = gr.HTML(label="Vista Previa del Reporte")
            # <--- CAMBIO 3: Añadir un componente de archivo para la descarga ---
            download_file = gr.File(label="Descargar Reporte Completo", interactive=False)

    # <--- CAMBIO 4: Actualizar el evento click para que maneje las tres salidas ---
    submit_btn.click(
        fn=process_documents,
        inputs=[api_key_input, file_input1, file_input2],
        outputs=[output_html, download_file, status_textbox]
    )

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 7860))
    demo.launch(server_name="0.0.0.0", server_port=port)
