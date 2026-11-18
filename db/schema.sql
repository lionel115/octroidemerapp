-- Schéma de la base exonérations d'octroi de mer (SQLite)
-- Dates au format ISO 'AAAA-MM-JJ' (comparaison lexicographique = chronologique).

PRAGMA foreign_keys = ON;

DROP VIEW IF EXISTS v_naf_equivalent;
DROP VIEW IF EXISTS v_deliberation_vigueur;
DROP TABLE IF EXISTS taux;
DROP TABLE IF EXISTS source_tarif;
DROP TABLE IF EXISTS exoneration;
DROP TABLE IF EXISTS correspondance_naf;
DROP TABLE IF EXISTS agrement;
DROP TABLE IF EXISTS beneficiaire;
DROP TABLE IF EXISTS categorie_beneficiaire;
DROP TABLE IF EXISTS activite;
DROP TABLE IF EXISTS bien;
DROP TABLE IF EXISTS modification;
DROP TABLE IF EXISTS deliberation;

-- Décision du conseil régional (AP, CP ou CR)
CREATE TABLE deliberation (
    numero               TEXT PRIMARY KEY,                 -- 'CP/26-599'
    organe               TEXT NOT NULL CHECK (organe IN ('AP', 'CP', 'CR')),
    nature               TEXT NOT NULL CHECK (nature IN ('CADRE', 'EXONERATION_SECTORIELLE',
                             'EXONERATION_PARTIELLE', 'EXONERATION_CATEGORIE', 'PROROGATION',
                             'MODIFICATION_TARIF', 'REFERENCEE')),
    objet                TEXT,
    date_seance          TEXT,
    date_publication     TEXT,
    date_avis_commission TEXT,
    date_debut           TEXT,                              -- entrée en vigueur
    date_fin             TEXT,                              -- fin initiale (NULL = sans terme)
    fichier              TEXT
);

-- Décision qui en modifie une autre (abrogation, prorogation)
CREATE TABLE modification (
    id                INTEGER PRIMARY KEY,
    source            TEXT NOT NULL REFERENCES deliberation (numero),
    cible             TEXT NOT NULL REFERENCES deliberation (numero),
    type              TEXT NOT NULL CHECK (type IN ('ABROGATION', 'PROROGATION')),
    date_effet        TEXT,
    nouvelle_date_fin TEXT,
    CHECK (source <> cible),
    CHECK (type <> 'PROROGATION' OR nouvelle_date_fin IS NOT NULL)
);

-- Bien importé, identifié par son code NC (8 chiffres, sans espaces)
CREATE TABLE bien (
    code_nc     TEXT PRIMARY KEY CHECK (length(code_nc) = 8 AND code_nc NOT GLOB '*[^0-9]*'),
    designation TEXT
);

-- Activité INSEE (NAF 2008 ou NAF 2025), format '01.13Z'
CREATE TABLE activite (
    code_naf     TEXT PRIMARY KEY CHECK (code_naf GLOB '[0-9][0-9].[0-9][0-9][A-Z]'),
    nomenclature TEXT NOT NULL CHECK (nomenclature IN ('NAF2008', 'NAF2025')),
    section      TEXT,
    libelle      TEXT
);

-- Bénéficiaire défini sans code NAF (ex. établissements et centres de santé)
CREATE TABLE categorie_beneficiaire (
    code    TEXT PRIMARY KEY,
    libelle TEXT NOT NULL
);

-- Bénéficiaire = une activité NAF OU une catégorie (généralisation exclusive)
CREATE TABLE beneficiaire (
    id        INTEGER PRIMARY KEY,
    code_naf  TEXT UNIQUE REFERENCES activite (code_naf),
    categorie TEXT UNIQUE REFERENCES categorie_beneficiaire (code),
    CHECK ((code_naf IS NULL) <> (categorie IS NULL))
);

