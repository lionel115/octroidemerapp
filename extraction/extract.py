"""
Extraction des délibérations (PDF) et du tarif (Excel) vers data/csv/.
Lancer depuis la racine : python extraction/extract.py
Génère aussi data/rapport_extraction.md (nombre de lignes + anomalies).
"""
import argparse
import csv
import datetime as dt
import re
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

import openpyxl
import pdfplumber

MOIS = {"janvier": 1, "février": 2, "fevrier": 2, "mars": 3, "avril": 4, "mai": 5, "juin": 6,
        "juillet": 7, "août": 8, "aout": 8, "septembre": 9, "octobre": 10, "novembre": 11,
        "décembre": 12, "decembre": 12}
RE_DATE_FR = r"(\d{1,2})(?:er)?\s+(janvier|f[ée]vrier|mars|avril|mai|juin|juillet|ao[uû]t|septembre|octobre|novembre|d[ée]cembre)\s+(\d{4})"
RE_NC = re.compile(r"\b(\d{4})\s?(\d{2})\s?(\d{2})\b")
RE_NUM_DELIB = re.compile(r"\b(AP|CP|CR)/(\d{2})-(\d+(?:-\d+)?)\b")

anomalies = []          # (fichier, type, détail)


def anomalie(fichier, typ, detail):
    anomalies.append((fichier, typ, detail))


# --------------------------------------------------------------------------- normalisation

def date_fr(txt):
    m = re.search(RE_DATE_FR, txt, re.I)
    if not m:
        return None
    j, mois, a = m.groups()
    mois = mois.lower().replace("û", "u")
    return dt.date(int(a), MOIS.get(mois, MOIS.get(mois.replace("é", "e"))), int(j)).isoformat()


def date_num(txt):
    """09/04/25 ou 09/04/2025 -> ISO"""
    m = re.search(r"(\d{2})/(\d{2})/(\d{2,4})", txt)
    if not m:
        return None
    j, mo, a = m.groups()
    a = int(a) + (2000 if len(a) == 2 else 0)
    return dt.date(a, int(mo), int(j)).isoformat()


def norm_nc(txt):
    """'8429 52 10' / '84295210' -> '84295210' (8 chiffres). None si pas un code NC."""
    if txt is None:
        return None
    s = re.sub(r"\s+", "", str(txt))
    return s if re.fullmatch(r"\d{8}", s) else None


def norm_naf(txt):
    """'0113Z' / '01.13Z' / '01.13 Z' -> '01.13Z' (format SIRENE)."""
    if txt is None:
        return None
    s = re.sub(r"[\s.]", "", str(txt)).upper()
    m = re.fullmatch(r"(\d{2})(\d{2})([A-Z])", s)
    return f"{m.group(1)}.{m.group(2)}{m.group(3)}" if m else None


def norm_num_delib(txt):
    m = RE_NUM_DELIB.search(txt)
    return f"{m.group(1)}/{m.group(2)}-{m.group(3)}" if m else None


def clean(txt):
    return re.sub(r"\s+", " ", txt or "").strip()


def taux(v):
    """'2,5' / 2.5 / '7' -> float ; formule ou vide -> None"""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().replace(",", ".").replace("%", "")
    try:
        return float(s)
    except ValueError:
        return None


# --------------------------------------------------------------------------- en-tête délibération

def pdf_text(path):
    return subprocess.run(["pdftotext", "-layout", str(path), "-"], capture_output=True,
                          text=True, check=True).stdout


