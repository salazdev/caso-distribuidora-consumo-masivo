"""
02_limpieza.py - Fase 2: limpieza y normalizacion.
Ejecutar desde la carpeta andina:   python scripts/02_limpieza.py
Lee datos/crudos/ (sin modificarlos) y escribe en datos/procesados/ y salidas/.
"""
from pathlib import Path
import json
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
# 4. Precios en cero: se imputan desde el catálogo; si el catálogo no tiene
#    precio, desde el historial de ventas del mismo SKU (precio venta = precio lista)
productos = pd.read_csv(CRUDOS / "productos.csv")
precio_historial = ventas[ventas["precio_unitario"] > 0].groupby("sku")["precio_unitario"].median()
precio_ref = productos.set_index("sku")["precio_lista"].fillna(precio_historial)

en_cero = ventas["precio_unitario"] == 0
ventas.loc[en_cero, "precio_unitario"] = ventas.loc[en_cero, "sku"].map(precio_ref)
ventas["precio_imputado"] = en_cero
assert ventas["precio_unitario"].gt(0).all(), "Quedaron precios en cero o vacíos"
print(f"  Precios en cero imputados: {en_cero.sum():,}")

# 5. Claves comodín: se marcan, no se borran
ventas["sku_comodin"] = ventas["sku"] == "SKU-0000"
ventas["cliente_comodin"] = ventas["id_cliente"] == "C-99999"
print(f"  SKU comodín marcados: {ventas['sku_comodin'].sum():,}")
print(f"  Cliente comodín marcados: {ventas['cliente_comodin'].sum():,}")

# ==================================================
# PRODUCTOS
# ==================================================
print("\n== PRODUCTOS ==")
print(f"  Filas recibidas: {len(productos):,}")

# 1. Categorías: 19 escrituras -> 5 categorías reales (tabla explícita, auditable)
CATEGORIAS = {
    "BEBIDAS": "Bebidas", "Bebidas": "Bebidas", "bebidas": "Bebidas", "Bebida": "Bebidas",
    "SNACKS": "Snacks", "Snacks": "Snacks", "snack": "Snacks", "Snaks": "Snacks",
    "ASEO": "Aseo", "Aseo": "Aseo", "aseo": "Aseo", "Aseo Hogar": "Aseo",
    "ABARROTES": "Abarrotes", "Abarrotes": "Abarrotes", "abarrote": "Abarrotes",
    "LACTEOS": "Lácteos", "Lacteos": "Lácteos", "lacteos": "Lácteos", "Lácteos": "Lácteos",
}
sin_mapa = set(productos["categoria"]) - set(CATEGORIAS)
assert not sin_mapa, f"Categorías sin mapear: {sin_mapa}"
productos["categoria"] = productos["categoria"].map(CATEGORIAS)
print(f"  Categorías unificadas: {productos['categoria'].nunique()}")

# 2. Precio de lista vacío: se recupera del historial de ventas (dato real, no estimado)
sin_precio = productos["precio_lista"].isna()
productos.loc[sin_precio, "precio_lista"] = productos.loc[sin_precio, "sku"].map(precio_historial)
productos["precio_desde_ventas"] = sin_precio
assert productos["precio_lista"].notna().all(), "Quedaron productos sin precio"
print(f"  Precios de lista recuperados desde ventas: {sin_precio.sum():,}")

# 3. Costo en cero: ESTIMADO con la relación costo/precio mediana de su categoría
#    (no existe fuente con el costo real; se marca y se reporta)
con_costo = productos["costo_unitario"] > 0
relacion = (productos[con_costo]
            .assign(r=lambda d: d["costo_unitario"] / d["precio_lista"])
            .groupby("categoria")["r"].median())
sin_costo = ~con_costo
productos.loc[sin_costo, "costo_unitario"] = (
    productos.loc[sin_costo, "precio_lista"]
    * productos.loc[sin_costo, "categoria"].map(relacion)).round(0)
productos["costo_imputado"] = sin_costo
assert productos["costo_unitario"].gt(0).all(), "Quedaron costos en cero"
print(f"  Costos estimados por categoría (marcados): {sin_costo.sum():,}")
# ==================================================
# CLIENTES - parte A: normalizar (la deduplicación va en la parte B)
# ==================================================
print("\n== CLIENTES ==")
clientes = pd.read_excel(CRUDOS / "clientes.xlsx", dtype=str)
print(f"  Filas recibidas: {len(clientes):,}")