-- Activités agréées par une délibération cadre (annexe II d'AP/25-15)
CREATE TABLE agrement (
    numero   TEXT NOT NULL REFERENCES deliberation (numero),
    code_naf TEXT NOT NULL REFERENCES activite (code_naf),
    ordre    INTEGER,
    PRIMARY KEY (numero, code_naf)
);

-- Passage NAF 2008 -> NAF 2025, lu dans les CP à double colonne
CREATE TABLE correspondance_naf (
    naf_2008 TEXT NOT NULL REFERENCES activite (code_naf),
    naf_2025 TEXT NOT NULL REFERENCES activite (code_naf),
    source   TEXT REFERENCES deliberation (numero),
    PRIMARY KEY (naf_2008, naf_2025)
);

-- Entité-association centrale : un bien x un bénéficiaire x une décision
CREATE TABLE exoneration (
    id               INTEGER PRIMARY KEY,
    numero           TEXT NOT NULL REFERENCES deliberation (numero),
    code_nc          TEXT NOT NULL REFERENCES bien (code_nc),
    beneficiaire_id  INTEGER NOT NULL REFERENCES beneficiaire (id),
    designation      TEXT,                                 -- libellé tel qu'écrit dans la délibération
    taux_applique    REAL NOT NULL DEFAULT 0 CHECK (taux_applique >= 0),
    date_debut_ligne TEXT,                                 -- bornes propres à la ligne (colonnes NAF 2008 / 2025)
    date_fin_ligne   TEXT,
    page             INTEGER,
    UNIQUE (numero, code_nc, beneficiaire_id, date_debut_ligne, date_fin_ligne)
);
CREATE INDEX ix_ligne_nc ON exoneration (code_nc, beneficiaire_id);

-- Publication d'un tarif : tarif annuel (Karudata) ou modification par délibération
CREATE TABLE source_tarif (
    code        TEXT PRIMARY KEY,                          -- 'TARIF_2024', 'CP/26-606'
    libelle     TEXT,
    date_effet  TEXT NOT NULL,
    numero      TEXT REFERENCES deliberation (numero)
);

-- Taux par code NC ; plusieurs lignes possibles par code (sous-cas EX, codes TARIC à 10 chiffres)
CREATE TABLE taux (
    id         INTEGER PRIMARY KEY,
    source     TEXT NOT NULL REFERENCES source_tarif (code),
    code_nc    TEXT NOT NULL REFERENCES bien (code_nc),
    complement TEXT NOT NULL DEFAULT '',                   -- 2 chiffres TARIC éventuels
    ex         INTEGER NOT NULL DEFAULT 0 CHECK (ex IN (0, 1)),
    libelle    TEXT,
    ome        REAL,
    omre       REAL,
    omi        REAL,
    omri       REAL,
    ecart      TEXT CHECK (ecart IN ('A', 'B') OR ecart IS NULL)
);
CREATE INDEX ix_tarif_nc ON taux (code_nc, source);

-- Période de vigueur effective : fin prorogée et date d'abrogation éventuelles
CREATE VIEW v_deliberation_vigueur AS
SELECT d.numero,
       d.nature,
       d.date_debut,
       d.date_fin                                       AS date_fin_initiale,
       COALESCE((SELECT MAX(m.nouvelle_date_fin) FROM modification m
                  WHERE m.cible = d.numero AND m.type = 'PROROGATION'), d.date_fin)
                                                        AS date_fin_effective,
       (SELECT group_concat(m.source) FROM modification m
         WHERE m.cible = d.numero AND m.type = 'PROROGATION')  AS prorogee_par,
       (SELECT MIN(m.date_effet) FROM modification m
         WHERE m.cible = d.numero AND m.type = 'ABROGATION')   AS date_abrogation,
       (SELECT group_concat(m.source) FROM modification m
         WHERE m.cible = d.numero AND m.type = 'ABROGATION')   AS abrogee_par
FROM deliberation d;

-- Un code NAF et ses équivalents dans l'autre nomenclature (et lui-même)
CREATE VIEW v_naf_equivalent AS
SELECT code_naf AS code, code_naf AS equivalent FROM activite
UNION SELECT naf_2008, naf_2025 FROM correspondance_naf
UNION SELECT naf_2025, naf_2008 FROM correspondance_naf;
