"""
Crée la base SQLite et la charge à partir des CSV produits par extraction/extract.py.

Usage :  python db/load.py [--csv data/csv] [--db data/octroi.db]
"""
import argparse
import csv
import sqlite3
from pathlib import Path

CATEGORIES = {"ETAB_SANTE": "Établissements et centres de santé"}


def lire(path):
    with open(path, encoding="utf-8") as fh:
        return [{k: (v if v != "" else None) for k, v in r.items()} for r in csv.DictReader(fh)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default="data/csv")
    ap.add_argument("--db", default="data/octroi.db")
    args = ap.parse_args()
    src = Path(args.csv)
    Path(args.db).unlink(missing_ok=True)
    con = sqlite3.connect(args.db)
    con.executescript((Path(__file__).parent / "schema.sql").read_text(encoding="utf-8"))
    cur = con.cursor()

    delibs = lire(src / "deliberations.csv")
    cur.executemany("""INSERT INTO deliberation VALUES (:numero,:organe,:nature,:objet,:date_seance,
                       :date_publication,:date_avis_commission,:date_debut,:date_fin,:fichier)""", delibs)
    taux_delib = {d["numero"]: float(d["taux_applique"] or 0) for d in delibs}

    cur.executemany("""INSERT INTO modification (source,cible,type,date_effet,nouvelle_date_fin)
                       VALUES (:source,:cible,:type,:date_effet,:nouvelle_date_fin)""",
                    lire(src / "modifications.csv"))

    acts = lire(src / "activites.csv")
    cur.executemany("INSERT INTO activite VALUES (:code_naf,:nomenclature,:section,:libelle)", acts)
    cur.executemany("INSERT INTO agrement VALUES (:numero,:code_naf,:ordre)", [a for a in acts if a["numero"]])
    cur.executemany("INSERT INTO categorie_beneficiaire VALUES (?,?)", CATEGORIES.items())
    cur.executemany("INSERT INTO beneficiaire (code_naf) VALUES (?)", [(a["code_naf"],) for a in acts])
    cur.executemany("INSERT INTO beneficiaire (categorie) VALUES (?)", [(c,) for c in CATEGORIES])
    benef = {r[0] or r[1]: r[2] for r in cur.execute("SELECT code_naf, categorie, id FROM beneficiaire")}
    cur.executemany("INSERT INTO correspondance_naf VALUES (:naf_2008,:naf_2025,:source)",
                    lire(src / "correspondance_naf.csv"))

    tarif = lire(src / "tarif.csv")
    lignes = lire(src / "lignes_exoneration.csv")
    # référentiel des biens : libellé du tarif en priorité, sinon celui de la délibération
    biens = {}
    for l in lignes:
        biens.setdefault(l["code_nc"], l["designation"])
    for t in tarif:
        if t["ex"] == "0" and not t["complement"]:
            biens[t["code_nc"]] = t["libelle"]
        biens.setdefault(t["code_nc"], t["libelle"])
    cur.executemany("INSERT INTO bien VALUES (?,?)", biens.items())

    cur.executemany("""INSERT INTO exoneration (numero,code_nc,beneficiaire_id,designation,taux_applique,
                       date_debut_ligne,date_fin_ligne,page) VALUES (?,?,?,?,?,?,?,?)""",
                    [(l["numero"], l["code_nc"], benef[l["code_naf"] or l["categorie"]], l["designation"],
                      taux_delib[l["numero"]], l["date_debut_ligne"], l["date_fin_ligne"], l["page"])
                     for l in lignes])

    sources = {}
    for t in tarif:
        if t["source"] not in sources:
            sources[t["source"]] = (t["source"], "Tarif d'octroi de mer 2024 (Karudata)" if t["source"] == "TARIF_2024"
                                    else f"Modification du tarif par {t['source']}", t["date_effet"],
                                    None if t["source"] == "TARIF_2024" else t["source"])
    cur.executemany("INSERT INTO source_tarif VALUES (?,?,?,?)", sources.values())
    cur.executemany("""INSERT INTO taux (source,code_nc,complement,ex,libelle,ome,omre,omi,omri,ecart)
                       VALUES (:source,:code_nc,:complement,:ex,:libelle,:ome,:omre,:omi,:omri,:ecart)""",
                    [{**t, "complement": t["complement"] or ""} for t in tarif])
    con.commit()

    for table in ["deliberation", "modification", "bien", "activite", "agrement", "beneficiaire",
                  "correspondance_naf", "exoneration", "source_tarif", "taux"]:
        print(f"{table:22s} {cur.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]:>6}")
    con.close()


if __name__ == "__main__":
    main()
