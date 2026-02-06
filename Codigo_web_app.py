import streamlit as st
import pdfplumber
import pandas as pd
import re
import os
import tempfile
from io import BytesIO

st.set_page_config(page_title="Procesador de PDF", page_icon="📄", layout="wide")
st.title("📄 Procesador de PDF de Trabajadores")

with st.sidebar:
    st.header("📋 Instrucciones")
    st.markdown("""
    1. Sube un PDF con listado de trabajadores
    2. Se procesará automáticamente
    3. Revisa los resultados
    4. Descarga el Excel
    
    **Característica:**
    - Solo mueve las fechas
    - Remuneración solo es "1" si aparece, sino vacío
    """)

# ============================================================================
# FUNCIONES DE PROCESAMIENTO
# ============================================================================

def es_encabezado(linea: str) -> bool:
    keywords = [
        "LISTADO DE TRABAJADORES", "Página", "Fecha de Impresión",
        "Apellidos y Nombres", "Nacimiento", "Fecha Ingreso",
        "Moneda", "Remuneración", "Estado Trabajador", "Estado Póliza"
    ]
    return any(kw in linea for kw in keywords)

def es_fragmento_nombre(linea: str) -> bool:
    linea = linea.strip()
    if len(linea) < 3 or re.match(r'^\d', linea):
        return False
    if not re.match(r'^[A-ZÁÉÍÓÚÑÜ\s\.\-\']+$', linea, re.IGNORECASE):
        return False
    
    palabras_datos = ['FEMENINO', 'MASCULINO', 'SOLES', 'DOLARES', 'ASEGURADO']
    return not any(palabra in linea.upper() for palabra in palabras_datos)

