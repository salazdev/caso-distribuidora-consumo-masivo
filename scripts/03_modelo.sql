-- ============================================================
-- 03_modelo.sql  -  Modelo estrella (Fase 3)
-- Constelación: 3 tablas de hechos que comparten 4 dimensiones
-- Se puede ejecutar varias veces: borra y recrea todo.
-- ============================================================
CREATE DATABASE IF NOT EXISTS distribuidora_dw
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_0900_ai_ci;

USE distribuidora_dw;

-- ------------------------------------------------------------
-- 1. Borrar: primero los hechos (dependen de las dimensiones)
-- ------------------------------------------------------------
DROP TABLE IF EXISTS fact_visitas;
DROP TABLE IF EXISTS fact_devoluciones;
DROP TABLE IF EXISTS fact_ventas;
DROP TABLE IF EXISTS dim_fecha;
DROP TABLE IF EXISTS dim_cliente;
DROP TABLE IF EXISTS dim_vendedor;
DROP TABLE IF EXISTS dim_producto;

-- ------------------------------------------------------------
-- 2. Dimensiones
-- ------------------------------------------------------------
CREATE TABLE dim_producto (
    sku                  VARCHAR(10)   NOT NULL,
    descripcion          VARCHAR(100)  NOT NULL,
    categoria            VARCHAR(20)   NOT NULL,
    proveedor            VARCHAR(10),
    costo_unitario       DECIMAL(12,2) NOT NULL,
    precio_lista         DECIMAL(12,2) NOT NULL,
    costo_imputado       BOOLEAN       NOT NULL DEFAULT FALSE,
    precio_desde_ventas  BOOLEAN       NOT NULL DEFAULT FALSE,
    PRIMARY KEY (sku)
);

CREATE TABLE dim_vendedor (
    id_vendedor      VARCHAR(10)   NOT NULL,
    nombre           VARCHAR(60)   NOT NULL,
    ruta             VARCHAR(10)   NOT NULL,
    ciudad_base      VARCHAR(40)   NOT NULL,
    fecha_ingreso    DATE          NOT NULL,
    salario_mensual  DECIMAL(12,2) NOT NULL,
    PRIMARY KEY (id_vendedor)
);

CREATE TABLE dim_cliente (
    id_cliente          VARCHAR(14)   NOT NULL,
    nit                 VARCHAR(15)   NOT NULL,
    nit_dv              VARCHAR(2),
    razon_social        VARCHAR(60)   NOT NULL,
    tipo_negocio        VARCHAR(24)   NOT NULL,
    ciudad              VARCHAR(40)   NOT NULL,
    direccion           VARCHAR(40)   NOT NULL,
    telefono            VARCHAR(20),
    email               VARCHAR(60),
    email_2             VARCHAR(60),
    ruta_asignada       VARCHAR(8)    NOT NULL,
    fecha_alta          DATE          NOT NULL,
    fecha_alta_ambigua  BOOLEAN       NOT NULL DEFAULT FALSE,
    cupo_credito        DECIMAL(12,2) NOT NULL,
    PRIMARY KEY (id_cliente)
);

CREATE TABLE dim_fecha (
    fecha_key         INT          NOT NULL,
    fecha             DATE         NOT NULL,
    anio              SMALLINT     NOT NULL,
    trimestre         TINYINT      NOT NULL,
    mes               TINYINT      NOT NULL,
    nombre_mes        VARCHAR(12)  NOT NULL,
    anio_mes          CHAR(7)      NOT NULL,
    semana_iso        TINYINT      NOT NULL,
    dia_mes           TINYINT      NOT NULL,
    dia_semana        TINYINT      NOT NULL,
    nombre_dia        VARCHAR(10)  NOT NULL,
    es_fin_de_semana  BOOLEAN      NOT NULL,
    es_festivo        BOOLEAN      NOT NULL DEFAULT FALSE,
    nombre_festivo    VARCHAR(100),
    PRIMARY KEY (fecha_key),
    UNIQUE KEY uk_fecha (fecha)
);