def entete(path, txt):
    """Métadonnées communes à toutes les délibérations."""
    f = path.name
    num = norm_num_delib(re.search(r"Délibération\s*:\s*N°\s*(\S+)", txt).group(1))
    seance = date_fr(re.search(r"SEANCE DU \w+ (.+)", txt).group(1))
    m_obj = re.search(r"Objet\s+(.+?)\n\s*\n", txt, re.S)
    objet = clean(m_obj.group(1)) if m_obj else ""
    if not objet:
        anomalie(f, "objet_absent", num)

    m_pub = re.search(r"publié (?:sur le site internet de la Région Guadeloupe )?le\s+" + RE_DATE_FR, txt)
    publication = date_fr(m_pub.group(0)) if m_pub else None
    if not publication:
        anomalie(f, "date_publication_absente", num)

    avis = None
    m_avis = re.search(r"Avis de la Commission Ad.hoc Octroi de Mer(?: du ([\d/]+))?\s*:\s*(\w*)", txt)
    if m_avis and m_avis.group(1):
        avis = date_num(m_avis.group(1))
    else:
        m2 = re.search(r"avis favorable de la commission ad hoc octroi de mer du\s+" + RE_DATE_FR, txt, re.I)
        avis = date_fr(m2.group(0)) if m2 else None
    if not avis:
        anomalie(f, "avis_commission_absent", f"{num} : pas de date d'avis de la commission ad hoc")

    decide = txt[txt.find("DECIDE"):] if "DECIDE" in txt else txt
    m_deb = re.search(r"(?:applicable à partir du|entrera en vigueur au)\s+" + RE_DATE_FR, decide)
    debut_explicite = date_fr(m_deb.group(0)) if m_deb else None
    m_fin = re.search(r"applicable jusqu.au\s+" + RE_DATE_FR, decide)
    fin = date_fr(m_fin.group(0)) if m_fin else None

    m_taux = re.search(r"appliquer un\s+taux de\s+([\d,]+)\s*%", decide)
    taux_applique = taux(m_taux.group(1)) if m_taux else 0.0

    return dict(numero=num, organe=num.split("/")[0], date_seance=seance, date_publication=publication,
                date_avis_commission=avis, objet=objet, date_debut_explicite=debut_explicite,
                date_fin_texte=fin, taux_applique=taux_applique, fichier=f, decide=decide)


def nature(d):
    o = d["objet"].lower()
    if d["organe"] == "AP" and "annexe iii" in d["decide"].lower():
        return "CADRE"
    if "prorogation" in o:
        return "PROROGATION"
    if "modification du taux" in o or "modifier l’annexe i" in d["decide"].lower() or "modifier l'annexe i" in d["decide"].lower():
        return "MODIFICATION_TARIF"
    if "partielle" in o:
        return "EXONERATION_PARTIELLE"
    if "santé" in o:
        return "EXONERATION_CATEGORIE"
    return "EXONERATION_SECTORIELLE"


# --------------------------------------------------------------------------- tableaux des CP

def cell_naf(cell):
    """'23.61Z\\nFabrication d’éléments…' -> ('23.61Z', 'Fabrication d’éléments…')"""
    if not cell:
        return None, None
    m = re.search(r"\b(\d{2}\.?\d{2}\s?[A-Z])\b", cell)
    if not m:
        return None, None
    lib = clean(cell[m.end():])
    return norm_naf(m.group(1)), lib or None


def colonnes_naf(header):
    """Repère les colonnes NAF et leur période de validité éventuelle."""
    cols = []
    for i, h in enumerate(header):
        hs = clean(h).lower()
        if "naf" not in hs:
            continue
        debut = fin = None
        if "jusqu" in hs:
            fin = date_fr(hs)
        if "partir du" in hs:
            debut = date_fr(hs)
        nomenclature = "NAF2025" if debut and debut >= "2027-01-01" else "NAF2008"
        cols.append((i, debut, fin, nomenclature))
    return cols


