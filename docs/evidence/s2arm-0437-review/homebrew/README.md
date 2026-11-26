# Fragment deko_basic et microprogrammes de S2Arm

Le shader de couleur de switchbrew a traversé le traducteur Maxwell de S2Arm sur Linux x86-64. devkitPro/uam 1.1.0 compile le GLSL en DKSH. Le banc lit le point d’entrée du programme dans le conteneur et vérifie que les instructions qui suivent son en-tête de 80 octets correspondent exactement à la sortie Maxwell brute de la même compilation. Le Runner du moteur lit cette entrée et émet le SPIR-V. Le banc valide ce module pour Vulkan 1.1 puis appelle la fonction de production `graphics/tools/spirv_msl.py::translate` avec SPIRV-Cross `vulkan-sdk-1.4.363.0` recompilé depuis les sources du moteur.

Mesa lavapipe a exécuté le SPIR-V sur CPU. Le lanceur d’origine vérifie le type de périphérique et le nom llvmpipe puis lit le pixel central du triangle plein écran. Un second exécutable utilise les mêmes shaders, pipeline, dessin et copie mémoire et enregistre toute la surface de 64 × 64. Le contrôle compare les octets du rendu à la couleur attendue et à la sortie obtenue indépendamment en compilant le GLSL d’origine avec glslc.

| Cas | Valeur attendue et obtenue |
| --- | --- |
| switchbrew/deko_basic | Les 4 096 pixels valent RGBA8 (64, 128, 191, 255). La référence GLSL et le SPIR-V de S2Arm ont la même image, SHA-256 `6a5fc0c57393484d59032f3e9b9c6ef109bc72d02450c1baf2d1f615b10a5f81`. |
| S2Arm attribute/reverse | Les 4 096 pixels valent RGBA8 (255, 191, 128, 64). |
| S2Arm memory/copy17 | Les 64 mots correspondent à l’oracle du projet, dont les valeurs de sortie 17 et 42 aux indices 1 et 2. |

Deux compilations indépendantes du shader par uam ont produit un octet différent dans le bytecode brut à l’index 37. Les deux SPIR-V, les deux MSL et les images lues sont identiques. Les deux compilations figurent dans `two-compiles.json`. Cinq replays sur des octets Maxwell figés retrouvent les mêmes 25 fichiers de sortie, dont les images de 16 384 octets. Chaque passage laisse ses empreintes dans `five.json`. Le SHA-256 du SPIR-V de deko_basic est `3a9009006b053bafdc5a4f75ea74aac1f314ddb1c010cc6743b4a1768f0aa380` et celui du texte MSL est `abbab49dd264eda31376e6258461b22c2c0e058ba1150abe7930920fa90d64bf`.

Le test couvre un fragment de démonstration de première génération et deux microprogrammes Maxwell synthétiques. Il mesure la conformité de ces sorties. La phase Metal s’arrête à l’émission MSL sur Linux. FPS, GPU Apple, énergie, frametime et exécution du programme complet deko_basic sur iPhone restent hors de la mesure.

## Sources et licences

