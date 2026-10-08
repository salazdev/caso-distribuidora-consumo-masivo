"""
03_carga.py - Fase 3: carga de los datos limpios al modelo estrella en MySQL.
Requisito: haber ejecutado 03_modelo.sql en MySQL Workbench.
Ejecutar desde la carpeta andina:   python scripts/03_carga.py
Se puede correr varias veces: vacía las tablas y las vuelve a llenar.
"""
from pathlib import Path
from getpass import getpass
import os
import pandas as pd
import holidays
from sqlalchemy import create_engine, text

RAIZ = Path(__file__).resolve().parent.parent
PROCESADOS = RAIZ / "datos" / "procesados"
CRUDOS = RAIZ / "datos" / "crudos"

# ---------- Conexión (la clave se pide al correr, nunca se escribe en el código) ----------
USUARIO = os.environ.get("MYSQL_USER", "root")
CLAVE = os.environ.get("MYSQL_PASSWORD") or getpass(f"Clave de MySQL para '{USUARIO}': ")
motor = create_engine(f"mysql+pymysql://{USUARIO}:{CLAVE}@localhost:3306/distribuidora_dw")

# ---------- Leer los datos limpios de la Fase 2 ----------
ventas = pd.read_csv(PROCESADOS / "ventas_limpias.csv", parse_dates=["fecha"])
devoluciones = pd.read_csv(PROCESADOS / "devoluciones_limpias.csv", parse_dates=["fecha"])
visitas = pd.read_csv(PROCESADOS / "visitas_limpias.csv", parse_dates=["fecha"])
productos = pd.read_csv(PROCESADOS / "productos_limpios.csv")
clientes = pd.read_csv(PROCESADOS / "clientes_limpios.csv", dtype=str)
vendedores = pd.read_excel(CRUDOS / "vendedores.xlsx")

def clave_fecha(serie):
    """2025-07-04 -> 20250704"""
    return serie.dt.strftime("%Y%m%d").astype(int)

# ==================================================
# DIMENSIONES
# ==================================================
# --- dim_fecha: un calendario con una fila por día ---
dias = pd.DataFrame({"fecha": pd.date_range("2023-01-01", "2026-06-30", freq="D")})
MESES = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio",
         "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]
DIAS = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
festivos = holidays.CO(years=range(2023, 2027), language="es")

dim_fecha = pd.DataFrame({
    "fecha_key": clave_fecha(dias["fecha"]),
    "fecha": dias["fecha"].dt.date,
    "anio": dias["fecha"].dt.year,
    "trimestre": dias["fecha"].dt.quarter,
    "mes": dias["fecha"].dt.month,
    "nombre_mes": dias["fecha"].dt.month.map(lambda m: MESES[m - 1]),
    "anio_mes": dias["fecha"].dt.strftime("%Y-%m"),
    "semana_iso": dias["fecha"].dt.isocalendar().week.astype(int),
    "dia_mes": dias["fecha"].dt.day,
    "dia_semana": dias["fecha"].dt.dayofweek + 1,          # 1 = lunes
    "nombre_dia": dias["fecha"].dt.dayofweek.map(lambda d: DIAS[d]),
    "es_fin_de_semana": dias["fecha"].dt.dayofweek >= 5,
    "es_festivo": dias["fecha"].dt.date.map(lambda f: f in festivos),
    "nombre_festivo": dias["fecha"].dt.date.map(lambda f: festivos.get(f)),
})

# --- dim_producto + miembro desconocido ---
dim_producto = productos.copy()
dim_producto.loc[len(dim_producto)] = {
    "sku": "SKU-0000", "descripcion": "Producto no identificado", "categoria": "No identificado",
    "proveedor": None, "costo_unitario": 0, "precio_lista": 0,
    "costo_imputado": False, "precio_desde_ventas": False}