def extraer_registro_solo_fechas(linea: str, nombre_externo: str = ""):
    match_inicio = re.match(r'^(\d+)\s+(\d{6,10})\s*(.*)$', linea)
    if not match_inicio:
        return None
    
    nro = match_inicio.group(1)
    documento = match_inicio.group(2)
    resto = match_inicio.group(3).strip()
    
    if nombre_externo:
        resto = (nombre_externo.strip() + " " + resto).strip()
    
    # Inicializar variables
    sexo = ""
    fecha_nacimiento = ""
    nombre = ""
    fecha_ingreso = ""
    fecha_aseguramiento = ""
    fecha_registro = ""
    fecha_modificacion = ""
    moneda = ""
    remuneracion = ""
    estado_trabajador = ""
    estado_poliza = ""
    
    # Buscar sexo primero
    match_sexo = re.search(r'\b(FEMENINO|MASCULINO)\b', resto)
    
    if match_sexo:
        sexo = match_sexo.group(1)
        pos_sexo_inicio = match_sexo.start()
        pos_sexo_fin = match_sexo.end()
        
        texto_antes_sexo = resto[:pos_sexo_inicio].strip()
        
        # Buscar fecha de nacimiento antes del sexo
        fechas_antes = re.findall(r'(\d{2}\s*/\s*\d{2}\s*/\s*\d{4})', texto_antes_sexo)
        if fechas_antes:
            fecha_nacimiento = fechas_antes[-1]
            fecha_nacimiento = re.sub(r'\s*/\s*', '/', fecha_nacimiento.strip())
            pos_fecha = texto_antes_sexo.rfind(fechas_antes[-1])
            nombre = texto_antes_sexo[:pos_fecha].strip()
        else:
            nombre = texto_antes_sexo.strip()
        
        texto_despues_sexo = resto[pos_sexo_fin:].strip()
    else:
        sexo = ""
        fechas_todas = re.findall(r'(\d{2}\s*/\s*\d{2}\s*/\s*\d{4})', resto)
        
        if fechas_todas:
            primera_fecha = fechas_todas[0]
            fecha_nacimiento = re.sub(r'\s*/\s*', '/', primera_fecha.strip())
            pos_primera_fecha = resto.find(primera_fecha)
            nombre = resto[:pos_primera_fecha].strip()
            texto_despues_sexo = resto[pos_primera_fecha + len(primera_fecha):].strip()
        else:
            nombre = resto.strip()
            texto_despues_sexo = ""
    
    # Procesar fechas después del sexo
    if texto_despues_sexo:
        fechas_despues = re.findall(r'(\d{2}\s*/\s*\d{2}\s*/\s*\d{4})', texto_despues_sexo)
        fechas_despues_limpias = [re.sub(r'\s*/\s*', '/', f.strip()) for f in fechas_despues]
        
        fecha_idx = 0
        
        # Asignar fechas secuencialmente
        if fecha_idx < len(fechas_despues_limpias):
            fecha_ingreso = fechas_despues_limpias[fecha_idx]
            fecha_idx += 1
        
        if fecha_idx < len(fechas_despues_limpias):
            fecha_aseguramiento = fechas_despues_limpias[fecha_idx]
            fecha_idx += 1
        
        if fecha_idx < len(fechas_despues_limpias):
            fecha_registro = fechas_despues_limpias[fecha_idx]
            fecha_idx += 1
        
        if fecha_idx < len(fechas_despues_limpias):
            fecha_modificacion = fechas_despues_limpias[fecha_idx]
            fecha_idx += 1
        
        # Buscar moneda
        match_moneda = re.search(r'\b(SOLES|DOLARES)\b', texto_despues_sexo)
        moneda = match_moneda.group(1) if match_moneda else ""
        
        # Buscar remuneración - SOLO EL NÚMERO "1"
        # Buscamos específicamente el número 1 como palabra separada
        if ' 1 ' in f" {texto_despues_sexo} ":
            remuneracion = "1"
        
        # Buscar estados
        texto_upper = texto_despues_sexo.upper()
        estados_trabajador = ['ASEGURADO', 'ACTIVO', 'INACTIVO', 'BAJA', 'RETIRADO', 'CESADO']
        for estado in estados_trabajador:
            if estado in texto_upper:
                estado_trabajador = estado
                break
        
        if 'NO ENVIADO' in texto_upper:
            estado_poliza = 'NO ENVIADO'
        elif 'RECEPCIONADO' in texto_upper:
            estado_poliza = 'RECEPCIONADO'
        elif 'ENVIADO' in texto_upper:
            estado_poliza = 'ENVIADO'
    
    # Validar nombre
    if nombre and nombre.isspace():
        nombre = ""
    
    return {
        'Nro': nro,
        'Nro. Documento': documento,
        'Apellidos y Nombres del Trabajador': nombre if nombre else "",
        'Fecha Nacimiento': fecha_nacimiento if fecha_nacimiento else "",
        'Sexo': sexo if sexo else "",
        'Fecha Ingreso/Reingreso': fecha_ingreso if fecha_ingreso else "",
        'Moneda': moneda if moneda else "",
        'Remuneración Asegurable': remuneracion if remuneracion else "",
        'Fecha Aseguramiento': fecha_aseguramiento if fecha_aseguramiento else "",
        'Fecha Registro': fecha_registro if fecha_registro else "",
        'Fecha Última Modificación': fecha_modificacion if fecha_modificacion else "",
        'Estado Trabajador': estado_trabajador if estado_trabajador else "",
        'Estado Póliza': estado_poliza if estado_poliza else ""
    }