def lignes_cp(path, d, txt):
    """Lignes d'exonération d'une CP (tableaux pdfplumber, repli texte si pas de tableau)."""
    out, f = [], path.name
    cat = "ETAB_SANTE" if d["nature"] == "EXONERATION_CATEGORIE" else None
    report = {}                                      # colonne -> dernier NAF lu (cellules fusionnées)
    with pdfplumber.open(path) as pdf:
        for pno, page in enumerate(pdf.pages, 1):
            for t in page.extract_tables():
                if not t or not any("code nc" in clean(c).lower() for c in t[0] if c):
                    continue
                header = t[0]
                i_nc = next(i for i, c in enumerate(header) if c and "code nc" in c.lower())
                i_des = next((i for i, c in enumerate(header) if c and "signation" in c), i_nc + 1)
                cols = colonnes_naf(header)
                if d["nature"] == "MODIFICATION_TARIF":
                    continue                         # traité dans tarif_cp()
                for row in t[1:]:
                    nc = norm_nc(row[i_nc])
                    if not nc:
                        if any(row):
                            anomalie(f, "ligne_sans_code_nc", f"p{pno} {clean(str(row))[:80]}")
                        continue
                    des = clean(row[i_des])
                    if not cols:
                        out.append(dict(numero=d["numero"], code_nc=nc, designation=des, code_naf=None,
                                        nomenclature=None, categorie=cat, date_debut_ligne=None,
                                        date_fin_ligne=None, page=pno))
                        if not cat:
                            anomalie(f, "beneficiaire_inconnu", nc)
                        continue
                    for (ci, deb, fin, nomencl) in cols:
                        naf, lib = cell_naf(row[ci])
                        if naf:
                            report[ci] = (naf, lib)
                        elif ci in report:
                            naf, lib = report[ci]    # cellule fusionnée : NAF écrit plus haut
                        else:
                            anomalie(f, "naf_absent", f"p{pno} {nc}")
                            continue
                        out.append(dict(numero=d["numero"], code_nc=nc, designation=des, code_naf=naf,
                                        nomenclature=nomencl, categorie=None, libelle_naf=lib,
                                        date_debut_ligne=deb, date_fin_ligne=fin, page=pno))
    if not out and d["nature"] in ("EXONERATION_SECTORIELLE", "EXONERATION_PARTIELLE", "EXONERATION_CATEGORIE"):
        # Repli : tableau sans bordures (ex. CP/25-270) -> lecture du texte de l'article 1
        art1 = d["decide"][d["decide"].find("Article 1"):d["decide"].find("Article 2")]
        nafs = [norm_naf(x) for x in re.findall(r"\b\d{2}\.\d{2}[A-Z]\b", art1)]
        for line in art1.splitlines():
            m = re.match(r"\s*(\d{4} \d{2} \d{2})\s+(.*)", line)
            if not m:
                continue
            nc = norm_nc(m.group(1))
            des = clean(re.sub(r"\s{3,}.*", "", m.group(2)))
            # la désignation est répartie sur les lignes voisines : on reprend le bloc autour
            bloc = art1.splitlines()
            k = bloc.index(line)
            morceaux = [clean(re.split(r"\s{3,}", b.strip())[0]) for b in bloc[max(0, k - 2):k + 3]
                        if b.strip() and not re.search(r"Code NC|Désignation|Secteur|d’activité|Code NAF", b)]
            des = clean(" ".join(x for x in morceaux if not RE_NC.match(x)) or des)
            for naf in nafs or [None]:
                out.append(dict(numero=d["numero"], code_nc=nc, designation=des, code_naf=naf,
                                nomenclature="NAF2008" if naf else None, categorie=cat,
                                date_debut_ligne=None, date_fin_ligne=None, page=None))
        anomalie(f, "tableau_sans_bordure", f"{d['numero']} lu par repli texte ({len(out)} ligne(s))")
    return out


def tarif_cp(path, d):
    """Lignes de tarif modifiées par une CP (ex. CP/26-606) : lues dans le texte."""
    out = []
    for line in d["decide"].splitlines():
        m = re.match(r"\s*(EX)?\s*(\d{4} \d{2} \d{2})\s+(.+?)\s{2,}([\d,]+)\s+([\d,]+)\s+([\d,]+)\s+([\d,]+)\s*$", line)
        if m:
            ex, nc, lib, a, b, c, e = m.groups()
            out.append(dict(source=d["numero"], code_nc=norm_nc(nc), complement="", ex=1 if ex else 0,
                            libelle=clean(lib), ome=taux(a), omre=taux(b), omi=taux(c), omri=taux(e),
                            ecart=None, date_effet=d["date_debut_explicite"]))
    return out


def prorogations(d):
    out = []
    if d["nature"] != "PROROGATION":
        return out
    cible = norm_num_delib(re.search(r"prorogation du délai d.application de la délibération n°\s*(\S+)",
                                     d["decide"]).group(1))
    nouvelle_fin = date_fr(re.search(r"applicable jusqu.au\s+" + RE_DATE_FR, d["decide"]).group(0))
    out.append(dict(source=d["numero"], cible=cible, type="PROROGATION", date_effet=d["date_publication"],
                    nouvelle_date_fin=nouvelle_fin))
    return out


# --------------------------------------------------------------------------- AP/25-15