# 1. Duplicados exactos (filas idénticas)
clientes = descartar(clientes, clientes.duplicated(), "clientes", "Duplicado exacto")

# 2. NIT: solo dígitos; base de 9 dígitos + dígito de verificación aparte
digitos = clientes["nit"].str.replace(r"\D", "", regex=True)
clientes["nit"] = digitos.str[:9]
clientes["nit_dv"] = digitos.str[9:].replace("", pd.NA)
assert clientes["nit"].str.len().eq(9).all(), "Hay NIT que no quedaron de 9 dígitos"
print(f"  NIT normalizados: {clientes['nit'].nunique():,} distintos")

# 3. Razón social: mayúsculas, sin espacios dobles, sufijo societario unificado
rs = (clientes["razon_social"].str.upper()
      .str.replace(r"\s+", " ", regex=True).str.strip())
rs = rs.str.replace(r"\s*S\.?A\.?S\.?$", " SAS", regex=True)
rs = rs.str.replace(r"\s*LTDA\.?$", " LTDA", regex=True)
clientes["razon_social"] = rs
print(f"  Razones sociales distintas: {clientes['razon_social'].nunique():,}")

# 4. Ciudad: diccionario construido en la Fase 2 (24 escrituras -> 7 ciudades)
CIUDADES = {
    "Pereira": "Pereira", "PEREIRA": "Pereira", "pereira": "Pereira",
    "Pereria": "Pereira", "Perera": "Pereira",
    "Santa Rosa de Cabal": "Santa Rosa de Cabal", "Sta Rosa de Cabal": "Santa Rosa de Cabal",
    "SANTA ROSA": "Santa Rosa de Cabal",
    "Dosquebradas": "Dosquebradas", "DOSQUEBRADAS": "Dosquebradas",
    "Dosquebrdas": "Dosquebradas", "Dos Quebradas": "Dosquebradas",
    "Manizales": "Manizales", "MANIZALES": "Manizales", "Manizalez": "Manizales",
    "Armenia": "Armenia", "ARMENIA": "Armenia", "Armenía": "Armenia",
    "Cartago": "Cartago", "CARTAGO": "Cartago", "Cartago Valle": "Cartago",
    "La Virginia": "La Virginia", "LA VIRGINIA": "La Virginia", "Lavirginia": "La Virginia",
}
sin_mapa = set(clientes["ciudad"]) - set(CIUDADES)
assert not sin_mapa, f"Ciudades sin mapear: {sin_mapa}"
clientes["ciudad"] = clientes["ciudad"].map(CIUDADES)
print(f"  Ciudades: {clientes['ciudad'].nunique()}")

# 5. Teléfono: solo dígitos, sin el indicativo 57, 10 dígitos
tel = clientes["telefono"].str.replace(r"\D", "", regex=True)
tel = tel.str.replace(r"^57(?=\d{10}$)", "", regex=True)
clientes["telefono"] = tel.where(tel.str.len() == 10)
print(f"  Teléfonos válidos: {clientes['telefono'].notna().sum():,} | vacíos: {clientes['telefono'].isna().sum():,}")

# 6. Email: 'å' -> '@', minúsculas, y los múltiples se separan en dos columnas
con_a = clientes["email"].str.contains("å", na=False)
em = clientes["email"].str.replace("å", "@", regex=False).str.lower()
partes_email = em.str.split(r"\s*\|\s*", expand=True, regex=True)
clientes["email"] = partes_email[0]
clientes["email_2"] = partes_email[1]
assert clientes["email"].dropna().str.contains("@").all(), "Hay emails sin @"
print(f"  Emails corregidos (å por @): {con_a.sum():,}")
print(f"  Emails con segundo correo separado: {clientes['email_2'].notna().sum():,}")

# 7. Fecha de alta: misma lógica que ventas (ambiguas como día/mes; si cae en el futuro, era mes/día)
clientes["tipo_fecha"] = clientes["fecha_alta"].apply(clasificar_fecha)
texto_alta = clientes["fecha_alta"]
clientes["fecha_alta"] = pd.concat(
    [pd.to_datetime(texto_alta[clientes["tipo_fecha"] == t], format=f) for t, f in FORMATOS.items()])
