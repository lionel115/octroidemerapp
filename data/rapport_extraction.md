# Rapport d'extraction

Généré le 18/11/2026 15:27

## Comptages

| Fichier CSV | Lignes |
|---|---:|
| deliberations.csv | 14 |
| modifications.csv | 8 |
| activites.csv | 134 |
| lignes_exoneration.csv | 7591 |
| tarif.csv | 9988 |
| correspondance_naf.csv | 4 |
| anomalies.csv | 118 |

### Lignes d'exonération par délibération

| Délibération | Lignes |
|---|---:|
| AP/25-15 | 7532 |
| CP/25-270 | 1 |
| CP/25-456 | 28 |
| CP/26-465 | 26 |
| CP/26-599 | 4 |

### Tarif

- lignes de titre ignorées (SECTION/CHAPITRE) : 118
- lignes tarif 2024 : 9978 (dont EX : 193, codes NC distincts : 9761)
- lignes modifiées par CP : 10

### Contrôle croisé annexe III (pdftotext vs pdfplumber)

- codes NC repérés par pdftotext dans la colonne CODE NC : 7543
- lignes extraites par pdfplumber (avant dédoublonnage) : 7542
- écarts : 1 manquant(s), 0 en trop

  - manquant : 89040010 x1

## Anomalies par type

| Type | Nombre | Exemple |
|---|---:|---|
| nc_absent_du_tarif_2024 | 60 | AP/25-15 — 90278011 (03.21Z) |
| code_taric_10_chiffres | 41 | tarif_om_2024.xlsx — ligne 1050 : 0706 10 00 10 |
| doublon_ligne_exoneration | 10 | AP/25-15 — ('AP/25-15', '39231090', '10.11Z', None) x2 |
| avis_commission_absent | 2 | cp_25_456.pdf — CP/25-456 : pas de date d'avis de la commission ad hoc |
| code_nc_6_chiffres | 2 | tarif_om_2024.xlsx — ligne 2519 : 2204 30 (position à 6 chiffres, complétée en 22043000) |
| code_nc_double_espace | 1 | tarif_om_2024.xlsx — ligne 3499 : '2920 22  00' |
| taux_non_numerique | 1 | tarif_om_2024.xlsx — ligne 9637 9021 10 10 omi = '=SUM(C9640)' |
| doublon_tarif | 1 | tarif_om_2024.xlsx — ligne 9363 : 87099000 (doublon supprimé) |