-- ------------------------------------------------------------
-- 3. Hechos
-- ------------------------------------------------------------
-- Grano: 1 fila = 1 transacción (folio) de un SKU
CREATE TABLE fact_ventas (
    folio            INT           NOT NULL,
    fecha_key        INT           NOT NULL,
    id_cliente       VARCHAR(14)   NOT NULL,
    sku              VARCHAR(10)   NOT NULL,
    id_vendedor      VARCHAR(10)   NOT NULL,
    canal            VARCHAR(12)   NOT NULL,
    cantidad         SMALLINT      NOT NULL,
    precio_unitario  DECIMAL(12,2) NOT NULL,
    descuento_pct    DECIMAL(5,2)  NOT NULL,
    venta_bruta      DECIMAL(14,2) NOT NULL,   -- cantidad x precio
    valor_descuento  DECIMAL(14,2) NOT NULL,   -- venta_bruta x descuento
    venta_neta       DECIMAL(14,2) NOT NULL,   -- venta_bruta - valor_descuento
    costo_total      DECIMAL(14,2) NOT NULL,   -- cantidad x costo unitario
    fecha_ambigua    BOOLEAN       NOT NULL DEFAULT FALSE,
    precio_imputado  BOOLEAN       NOT NULL DEFAULT FALSE,
    sku_comodin      BOOLEAN       NOT NULL DEFAULT FALSE,
    cliente_comodin  BOOLEAN       NOT NULL DEFAULT FALSE,
    PRIMARY KEY (folio),
    CONSTRAINT fk_ventas_fecha    FOREIGN KEY (fecha_key)   REFERENCES dim_fecha (fecha_key),
    CONSTRAINT fk_ventas_cliente  FOREIGN KEY (id_cliente)  REFERENCES dim_cliente (id_cliente),
    CONSTRAINT fk_ventas_producto FOREIGN KEY (sku)         REFERENCES dim_producto (sku),
    CONSTRAINT fk_ventas_vendedor FOREIGN KEY (id_vendedor) REFERENCES dim_vendedor (id_vendedor)
);

-- Grano: 1 fila = 1 devolución de un SKU
CREATE TABLE fact_devoluciones (
    id_devolucion    VARCHAR(16)   NOT NULL,
    fecha_key        INT           NOT NULL,
    id_cliente       VARCHAR(14)   NOT NULL,
    sku              VARCHAR(10)   NOT NULL,
    cantidad         SMALLINT      NOT NULL,
    motivo           VARCHAR(50)   NOT NULL,
    origen           VARCHAR(40)   NOT NULL,
    fecha_ambigua    BOOLEAN       NOT NULL DEFAULT FALSE,
    sku_comodin      BOOLEAN       NOT NULL DEFAULT FALSE,
    cliente_comodin  BOOLEAN       NOT NULL DEFAULT FALSE,
    PRIMARY KEY (id_devolucion),
    CONSTRAINT fk_dev_fecha    FOREIGN KEY (fecha_key)  REFERENCES dim_fecha (fecha_key),
    CONSTRAINT fk_dev_cliente  FOREIGN KEY (id_cliente) REFERENCES dim_cliente (id_cliente),
    CONSTRAINT fk_dev_producto FOREIGN KEY (sku)        REFERENCES dim_producto (sku)
);

-- Grano: 1 fila = 1 visita de un vendedor a un cliente
CREATE TABLE fact_visitas (
    visita_id        VARCHAR(12)   NOT NULL,
    fecha_key        INT           NOT NULL,
    id_cliente       VARCHAR(14)   NOT NULL,
    id_vendedor      VARCHAR(10)   NOT NULL,
    efectiva         BOOLEAN       NOT NULL,
    motivo_no_venta  VARCHAR(30),
    duracion_min     SMALLINT      NOT NULL,
    lat              DECIMAL(9,5),
    lon              DECIMAL(9,5),
    ruta_app         VARCHAR(10),              -- dato de la app, NO confiable (ver Fase 2)
    PRIMARY KEY (visita_id),
    CONSTRAINT fk_vis_fecha    FOREIGN KEY (fecha_key)   REFERENCES dim_fecha (fecha_key),
    CONSTRAINT fk_vis_cliente  FOREIGN KEY (id_cliente)  REFERENCES dim_cliente (id_cliente),
    CONSTRAINT fk_vis_vendedor FOREIGN KEY (id_vendedor) REFERENCES dim_vendedor (id_vendedor)
);

-- ------------------------------------------------------------
-- 4. Índices extra para los filtros más comunes
--    (MySQL ya crea un índice por cada clave foránea)
-- ------------------------------------------------------------
CREATE INDEX ix_ventas_canal       ON fact_ventas (canal);
CREATE INDEX ix_cliente_ciudad     ON dim_cliente (ciudad);
CREATE INDEX ix_producto_categoria ON dim_producto (categoria);