def procesar_pdf_solo_fechas(pdf_path: str):
    with pdfplumber.open(pdf_path) as pdf:
        lineas_raw = []
        for pagina in pdf.pages:
            texto = pagina.extract_text()
            if texto:
                for linea in texto.split('\n'):
                    linea_limpia = re.sub(r'\s+', ' ', linea).strip()
                    if linea_limpia:
                        lineas_raw.append(linea_limpia)
    
    lineas = [l for l in lineas_raw if not es_encabezado(l)]
    
    registros = []
    lineas_problema = []
    registros_sin_sexo = []
    lineas_usadas = set()
    
    i = 0
    while i < len(lineas):
        if i in lineas_usadas:
            i += 1
            continue
        
        linea_actual = lineas[i]
        
        if not re.match(r'^\d+\s+\d{6,10}', linea_actual):
            i += 1
            continue
        
        m = re.match(r'^(\d+)\s+(\d{6,10})\s*(.*)$', linea_actual)
        resto = m.group(3).strip() if m else ""
        
        falta_nombre = bool(re.match(r'^(\d{2}\s*/\s*\d{2}\s*/\s*\d{4}\b|FEMENINO\b|MASCULINO\b)', resto, re.IGNORECASE))
        
        nombre_parts = []
        used_now = []
        
        if falta_nombre:
            j = i - 1
            pasos = 0
            while j >= 0 and pasos < 2 and (j not in lineas_usadas):
                if es_fragmento_nombre(lineas[j]):
                    nombre_parts.insert(0, lineas[j].strip())
                    used_now.append(j)
                    j -= 1
                    pasos += 1
                else:
                    break
        
        nombre_externo = " ".join(nombre_parts).strip()
        
        for idx_used in used_now:
            lineas_usadas.add(idx_used)
        
        registro = extraer_registro_solo_fechas(linea_actual, nombre_externo=nombre_externo)
        
        if registro:
            registros.append(registro)
            if not registro['Sexo']:
                registros_sin_sexo.append(registro['Nro'])
        else:
            lineas_problema.append((i + 1, linea_actual[:200]))
        
        i += 1
    
    if registros:
        df = pd.DataFrame(registros)
        for col in df.columns:
            if df[col].dtype == 'object':
                df[col] = df[col].astype(str).str.strip()
                df[col] = df[col].replace(['nan', 'None', 'N/A', 'NaN', 'null'], '', regex=False)
    else:
        df = pd.DataFrame()
    
    return df, len(registros), registros_sin_sexo, lineas_problema

def crear_excel_en_memoria(df):
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Trabajadores')
        
        workbook = writer.book
        worksheet = writer.sheets['Trabajadores']
        
        for i, col in enumerate(df.columns):
            column_width = max(df[col].astype(str).map(len).max(), len(col)) + 2
            worksheet.set_column(i, i, min(column_width, 50))
    
    output.seek(0)
    return output

# ============================================================================
# INTERFAZ PRINCIPAL
# ============================================================================

def main():
    uploaded_file = st.file_uploader("📤 Sube tu archivo PDF", type="pdf")
    
    if uploaded_file is not None:
        col1, col2 = st.columns(2)
        with col1:
            st.metric("📄 Nombre", uploaded_file.name)
        with col2:
            st.metric("⚖️ Tamaño", f"{uploaded_file.size / 1024:.2f} KB")
        
        with st.spinner("🔍 Procesando PDF..."):
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
                tmp_file.write(uploaded_file.getvalue())
                tmp_path = tmp_file.name
            
            try:
                df, num_registros, sin_sexo, problemas = procesar_pdf_solo_fechas(tmp_path)
                os.unlink(tmp_path)
                
                if num_registros == 0:
                    st.error("❌ No se encontraron registros.")
                    return
                
                st.success(f"✅ {num_registros} registros encontrados")
                
                tab1, tab2 = st.tabs(["📊 Datos", "🔍 Problemas"])
                
                with tab1:
                    st.dataframe(df, use_container_width=True, height=400)
                    
                    with st.expander("📅 Estadísticas"):
                        st.write(f"**Total registros:** {len(df)}")
                        if 'Sexo' in df.columns:
                            conteo = df['Sexo'].value_counts()
                            st.write("**Sexo:**")
                            st.write(conteo)
                        if 'Remuneración Asegurable' in df.columns:
                            unos = (df['Remuneración Asegurable'] == '1').sum()
                            st.write(f"**Registros con '1' en remuneración:** {unos}")
                
                with tab2:
                    if problemas:
                        for idx, linea in problemas[:10]:
                            st.text(f"Línea {idx}: {linea[:100]}...")
                        if len(problemas) > 10:
                            st.info(f"... y {len(problemas) - 10} más")
                    else:
                        st.success("✅ Sin problemas")
                
                excel_data = crear_excel_en_memoria(df)
                nombre_base = os.path.splitext(uploaded_file.name)[0]
                
                st.download_button(
                    label="📥 Descargar Excel",
                    data=excel_data,
                    file_name=f"{nombre_base}_procesado.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
                
            except Exception as e:
                st.error(f"❌ Error: {str(e)}")
    else:
        st.info("👈 Sube un PDF para comenzar")

if __name__ == "__main__":
    main()