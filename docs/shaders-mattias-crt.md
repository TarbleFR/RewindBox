# Mattias CRT pour Dolphin — étude technique et droits (Build 450)

Demande du mainteneur : étudier le portage Dolphin du shader CRT de Mattias,
préparer un adaptateur compatible, et « vérifier les droits auprès de sources
faisant autorité avant de redistribuer ou d'intégrer les shaders à une version
publique de NeoStation. Conserver l'attribution à Mattias Gustavsson et les
crédits du port. Si l'autorisation de redistribution ne peut pas être établie,
ne pas empaqueter ni distribuer automatiquement les fichiers. […] Ne pas
assimiler un dépôt GitHub public à une autorisation générale de
redistribution. »

## 1. Sources examinées

| Élément | Identité | Constat |
|---|---|---|
| Shader d'origine | « CRT Emulation » par Mattias, Shadertoy `lsB3DV` | En-tête : `// CRT Emulation // by Mattias // https://www.shadertoy.com/view/lsB3DV`. Aucune licence dans le fichier. |
| Version libretro GLSL | `libretro/glsl-shaders` `crt/shaders/crt-mattias.glsl` @ `435612fe4f1023117b3aae48c88603fb413404a3`, SHA-256 `b6de4b3a…7c083` (selon le NOTICE du portage) | Même en-tête, aucune licence. L'auteur est identifié comme Mattias Gustavsson dans `libretro/slang-shaders` issue #134. |
| Version libretro slang | `libretro/slang-shaders` `crt/crt-mattias.slangp` @ `e1d75632` | Au catalogue NeoStation (rendu vérifié en CI), avec les remarques « origine Shadertoy » et « aucune licence indiquée ». Téléchargée seulement à la demande depuis ce dépôt ; jamais empaquetée. |
| Portage Dolphin | `pakovm-git/Mattias-CRT-Dolphin` @ `a7b5603e5954563df9d111049c9645db7a0d860c` (9 octobre 2026), versions publiées `26.10.09` | 6 fichiers : Original, Soft, Strong et leurs éditions « Performance ». Son `NOTICE.md` conserve l'attribution et écrit lui-même : « No license grant for the underlying work is created by this repository. Confirm the applicable terms with authoritative source material or the relevant rights holders before treating this as a freely redistributable or sublicensable package. » |

## 2. Analyse technique

- Format : shader de post-traitement Dolphin (`void main()`, `Sample*`,
  `SetOutput`, `GetWindowResolution`, `GetTime`, `src_rect`), bloc
  `[configuration]` avec trois réglages identiques dans les six fichiers :
  `M_CURVATURE` (0–1, 0,5, pas 0,05), `M_SCAN_SPEED` (0–10, 1, pas 0,5),
  `M_EXPOSURE` (−2 à +2, 0, pas 0,1).
- Traduction par la reproduction NeoStation du pipeline Metal du cœur Dolphin
  embarqué (en-tête et bloc d'uniformes de Dolphin, GLSL → SPIR-V → MSL de la
  révision DolphiniOS `7cac5416`) : les six fichiers se traduisent
  (vérifié ici, Linux) ; tampon d'uniformes de 188 octets (140 octets
  intégrés + 3 emplacements de 16 octets).
- Coût : 225 lectures de texture par pixel pour les éditions complètes, 81
  pour les éditions « Performance » (comptage statique sur le SPIR-V, sans
  boucle) ; dessin à la taille de l'écran.
- Validation CI (`test/neo_shader_kit_dolphin_test.py`, workflow
  `shader-kit-checks`) : le portage est récupéré à son commit épinglé pendant la
  CI uniquement, traduit pour iOS, compilé par le compilateur Metal de
  l'iPhone et dessiné par une reproduction de l'interface de post-traitement
  de Dolphin, comparé au rendu sans effet. Résultats : § 5.

## 3. Adaptateur compatible : l'import Dolphin de NeoStation

Aucune modification des fichiers n'est nécessaire : ils sont écrits pour
l'interface de Dolphin que le cœur embarqué fournit. L'adaptateur est donc le
chemin d'import livré en Build 450 :

1. le joueur télécharge lui-même la version publiée du portage et extrait le
   ZIP dans Fichiers (iOS sait le faire) ;
2. Menu en jeu Dolphin › Graphismes › Affichage › **Effet de
   post-traitement** › « Importer des shaders Dolphin (.glsl)… », sélection
   multiple possible ;
