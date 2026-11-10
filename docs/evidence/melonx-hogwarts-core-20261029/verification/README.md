# Reproduire la vérification hors ligne du Core84

`verify_core84.py` est le vérificateur exact utilisé pour le reçu
`../independent-apple-verification.json`. Son SHA-256 est
`78a39a1999c601bd4a7f3aeee0a48ed852db5406c57570b1d8b0922c74d6413f`.
Le parseur adjacent `verify_ipa.py` est une copie exacte du blob Git
`6032458096236bcf75fc007d208d4ba177dd3216` ; seules ses définitions de parsing
Mach-O sont chargées. Aucune IPA n'est créée ou exécutée.

Depuis la racine d'un clone qui contient les objets du commit
`5045889ff9f1a872d238435293c50cacd7c127b5`, fournir les deux archives :

```bash
python3 docs/evidence/melonx-hogwarts-core-20261029/verification/verify_core84.py \
  --repo . \
  --baseline-zip /chemin/vers/melonx-engine82-verified.zip \
  --zip /chemin/vers/RewindBox-MeloNX-Core84-5045889f.zip \
  --run-metadata docs/evidence/melonx-hogwarts-core-20261029/verification/run.json \
  --job-metadata docs/evidence/melonx-hogwarts-core-20261029/verification/job.json \
  --artifact-metadata docs/evidence/melonx-hogwarts-core-20261029/verification/artifact.json \
  --artifact-id 12907831125 \
  --output /tmp/core84-independent-verification.json
```

Les métadonnées sont les réponses GitHub conservées après le succès du run.
Le vérificateur les contrôle sans accès réseau. Dans un clone partiel, un blob
manquant peut être fourni avec `--source-file CHEMIN_GIT=FICHIER_LOCAL` ; son
identité Git reste obligatoirement vérifiée. Le script refuse le lazy-fetch.

Le contrôle lit les archives, les objets Git et les preuves enregistrées. Il
ne rejoue pas les tests, ne compile rien et ne charge aucun code natif. Les
frameworks externes ne figurent pas dans l'archive du Core : leurs preuves
historiques et leur réauthentification CI sont contrôlées, sans prétendre
relire leurs octets localement. Le résultat reste limité au cœur compilé et
aux deux sessions de homebrew sans vidéo sur simulateur.