corregir_alta = (clientes["tipo_fecha"] == "barra: ambigua") & (clientes["fecha_alta"] > FECHA_MAX)
clientes.loc[corregir_alta, "fecha_alta"] = pd.to_datetime(texto_alta[corregir_alta], format="%m/%d/%Y")
clientes["fecha_alta_ambigua"] = (clientes["tipo_fecha"] == "barra: ambigua") & ~corregir_alta
clientes = clientes.drop(columns="tipo_fecha")
assert clientes["fecha_alta"].notna().all(), "Quedaron fechas de alta sin convertir"
print(f"  Fechas de alta ambiguas marcadas: {clientes['fecha_alta_ambigua'].sum():,}")

clientes["cupo_credito"] = clientes["cupo_credito"].astype(int)
print(f"  Filas que siguen: {len(clientes):,}")
# ==================================================
# CLIENTES - parte B: deduplicar por NIT y reasignar ventas
# ==================================================
# Regla: 1) mismo NIT = mismo cliente  2) más campos llenos  3) más ventas
#        4) id_cliente menor (desempate fijo para que el resultado sea reproducible)
clientes["campos_llenos"] = clientes[["telefono", "email", "direccion"]].notna().sum(axis=1)
clientes["n_ventas"] = clientes["id_cliente"].map(ventas["id_cliente"].value_counts()).fillna(0).astype(int)

clientes = clientes.sort_values(["nit", "campos_llenos", "n_ventas", "id_cliente"],
                                ascending=[True, False, False, True])
clientes["id_conservado"] = clientes.groupby("nit")["id_cliente"].transform("first")
duplicado = clientes["id_cliente"] != clientes["id_conservado"]
mapa_ids = clientes.loc[duplicado].set_index("id_cliente")["id_conservado"]

clientes = descartar(clientes, duplicado, "clientes", "Duplicado lógico (mismo NIT)")
clientes = clientes.drop(columns=["campos_llenos", "n_ventas", "id_conservado"]).sort_values("id_cliente")

# Reasignar las ventas y devoluciones de los registros descartados al registro conservado
reasignadas = ventas["id_cliente"].isin(mapa_ids.index)
ventas["id_cliente"] = ventas["id_cliente"].replace(mapa_ids)
dev_desde_ventas["id_cliente"] = dev_desde_ventas["id_cliente"].replace(mapa_ids)
print(f"  Ventas reasignadas al cliente conservado: {reasignadas.sum():,}")

validos = set(clientes["id_cliente"]) | {"C-99999"}
assert ventas["id_cliente"].isin(validos).all(), "Hay ventas con clientes que no existen"
assert clientes["nit"].is_unique, "Quedaron NIT repetidos"
print(f"  Clientes únicos finales: {len(clientes):,}")
# ==================================================
# DEVOLUCIONES
# ==================================================
print("\n== DEVOLUCIONES ==")
devoluciones = pd.read_csv(CRUDOS / "devoluciones.csv")
print(f"  Filas recibidas: {len(devoluciones):,}")

# 1. Fechas: misma lógica que ventas
devoluciones["tipo_fecha"] = devoluciones["fecha"].apply(clasificar_fecha)
devoluciones = descartar(devoluciones, devoluciones["tipo_fecha"] == "inválida", "devoluciones", "Fecha imposible")
texto_dev = devoluciones["fecha"]
devoluciones["fecha"] = pd.concat(
    [pd.to_datetime(texto_dev[devoluciones["tipo_fecha"] == t], format=f) for t, f in FORMATOS.items()])
corregir_dev = (devoluciones["tipo_fecha"] == "barra: ambigua") & (devoluciones["fecha"] > FECHA_MAX)
devoluciones.loc[corregir_dev, "fecha"] = pd.to_datetime(texto_dev[corregir_dev], format="%m/%d/%Y")
devoluciones["fecha_ambigua"] = (devoluciones["tipo_fecha"] == "barra: ambigua") & ~corregir_dev
devoluciones = devoluciones.drop(columns="tipo_fecha")
assert devoluciones["fecha"].notna().all() and devoluciones["fecha"].max() <= FECHA_MAX
print(f"  Fechas ambiguas marcadas: {devoluciones['fecha_ambigua'].sum():,}")

