# Exonération d'octroi de mer — Projet 2 M2 MIAGE

Outil qui indique à un importateur guadeloupéen s'il peut être exonéré d'octroi de mer, sur quels biens et pour combien.

## Équipe

| Membre | Rôle |
|---|---|
| Maelle | Cheffe de projet |
| Noah | Données (extraction) |
| Lionel | Modèle de données |
| Charles | API |

## Avancement

- [x] J1 — Extraction : script + CSV
- [x] J2 — Modèle : MCD, MLD, base SQLite chargée
- [ ] J3 — API (3 routes)
- [ ] J4 — Finalisation

## Lancer

Python 3.10+ et `pdftotext` (poppler) sont nécessaires.

```
pip install -r requirements.txt
python extraction/extract.py   # corpus/ -> data/csv/ + data/rapport_extraction.md
python db/load.py              # data/csv/ -> data/octroi.db
```

## Contenu

```
corpus/       fichiers fournis (délibérations PDF, tarif 2024)
extraction/   script d'extraction
data/csv/     CSV produits
db/           schema.sql, load.py, requete_unique.sql
docs/         MCD (png, pdf, source graphviz) et modele.md
ihm/          maquette de l'interface (pas encore reliée à l'API)
```

## Extraction (J1)

| CSV | Lignes |
|---|---:|
| deliberations | 14 (dont 7 abrogées, citées dans l'annexe I) |
| activites | 134 |
| lignes_exoneration | 7 591 |
| tarif | 9 988 |
| modifications | 8 (7 abrogations, 1 prorogation) |
| anomalies | 118 |

Principales anomalies : cellules NAF fusionnées dans les CP, codes NAF écrits de trois façons (0113Z, 01.13Z, 01.13Y), taux du tarif en texte (« 2,5 »), une formule Excel à la place d'un taux, lignes EX, codes à 10 chiffres, un doublon, et 60 codes NC des délibérations absents du tarif 2024. Le détail est dans `data/rapport_extraction.md`.

Pour vérifier l'annexe III, on compare deux outils : pdftotext trouve 7 543 codes, pdfplumber en extrait 7 542. L'écart vient d'un code cité dans une désignation.

## Modèle (J2)

Voir `docs/modele.md` et `docs/mcd.png`.