def traiter_ap(path, d, txt):
    f = path.name
    delibs_ref, modifs, activites, lignes = [], [], [], []

    # Annexe I : délibérations abrogées
    a1 = txt[txt.find("ANNEXE I\n") if "ANNEXE I\n" in txt else txt.find("ANNEXE I"):txt.find("ANNEXE II")]
    for m in re.finditer(r"^\s*\d+\.\s+((?:AP|CP|CR)/[\d\-]+)\s+(.+?)\s*$", a1, re.M):
        num, date_txt = m.group(1), m.group(2)
        delibs_ref.append(dict(numero=num, organe=num.split("/")[0], date_seance=date_fr(date_txt),
                               date_publication=None, date_avis_commission=None,
                               objet="Délibération abrogée (citée en annexe I d'AP/25-15, texte non fourni)",
                               nature="REFERENCEE", date_debut=None, date_fin=None, taux_applique=None,
                               fichier=None))
        modifs.append(dict(source=d["numero"], cible=num, type="ABROGATION",
                           date_effet=d["date_debut_explicite"], nouvelle_date_fin=None))

    with pdfplumber.open(path) as pdf:
        n_pages = len(pdf.pages)
        for pno in range(n_pages):
            page = pdf.pages[pno]
            for t in page.extract_tables():
                if not t or not t[0]:
                    continue
                head = " ".join(clean(c) for c in t[0] if c).upper()
                # Annexe II : activités agréées
                if "LIBELLE NAF" in head and "CODE NC" not in head:
                    for row in t[1:]:
                        cells = [clean(c) for c in row if c and clean(c)]
                        if len(cells) >= 3 and norm_naf(cells[2]):
                            activites.append(dict(code_naf=norm_naf(cells[2]), section=cells[1],
                                                  libelle=" ".join(cells[3:]), nomenclature="NAF2008",
                                                  ordre=int(cells[0].rstrip(".")), numero=d["numero"]))
                        elif any(cells):
                            anomalie(f, "annexe2_ligne_illisible", f"p{pno+1} {cells}")
                # Annexe III : couples NAF x NC
                elif "CODE NC" in head and "NAF" in head:
                    for row in t[1:]:
                        if len(row) < 5:
                            anomalie(f, "annexe3_ligne_courte", f"p{pno+1} {row}")
                            continue
                        sec, naf, lib, nc, des = row[:5]
                        naf_n, nc_n = norm_naf(naf), norm_nc(nc)
                        if not naf_n or not nc_n:
                            if any(row):
                                anomalie(f, "annexe3_code_illisible", f"p{pno+1} {clean(str(row))[:100]}")
                            continue
                        lignes.append(dict(numero=d["numero"], code_nc=nc_n, designation=clean(des),
                                           code_naf=naf_n, nomenclature="NAF2008", categorie=None,
                                           libelle_naf=clean(lib), date_debut_ligne=None,
                                           date_fin_ligne=None, page=pno + 1, section=clean(sec)))
    return delibs_ref, modifs, activites, lignes


def controle_annexe3(txt, lignes):
    """Contrôle croisé : pdftotext compte les lignes 'SECTION NAF ... NC' indépendamment de pdfplumber."""
    a3 = txt[txt.find("ANNEXE III"):]
    attendu = Counter()
    for line in a3.splitlines():
        # code NC dans la colonne CODE NC (après le libellé NAF), suivi de la désignation
        m = re.match(r"^.{20,80}?\s(\d{4} \d{2} \d{2})(?:\s|$)", line)
        if m:
            attendu[norm_nc(m.group(1))] += 1
    obtenu = Counter(l["code_nc"] for l in lignes)
    return sum(attendu.values()), attendu - obtenu, obtenu - attendu


# --------------------------------------------------------------------------- tarif Excel

def tarif_excel(path):
    f = path.name
    ws = openpyxl.load_workbook(path, data_only=False).active
    out, titres = [], 0
    for i, r in enumerate(ws.iter_rows(min_row=5, values_only=True), 5):
        a, b, c, d_, e, g, h, ecart = (list(r) + [None] * 8)[:8]
        if b is None:
            continue
        brut = str(b).replace("\xa0", " ").strip()
        chiffres = re.sub(r"\s+", "", brut)
        if not re.fullmatch(r"\d{6,10}", chiffres):
            titres += 1                                  # SECTION / CHAPITRE
            continue
        if len(chiffres) == 6:
            anomalie(f, "code_nc_6_chiffres", f"ligne {i} : {brut} (position à 6 chiffres, complétée en {chiffres}00)")
            chiffres += "00"
        if "  " in brut:
            anomalie(f, "code_nc_double_espace", f"ligne {i} : {brut!r}")
        nc, complement = chiffres[:8], chiffres[8:]
        if complement:
            anomalie(f, "code_taric_10_chiffres", f"ligne {i} : {brut}")
        rates = []
        for col, v in zip(("ome", "omre", "omi", "omri"), (d_, e, g, h)):
            t = taux(v)
            if t is None:
                anomalie(f, "taux_non_numerique", f"ligne {i} {brut} {col} = {v!r}")
            rates.append(t)
        out.append(dict(source="TARIF_2024", code_nc=nc, complement=complement,
                        ex=1 if a and str(a).strip().upper() == "EX" else 0, libelle=clean(str(c)),
                        ome=rates[0], omre=rates[1], omi=rates[2], omri=rates[3],
                        ecart=(str(ecart).strip() if ecart else None), date_effet="2024-01-01", ligne_excel=i))
    # doublons exacts sur la clé (code, complément, EX)
    cles = Counter((x["code_nc"], x["complement"], x["ex"], x["libelle"]) for x in out)
    vus, dedup = set(), []
    for x in out:
        k = (x["code_nc"], x["complement"], x["ex"], x["libelle"])
        if cles[k] > 1 and k in vus:
            anomalie(f, "doublon_tarif", f"ligne {x['ligne_excel']} : {x['code_nc']} (doublon supprimé)")
            continue
        vus.add(k)
        dedup.append(x)
    return dedup, titres