- Le projet switchbrew marque ses exemples comme domaine public. [Shader exact](https://github.com/switchbrew/switch-examples/blob/669786898205b7beb25ff1731e72982e6d0397d3/graphics/deko3d/deko_basic/source/color_fsh.glsl) et [déclaration du projet](https://github.com/switchbrew/switch-examples/blob/669786898205b7beb25ff1731e72982e6d0397d3/README.md).
- devkitPro/uam, commit 5a5afc2bae8b55409ab36ba45be63fcb73f68993, zlib pour le projet et MIT pour mesa-imported. Le code C++ du compilateur et le GLSL ont été utilisés tels que publiés. [Compilateur et licence](https://github.com/devkitPro/uam/blob/5a5afc2bae8b55409ab36ba45be63fcb73f68993/LICENSE).
- Cas originaux de S2Arm sous Apache-2.0, traducteur dérivé de Ryujinx sous MIT, SPIRV-Cross sous Apache-2.0 ou MIT. Le test part de l’arbre moteur matérialisé jusqu’au correctif 0436, basé sur 6b6a571553f7a687af46e03e2cdbf8ef4d77f335. Les empreintes des sources figurent dans `inputs.sha256`. [Microprogrammes](https://github.com/jhaizhou-ops/S2Arm/tree/6b6a571553f7a687af46e03e2cdbf8ef4d77f335/tests/shader_cases) et [licence du projet](https://github.com/jhaizhou-ops/S2Arm/blob/6b6a571553f7a687af46e03e2cdbf8ef4d77f335/LICENSE).

## Reproduction Linux

Les programmes nécessaires sont le SDK .NET 10.0.403, un compilateur C/C++, Python 3, les outils Vulkan `glslc` et `spirv-val`, les headers et le chargeur Vulkan et le pilote Mesa lavapipe. Cette exécution a utilisé Mesa 25.2.8 sur x86-64. Les commandes supposent un shell Bash sous Linux, les outils `realpath` et `cmp`, et les exécutables du SDK et des outils de validation dans le PATH. Les paquets Ubuntu 24.04 utilisés pour les outils du banc sont `glslc`, `libshaderc1`, `spirv-tools`, `libvulkan-dev`, `libvulkan1` et `mesa-vulkan-drivers`. La recette crée exclusivement un nouveau répertoire de sortie. Elle utilise le contenu de l’arbre moteur fourni et construit les outils localement. `VULKAN_HEADERS` indique un répertoire d’include non standard. `VK_DRIVER_FILES` peut désigner le fichier ICD de lavapipe.

Récupérer le compilateur depuis le commit exact cité ci-dessus. L’archive officielle `https://codeload.github.com/devkitPro/uam/tar.gz/5a5afc2bae8b55409ab36ba45be63fcb73f68993` a le SHA-256 `179a9485689d7fa4e1e0e6adc5bc2de279572588e88b5394370458c026348a50`. Le shader GLSL original et le README de sa distribution accompagnent la recette. Compiler uam avec meson et ninja. Les dépendances de compilation de uam sont Python avec Mako et setuptools, flex et bison. Avec le commit indiqué, les chemins de diagnostic de sa compilation debug activent des includes absents du tarball. La configuration suivante correspond au binaire utilisé.

```sh
meson setup uam-build source-uam --buildtype=debug -Db_ndebug=true
ninja -C uam-build
bash reproduce.sh /chemin/arbre-moteur sortie-neuve "$(realpath uam-build/uam)" /chemin/color_fsh.glsl
```

La recette compile le shader homebrew une seule fois et fige le DKSH et le code Maxwell brut pour les cinq passages. Un premier lancement remplit un cache Mesa propre à la série. Chacun des cinq passages suivants lance le traducteur, les validations SPIR-V, les compilations GLSL de référence, les exécutions Vulkan et la génération du MSL dans de nouveaux processus. Le chronomètre monotone englobe ces étapes ainsi que les E/S. La durée exclut la construction de uam et du traducteur. Les cinq durées murales sur la même entrée enregistrée sont 0,892 s, 0,790 s, 0,791 s, 1,055 s, 0,795 s. La médiane est 0,795 s sur ce Linux x86-64 (Xeon Platinum 8370C, deux processeurs logiques disponibles). Ce temps sert à dimensionner la validation hôte. Les empreintes des 25 fichiers par passage figurent dans `five.json`, les valeurs lues dans `reference-output.json`.

Pour répéter l’essai sur les octets de référence conservés, le fichier `reference-guest.json` contient uniquement la sortie du compilateur pour le fragment de switchbrew. `repeat.py` contrôle ses deux empreintes avant de s’en servir. Cette commande s’exécute après la recette ci-dessus dans le même environnement avec le `spirv-cross` recompilé depuis les sources.

```sh
export PATH="$(realpath sortie-neuve/bin):$PATH"
export VK_DRIVER_FILES=/usr/share/vulkan/icd.d/lvp_icd.json
python3 repeat.py /chemin/arbre-moteur sortie-neuve reference-guest.json color_fsh.glsl nouvel-essai-fige
```

Les entrées d’empreintes agrégées dans `inputs.sha256` aux lignes marquées `-` couvrent, dans l’ordre, les sources et en-têtes de SPIRV-Cross inclus dans le moteur, puis les fichiers C# de Ryujinx.Graphics.Shader et Spv.Generator. Les autres entrées sont des empreintes individuelles. La préparation de l’arbre moteur suit le manifeste de RewindBox.

## Lecture retour Metal

`python3 metal_readback.py` vérifie les SHA-256 des trois fichiers MSL produits par la traduction puis les compile avec le SDK iPhoneOS sur Mac. Pour chaque programme, le périphérique Metal du runner exécute six soumissions et compare entièrement le buffer ou la texture RGBA8 à l’oracle Vulkan. Sous Linux le même script vérifie les empreintes des shaders et les sorties de référence avant de renvoyer 77. Le banc d’émulation complet de la console et la présentation à l’écran ne sont pas exercés par cette épreuve.