# --- dim_cliente + miembro desconocido ---
dim_cliente = clientes.copy()
dim_cliente["fecha_alta"] = pd.to_datetime(dim_cliente["fecha_alta"]).dt.date
dim_cliente["fecha_alta_ambigua"] = dim_cliente["fecha_alta_ambigua"] == "True"
dim_cliente.loc[len(dim_cliente)] = {
    "id_cliente": "C-99999", "nit": "000000000", "nit_dv": None,
    "razon_social": "CLIENTE NO IDENTIFICADO", "tipo_negocio": "No identificado",
    "ciudad": "No identificada", "direccion": "No identificada", "telefono": None,
    "email": None, "email_2": None, "ruta_asignada": "N/A",
    "fecha_alta": pd.Timestamp("2023-01-01").date(), "fecha_alta_ambigua": False,
    "cupo_credito": 0}

# --- dim_vendedor ---
dim_vendedor = vendedores.copy()
dim_vendedor["fecha_ingreso"] = pd.to_datetime(dim_vendedor["fecha_ingreso"]).dt.date

# ==================================================
# HECHOS
# ==================================================
# --- fact_ventas: métricas calculadas aquí para que las consultas sean simples ---
costo_unit = dim_producto.set_index("sku")["costo_unitario"]
fv = ventas.copy()
fv["fecha_key"] = clave_fecha(fv["fecha"])
fv["venta_bruta"] = (fv["cantidad"] * fv["precio_unitario"]).round(2)
fv["valor_descuento"] = (fv["venta_bruta"] * fv["descuento_pct"] / 100).round(2)
fv["venta_neta"] = fv["venta_bruta"] - fv["valor_descuento"]
fv["costo_total"] = (fv["cantidad"] * fv["sku"].map(costo_unit)).round(2)
# OJO: las ventas con SKU-0000 quedan con costo 0 (no se sabe qué producto es).
#      En los análisis de margen se excluyen con: WHERE sku_comodin = 0
fact_ventas = fv[["folio", "fecha_key", "id_cliente", "sku", "id_vendedor", "canal",
                  "cantidad", "precio_unitario", "descuento_pct", "venta_bruta",
                  "valor_descuento", "venta_neta", "costo_total", "fecha_ambigua",
                  "precio_imputado", "sku_comodin", "cliente_comodin"]]

# --- fact_devoluciones ---
fd = devoluciones.copy()
fd["fecha_key"] = clave_fecha(fd["fecha"])
fact_devoluciones = fd[["id_devolucion", "fecha_key", "id_cliente", "sku", "cantidad",
                        "motivo", "origen", "fecha_ambigua", "sku_comodin", "cliente_comodin"]]

# --- fact_visitas ---
fvi = visitas.copy()
fvi["fecha_key"] = clave_fecha(fvi["fecha"])
fact_visitas = fvi.rename(columns={"cliente_id": "id_cliente", "vendedor_id": "id_vendedor"})[
    ["visita_id", "fecha_key", "id_cliente", "id_vendedor", "efectiva", "motivo_no_venta",
     "duracion_min", "lat", "lon", "ruta_app"]]

# ==================================================
# CARGA: vaciar (hechos primero) y llenar (dimensiones primero)
# ==================================================
CARGA = [("dim_fecha", dim_fecha), ("dim_producto", dim_producto),
         ("dim_cliente", dim_cliente), ("dim_vendedor", dim_vendedor),
         ("fact_ventas", fact_ventas), ("fact_devoluciones", fact_devoluciones),
         ("fact_visitas", fact_visitas)]

with motor.begin() as con:
    for tabla, _ in reversed(CARGA):
        con.execute(text(f"DELETE FROM {tabla}"))
    for tabla, df in CARGA:
        df.to_sql(tabla, con, if_exists="append", index=False, chunksize=5000, method="multi")
        print(f"  {tabla:<18} {len(df):>7,} filas cargadas")

# ==================================================
# VERIFICACIÓN: lo que hay en MySQL debe coincidir con lo que se cargó
# ==================================================
print("\nVerificación en MySQL:")
with motor.connect() as con:
    for tabla, df in CARGA:
        n = con.execute(text(f"SELECT COUNT(*) FROM {tabla}")).scalar()
        estado = "OK" if n == len(df) else "NO COINCIDE"
        print(f"  {tabla:<18} {n:>7,}  {estado}")