# --------------------------------------------------------------------------- main

def ecrire(path, rows, cols):
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", default="corpus")
    ap.add_argument("--out", default="data/csv")
    args = ap.parse_args()
    corpus, out = Path(args.corpus), Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    delibs, modifs, activites, lignes, tarifs = [], [], [], [], []
    controle = None
    for pdf in sorted(corpus.glob("*.pdf")):
        print(f"  lecture {pdf.name}…", file=sys.stderr)
        txt = pdf_text(pdf)
        d = entete(pdf, txt)
        d["nature"] = nature(d)
        # date de début : explicite si écrite, sinon date de publication (caractère exécutoire)
        d["date_debut"] = d["date_debut_explicite"] or d["date_publication"]
        d["date_fin"] = d["date_fin_texte"] if d["nature"] != "PROROGATION" else None
        if d["nature"] == "CADRE":
            refs, mods, acts, lgn = traiter_ap(pdf, d, txt)
            delibs += refs
            modifs += mods
            activites += acts
            lignes += lgn
            controle = controle_annexe3(txt, lgn)
        elif d["nature"] == "MODIFICATION_TARIF":
            tarifs += tarif_cp(pdf, d)
        else:
            lignes += lignes_cp(pdf, d, txt)
            modifs += prorogations(d)
        delibs.append(d)

    for x in corpus.glob("*.xlsx"):
        t, titres = tarif_excel(x)
        tarifs = t + tarifs

    # activités citées dans les CP sectorielles (NAF 2008 et NAF 2025)
    connues = {a["code_naf"] for a in activites}
    for l in lignes:
        if l.get("code_naf") and l["code_naf"] not in connues:
            activites.append(dict(code_naf=l["code_naf"], section=None, libelle=l.get("libelle_naf"),
                                  nomenclature=l["nomenclature"], ordre=None, numero=None))
            connues.add(l["code_naf"])

    # correspondances NAF 2008 -> NAF 2025 lues dans les CP à double colonne
    corresp = {}
    par_ligne = defaultdict(dict)
    for l in lignes:
        if l.get("nomenclature") and (l["date_debut_ligne"] or l["date_fin_ligne"]):
            par_ligne[(l["numero"], l["code_nc"])][l["nomenclature"]] = l["code_naf"]
    for (num, _), v in par_ligne.items():
        if "NAF2008" in v and "NAF2025" in v:
            corresp[(v["NAF2008"], v["NAF2025"])] = num
    corresp_rows = [dict(naf_2008=a, naf_2025=b, source=s) for (a, b), s in sorted(corresp.items())]

    # contrôles
    nc_tarif = {t["code_nc"] for t in tarifs}
    for l in lignes:
        if l["code_nc"] not in nc_tarif:
            anomalie(l["numero"], "nc_absent_du_tarif_2024", f"{l['code_nc']} ({l.get('code_naf') or l.get('categorie')})")
    dup = Counter((l["numero"], l["code_nc"], l.get("code_naf"), l.get("categorie")) for l in lignes)
    for k, n in dup.items():
        if n > 1:
            anomalie(k[0], "doublon_ligne_exoneration", f"{k} x{n}")
    agrees = {a["code_naf"] for a in activites if a["numero"]}
    for l in lignes:
        if l["numero"] != "AP/25-15" and l.get("nomenclature") == "NAF2008" and l["code_naf"] not in agrees:
            anomalie(l["numero"], "naf_hors_annexe2", l["code_naf"])
    for m in modifs:
        if m["cible"] not in {d["numero"] for d in delibs}:
            anomalie(m["source"], "cible_inconnue", m["cible"])

    # dédoublonnage des lignes (clé métier)
    vus, lignes_u = set(), []
    for l in lignes:
        k = (l["numero"], l["code_nc"], l.get("code_naf"), l.get("categorie"), l["date_debut_ligne"], l["date_fin_ligne"])
        if k not in vus:
            vus.add(k)
            lignes_u.append(l)

    ecrire(out / "deliberations.csv", delibs, ["numero", "organe", "nature", "objet", "date_seance",
           "date_publication", "date_avis_commission", "date_debut", "date_fin", "taux_applique", "fichier"])
    ecrire(out / "modifications.csv", modifs, ["source", "cible", "type", "date_effet", "nouvelle_date_fin"])
    ecrire(out / "activites.csv", activites, ["code_naf", "nomenclature", "section", "libelle", "ordre", "numero"])
    ecrire(out / "lignes_exoneration.csv", lignes_u, ["numero", "code_nc", "designation", "code_naf",
           "nomenclature", "categorie", "date_debut_ligne", "date_fin_ligne", "page"])
    ecrire(out / "tarif.csv", tarifs, ["source", "code_nc", "complement", "ex", "libelle", "ome", "omre",
           "omi", "omri", "ecart", "date_effet"])
    ecrire(out / "correspondance_naf.csv", corresp_rows, ["naf_2008", "naf_2025", "source"])
    ecrire(out / "anomalies.csv", [dict(fichier=a, type=b, detail=c) for a, b, c in anomalies],
           ["fichier", "type", "detail"])

    # rapport
    r = ["# Rapport d'extraction", "", f"Généré le {dt.datetime.now():%d/%m/%Y %H:%M}", "", "## Comptages", "",
         "| Fichier CSV | Lignes |", "|---|---:|"]
    for name, rows in [("deliberations.csv", delibs), ("modifications.csv", modifs), ("activites.csv", activites),
                       ("lignes_exoneration.csv", lignes_u), ("tarif.csv", tarifs),
                       ("correspondance_naf.csv", corresp_rows), ("anomalies.csv", anomalies)]:
        r.append(f"| {name} | {len(rows)} |")
    r += ["", "### Lignes d'exonération par délibération", "", "| Délibération | Lignes |", "|---|---:|"]
    for k, v in sorted(Counter(l["numero"] for l in lignes_u).items()):
        r.append(f"| {k} | {v} |")
    r += ["", "### Tarif", "",
          f"- lignes de titre ignorées (SECTION/CHAPITRE) : {titres}",
          f"- lignes tarif 2024 : {sum(1 for t in tarifs if t['source']=='TARIF_2024')} "
          f"(dont EX : {sum(1 for t in tarifs if t['source']=='TARIF_2024' and t['ex'])}, "
          f"codes NC distincts : {len({t['code_nc'] for t in tarifs if t['source']=='TARIF_2024'})})",
          f"- lignes modifiées par CP : {sum(1 for t in tarifs if t['source']!='TARIF_2024')}", ""]
    if controle:
        total, manquants, en_trop = controle
        r += ["### Contrôle croisé annexe III (pdftotext vs pdfplumber)", "",
              f"- codes NC repérés par pdftotext dans la colonne CODE NC : {total}",
              f"- lignes extraites par pdfplumber (avant dédoublonnage) : {sum(1 for l in lignes if l['numero']=='AP/25-15')}",
              f"- écarts : {sum(manquants.values())} manquant(s), {sum(en_trop.values())} en trop", ""]
        for nc, n in list(manquants.items())[:20]:
            r.append(f"  - manquant : {nc} x{n}")
        for nc, n in list(en_trop.items())[:20]:
            r.append(f"  - en trop : {nc} x{n}")
        r.append("")
    r += ["## Anomalies par type", "", "| Type | Nombre | Exemple |", "|---|---:|---|"]
    par_type = defaultdict(list)
    for a in anomalies:
        par_type[a[1]].append(a)
    for t, lst in sorted(par_type.items(), key=lambda x: -len(x[1])):
        r.append(f"| {t} | {len(lst)} | {lst[0][0]} — {lst[0][2][:90]} |")
    Path(out.parent / "rapport_extraction.md").write_text("\n".join(r) + "\n", encoding="utf-8")
    print("\n".join(r[:40]), file=sys.stderr)


if __name__ == "__main__":
    main()
