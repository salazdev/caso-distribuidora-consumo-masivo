"""
02_limpieza.py - Fase 2: limpieza y normalizacion.
Ejecutar desde la carpeta andina:   python scripts/02_limpieza.py
Lee datos/crudos/ (sin modificarlos) y escribe en datos/procesados/ y salidas/.
"""
from pathlib import Path
import pandas as pd
from herramientas_perfilado import clasificar_fecha

# ---------- Rutas ----------
RAIZ = Path(__file__).resolve().parent.parent
CRUDOS = RAIZ / "datos" / "crudos"
PROCESADOS = RAIZ / "datos" / "procesados"
SALIDAS = RAIZ / "salidas"
PROCESADOS.mkdir(parents=True, exist_ok=True)

# ---------- Registro de descartes ----------
descartados = []

def descartar(df, mascara, tabla, motivo):
    """Saca las filas marcadas, las guarda con su motivo y devuelve el resto."""
    fuera = df[mascara].copy()
    fuera["tabla"] = tabla
    fuera["motivo_descarte"] = motivo
    descartados.append(fuera)
    print(f"  {motivo}: {len(fuera):,} filas descartadas")
    return df[~mascara].copy()

# ==================================================
# VENTAS
# ==================================================
print("\n== VENTAS ==")
ventas = pd.read_csv(CRUDOS / "ventas.csv")
print(f"  Filas recibidas: {len(ventas):,}")

# 1. Duplicados exactos (siempre primero)
ventas = descartar(ventas, ventas.duplicated(), "ventas", "Duplicado exacto")

# 2. Fechas: clasificar, descartar imposibles, convertir y marcar ambiguas
FECHA_MAX = pd.Timestamp("2026-06-30")   # último día de datos según el encargo

ventas["tipo_fecha"] = ventas["fecha"].apply(clasificar_fecha)
ventas = descartar(ventas, ventas["tipo_fecha"] == "inválida", "ventas", "Fecha imposible")

FORMATOS = {
    "ISO": "%Y-%m-%d",
    "dd-mm-aaaa": "%d-%m-%Y",
    "barra: día/mes seguro": "%d/%m/%Y",
    "barra: ambigua": "%d/%m/%Y",      # regla 1: ambiguas se leen como día/mes
    "barra: mes/día seguro": "%m/%d/%Y",
}
texto = ventas["fecha"]
partes = [pd.to_datetime(texto[ventas["tipo_fecha"] == t], format=f)
          for t, f in FORMATOS.items()]
ventas["fecha"] = pd.concat(partes)

# Regla 2: si la lectura día/mes cae después del último día de datos, era mes/día
amb = ventas["tipo_fecha"] == "barra: ambigua"
corregir = amb & (ventas["fecha"] > FECHA_MAX)
ventas.loc[corregir, "fecha"] = pd.to_datetime(texto[corregir], format="%m/%d/%Y")
print(f"  Ambiguas resueltas por rango (eran mes/día): {corregir.sum():,}")

ventas["fecha_ambigua"] = amb & ~corregir
ventas = ventas.drop(columns="tipo_fecha")

assert ventas["fecha"].notna().all(), "Quedaron fechas sin convertir"
assert ventas["fecha"].max() <= FECHA_MAX, "Hay fechas después del último día de datos"
print(f"  Fechas ambiguas marcadas: {ventas['fecha_ambigua'].sum():,}")
print(f"  Rango: {ventas['fecha'].min().date()} a {ventas['fecha'].max().date()}")
print(f"  Filas que siguen: {len(ventas):,}")

# 3. Devoluciones cargadas como venta negativa: se separan, no se borran
es_dev = ventas["cantidad"] < 0
dev_desde_ventas = ventas[es_dev].copy()
dev_desde_ventas["cantidad"] = -dev_desde_ventas["cantidad"]   # se guardan en positivo
dev_desde_ventas["origen"] = "ventas.csv (cantidad negativa)"
ventas = ventas[~es_dev].copy()
print(f"  Devoluciones separadas a su propia tabla: {len(dev_desde_ventas):,}")
print(f"  Ventas que siguen: {len(ventas):,}")

# ==================================================
# GUARDAR
# ==================================================
ventas.to_csv(PROCESADOS / "ventas_limpias.csv", index=False)
dev_desde_ventas.to_csv(PROCESADOS / "devoluciones_desde_ventas.csv", index=False)
pd.concat(descartados).to_csv(SALIDAS / "descartados.csv", index=False)
print(f"\nListo. Descartados totales: {sum(len(d) for d in descartados):,}")