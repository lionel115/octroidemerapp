-- « Pour l'activité X, le bien Y importé à la date D est-il exonéré, par quelle délibération et à quel taux ? »
-- Exemple : cas 1 du sujet (NAF 23.61Z, excavateur 8429 52 10, import le 03/11/2026)
-- Lancer :  python -c "import sqlite3;c=sqlite3.connect('data/octroi.db');print(c.execute(open('db/requete_unique.sql').read()).fetchall())"

SELECT l.numero, l.taux_applique, t.ome AS taux_ome_tarif,
       v.date_fin_effective, v.prorogee_par
FROM exoneration l
JOIN beneficiaire b           ON b.id = l.beneficiaire_id
JOIN v_deliberation_vigueur v ON v.numero = l.numero
LEFT JOIN taux t       ON t.code_nc = l.code_nc AND t.source = 'TARIF_2024' AND t.ex = 0 AND t.complement = ''
WHERE l.code_nc = '84295210'
  AND (b.code_naf IN (SELECT equivalent FROM v_naf_equivalent WHERE code = '23.61Z') OR b.categorie = NULL)
  AND '2026-11-03' >= v.date_debut
  AND (v.date_fin_effective IS NULL OR '2026-11-03' <= v.date_fin_effective)
  AND (v.date_abrogation   IS NULL OR '2026-11-03' <  v.date_abrogation)
  AND (l.date_debut_ligne  IS NULL OR '2026-11-03' >= l.date_debut_ligne)
  AND (l.date_fin_ligne    IS NULL OR '2026-11-03' <= l.date_fin_ligne);