3. chaque fichier est traduit comme le fait le cœur puis compilé par le
   compilateur Metal de l'appareil ; s'il échoue, il est refusé avec le code
   technique ; sinon il est copié dans `User/Shaders` de Dolphin (jamais
   ailleurs) ;
4. l'effet se choisit pour tous les jeux ou pour ce jeu, ses trois réglages
   s'ajustent avec des curseurs, et il s'applique au lancement suivant ;
5. la page cite les lignes de crédit du fichier telles qu'elles sont écrites
   (« by Mattias », adresse Shadertoy) ; la suppression d'un import le retire
   de `User/Shaders` et remet « aucun effet » là où il était choisi.

## 4. Droits : ce qui empêche la distribution

- Le fichier d'origine ne comporte aucune licence ; aucune source faisant
  autorité consultée ne donne d'autorisation de redistribution pour ce shader
  précis.
- Shadertoy affiche par défaut une licence Creative Commons BY-NC-SA 3.0
  pour les shaders sans mention contraire ; la page `lsB3DV` n'a pas pu être
  consultée pendant ce chantier et ce point reste à confirmer auprès de la
  source. Si elle s'applique, ses clauses « pas d'utilisation commerciale » et
  « partage dans les mêmes conditions » ne sont pas compatibles avec la
  distribution de NeoStation sous GPL-3.0, et une distribution exigerait
  l'accord des titulaires.
- Les implémentations CRT plus récentes de Mattias Gustavsson sont publiées
  sous d'autres conditions ; elles ne s'appliquent pas automatiquement à ce
  shader plus ancien ni aux modifications de libretro ou du portage.
- Le portage Dolphin déclare explicitement ne créer aucune licence.

Conséquence appliquée : les fichiers Mattias ne sont **ni ajoutés au dépôt, ni
empaquetés dans l'IPA, ni téléchargés automatiquement** ; la CI les récupère
seulement pour les vérifier. Pour les intégrer, il faudrait une autorisation
écrite de Mattias Gustavsson pour le shader d'origine et de l'auteur du
portage (pakovm-git) pour l'adaptation, ou une licence publiée par eux
compatible avec la distribution de NeoStation ; l'attribution à Mattias
Gustavsson et les crédits du portage seraient alors conservés dans les
fichiers et dans les mentions légales.

## 5. Résultats CI du portage

Run `shader-kit-checks` 38334940237, job `metal` 115092786948, source
`71b8815e4a3808db9cd258165bd29a01822e9e80`, macOS 15 (GPU « Apple
Paravirtual device »), compilateur Metal de l'iPhone de Xcode 26.3 ; portage
récupéré au commit `a7b5603e5954563df9d111049c9645db7a0d860c` pendant la CI
seulement.

| Fichier | Résultat | Pixels changés | Temps GPU (1186 × 890) |
|---|---|---|---|
| `full-quality/crt-mattias-original.glsl` | rendu | 99,99 % | 14,43 ms |
| `full-quality/crt-mattias-soft.glsl` | rendu | 99,98 % | 14,38 ms |
| `full-quality/crt-mattias-strong.glsl` | rendu | 99,99 % | 14,49 ms |
| `performance/crt-mattias-performance.glsl` | rendu | 99,98 % | 2,71 ms |
| `performance/crt-mattias-performance-soft.glsl` | rendu | 99,94 % | 2,62 ms |
| `performance/crt-mattias-performance-strong.glsl` | rendu | 99,99 % | 2,91 ms |

« Rendu » veut dire : traduit comme le fait le cœur, compilé par le
compilateur Metal de l'iPhone, dessiné par la reproduction de l'interface de
post-traitement de Dolphin et visiblement différent du rendu sans effet.
Les six fichiers sont donc techniquement compatibles avec le chemin d'import
du § 3. Ce n'est pas une mesure sur iPhone : le GPU de la CI est celui d'un
Mac virtualisé. Hypothèse non vérifiée : à 60 images/s le budget d'une image
est de 16,7 ms et les éditions complètes en consomment près de 14,5 ms sur ce
GPU ; les éditions « Performance » (environ cinq fois moins coûteuses) sont
celles à essayer d'abord sur iPhone.

Ces résultats ne changent rien au § 4 : la compatibilité technique n'est pas
une autorisation de redistribution.