# 2. Motivos: 7 escrituras -> 5 motivos reales (diccionario construido en la Fase 2)
MOTIVOS = {
    "Vencido": "Vencido",
    "No solicitado": "No solicitado",
    "averiado": "Producto averiado",
    "Producto averiado": "Producto averiado",
    "PRODUCTO AVERIADO": "Producto averiado",
    "Error de despacho": "Error de despacho",
    "Empaque defectuoso": "Empaque defectuoso",
}
sin_mapa = set(devoluciones["motivo"]) - set(MOTIVOS)
assert not sin_mapa, f"Motivos sin mapear: {sin_mapa}"
devoluciones["motivo"] = devoluciones["motivo"].map(MOTIVOS)
print(f"  Motivos unificados: {devoluciones['motivo'].nunique()}")

# 3. Unir con las devoluciones que venían en ventas como cantidad negativa
devoluciones["origen"] = "devoluciones.csv"
dev_desde_ventas["motivo"] = "Sin motivo (cargada como venta negativa)"
dev_desde_ventas["id_devolucion"] = "DEV-V" + dev_desde_ventas["folio"].astype(str)
devoluciones = pd.concat(
    [devoluciones, dev_desde_ventas[["id_devolucion", "fecha", "id_cliente", "sku", "cantidad",
                                     "motivo", "fecha_ambigua", "origen"]]],
    ignore_index=True)

# 4. Clientes duplicados -> código conservado; claves comodín marcadas
devoluciones["id_cliente"] = devoluciones["id_cliente"].replace(mapa_ids)
devoluciones["sku_comodin"] = devoluciones["sku"] == "SKU-0000"
devoluciones["cliente_comodin"] = devoluciones["id_cliente"] == "C-99999"
assert devoluciones["id_cliente"].isin(validos).all(), "Devoluciones con clientes que no existen"
print(f"  Devoluciones totales (archivo + ventas negativas): {len(devoluciones):,}")

# ==================================================
# VISITAS
# ==================================================
print("\n== VISITAS ==")
with open(CRUDOS / "visitas_ruta.json", encoding="utf-8") as f:
    visitas = pd.json_normalize(json.load(f))
visitas.columns = [c.split(".")[-1] if c.startswith(("resultado.", "geo.")) else c.replace(".", "_")
                   for c in visitas.columns]
print(f"  Filas recibidas: {len(visitas):,}")

visitas["fecha"] = pd.to_datetime(visitas["fecha"], format="%Y-%m-%d")
assert visitas["fecha"].max() <= FECHA_MAX

# 1. Ruta: la tabla de vendedores es la fuente de verdad; la de la app se conserva aparte
vendedores = pd.read_excel(CRUDOS / "vendedores.xlsx")
visitas = visitas.rename(columns={"vendedor_ruta": "ruta_app"})
visitas["ruta"] = visitas["vendedor_id"].map(vendedores.set_index("id_vendedor")["ruta"])
print(f"  Visitas con ruta de la app distinta a la del vendedor: {(visitas['ruta'] != visitas['ruta_app']).sum():,}")

# 2. Visitas no efectivas sin motivo: se marcan, no se borran
sin_motivo = ~visitas["efectiva"] & visitas["motivo_no_venta"].isna()
visitas.loc[sin_motivo, "motivo_no_venta"] = "Sin motivo registrado"
print(f"  No efectivas sin motivo (marcadas): {sin_motivo.sum():,}")

# 3. Clientes duplicados -> código conservado
visitas["cliente_id"] = visitas["cliente_id"].replace(mapa_ids)
assert visitas["cliente_id"].isin(validos).all(), "Visitas con clientes que no existen"
print(f"  Filas que siguen: {len(visitas):,}")   

# ==================================================
# GUARDAR
# ==================================================
ventas.to_csv(PROCESADOS / "ventas_limpias.csv", index=False)
devoluciones.to_csv(PROCESADOS / "devoluciones_limpias.csv", index=False)
visitas.to_csv(PROCESADOS / "visitas_limpias.csv", index=False)
productos.to_csv(PROCESADOS / "productos_limpios.csv", index=False)
clientes.to_csv(PROCESADOS / "clientes_limpios.csv", index=False)
mapa_ids.rename("id_conservado").to_csv(PROCESADOS / "mapa_clientes_duplicados.csv")
pd.concat(descartados).to_csv(SALIDAS / "descartados.csv", index=False)
print(f"\nListo. Descartados totales: {sum(len(d) for d in descartados):,}")