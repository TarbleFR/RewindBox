# Vérification indépendante de l'IPA595

`verify_ipa595_offline.py` est lié au commit de livraison
`d2e5029f8d7ca33eec279546d64a7f908285e804`, run `40928805790`,
job `123641427943`. Il exige la réussite du run et utilise les véritables
validateurs signés de ce commit, sans modification de leurs fonctions.

Le programme vérifie l'archive chiffrée, le fichier IPA déchiffré, les archives
originales des deux cores, leurs identités et les preuves conservées. Il vérifie
également les 88 fichiers Mach-O : 85 images ARM64 simples avec comparaison
exacte des empreintes de préservation et trois conteneurs universels mono-ARM64
avec identité après signature et structure strictement vérifiées. Ces trois
conteneurs n'ont pas de preuve d'empreinte avant/après signature dans le reçu CI.
Les huit versions de bundles et l'inventaire des 88 signatures contrôlées par le
runner Apple sont également vérifiés. La cryptographie des signatures
n'est pas réexécutée sur Linux ; cette limite est explicite dans le résultat.

Il ne lit aucune clé privée, ne lance aucun compilateur, test natif ou binaire
ARM64 et n'accède pas au réseau. Les réponses API originales des builds de cores
sont authentifiées avant leur utilisation. Le checkout reste intact ; les
validateurs sont exécutés depuis un miroir temporaire de sources vérifiées.

Exemple, après déchiffrement authentifié de la livraison :

```bash
python3 verify_ipa595_offline.py \
  --repo /chemin/RewindBox \
  --ipa /chemin/RewindBox-Build595.ipa \
  --artifact-root /chemin/livraison-dechiffree \
  --core-zip /chemin/RPCS3Core-f42573af.zip \
  --core-diagnostics-zip /chemin/RPCS3Core-f42573af-diagnostics.zip \
  --melonx-zip /chemin/MeloNX-Core85.zip \
  --melonx-metadata-dir /chemin/metadata-core85 \
  --delivery-metadata-dir /chemin/metadata-ipa595 \
  --delivery-archive /chemin/IPA595-artefact-chiffre.zip \
  --output /chemin/independent-ipa-verification.json
```

Les répertoires de métadonnées contiennent les réponses complètes `run.json`,
`job.json` et `artifact.json`. `--artifact-root` contient les JSON et
`SHA256SUMS` réellement extraits de l'enveloppe, et non des preuves recréées.

La première tentative `40926266201` reste un échec historique : l'application
avait compilé, mais une référence Dolphin altérée dans la recette a été refusée
par le contrôle de notices. Elle n'a produit aucune IPA livrable. Le nouveau
vérificateur ne la présente pas comme une livraison réussie.

## Résultat exécuté

La vérification du fichier téléchargé réussit : voir
`offline-ipa595-verification.json`. Les 522 fichiers de sources authentifiés,
les validateurs signés inchangés et les archives originales sont liés au
résultat. Aucun test natif ni build supplémentaire n'est exécuté.

Le premier script supposait à tort que les 85 empreintes de préservation
représentaient tous les fichiers Mach-O. Son échec reste conservé avec le script
initial, le diff exact et `offline-verifier-correction.json`. La correction
inventorie les trois conteneurs mono-ARM64 supplémentaires sans modifier l'IPA
ou les deux validateurs signés. Les contrôles cryptographiques de signature
restent ceux du runner Apple.
