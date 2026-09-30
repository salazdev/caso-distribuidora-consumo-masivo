import pandas as pd


def perfilar(df):
    """Una fila por columna: tipo, nulos, cardinalidad, rango y un ejemplo."""
    filas = []
    for col in df.columns:
        serie = df[col]
        info = {
            "columna": col,
            "tipo": str(serie.dtype),
            "nulos": serie.isna().sum(),
            "% nulos": round(serie.isna().mean() * 100, 1),
            "valores_unicos": serie.nunique(),
            "ejemplo": serie.dropna().iloc[0] if serie.notna().any() else None,
        }
        if pd.api.types.is_numeric_dtype(serie):
            info["min"] = serie.min()
            info["max"] = serie.max()
        filas.append(info)
    return pd.DataFrame(filas)


def patrones(serie):
    """Cambia cada digito por 9 y cada letra por A para ver los formatos."""
    return (serie.astype(str)
                 .str.replace(r"\d", "9", regex=True)
                 .str.replace(r"[A-Za-zÁÉÍÓÚáéíóúÑñ]", "A", regex=True)
                 .value_counts(dropna=False))


def huerfanos(hechos, col, referencia, col_ref=None):
    """Claves de 'hechos' que no existen en 'referencia'."""
    col_ref = col_ref or col
    mask = ~hechos[col].isin(referencia[col_ref])
    print(f"{col}: {mask.sum():,} filas huérfanas")
    return hechos.loc[mask, col].value_counts()


def clasificar_fecha(texto):
    """ISO, dd-mm-aaaa, barra (día/mes, mes/día o ambigua) o inválida."""
    if "-" in texto and len(texto.split("-")[0]) == 4:
        fecha = pd.to_datetime(texto, format="%Y-%m-%d", errors="coerce")
        if pd.isna(fecha):
            return "inválida"
        return "ISO"
    elif "-" in texto:
        return "dd-mm-aaaa"
    else:
        a, b, anio = texto.split("/")
        a, b = int(a), int(b)
        if a > 12:
            return "barra: día/mes seguro"
        if b > 12:
            return "barra: mes/día seguro"
        return "barra: ambigua"
