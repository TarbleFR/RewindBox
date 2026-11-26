# Reconnaissance des matrices du moteur grand écran

La source témoin WidenRewriter.cs a pour SHA-256 `8e3cc210862e3dcc270f87a53b4ba362bcc91c1fafce2487ca72e5ddc7c7f7f4`. Les variantes testent le passage direct d’une matrice déjà dans le bon sens, l’arrêt dès qu’une projection prioritaire est reconnue, et la reconnaissance d’une matrice orthographique symétrique sans créer sa transposée. Les entrées incluent les deux orientations de stockage, les perspectives, les matrices orthographiques, des valeurs invalides et des constantes proches des limites.

Chaque variante et la référence produisent la même empreinte `8551e2601e38bc9e` sur les 8 192 matrices de vérification. Elle couvre les deux sorties de Match, les décisions et octets de RewriteWindow et Rewrite ainsi que le nombre et la version des caméras. Chaque lot chronométré porte sur 131 072 appels de RewriteWindow après échauffement.

Avec .NET 10 JIT sur Linux x86-64 et 16 séries appariées, la médiane du lot de projections en lignes est de 51,56 ms sur la référence et de 34,19 ms avec les trois modifications. Pour les entrées mixtes elle est de 68,69 et 60,07 ms. Les entrées rejetées très tôt donnent des mesures plus dispersées. Ces bancs ne mesurent ni le FPS ni la proportion de matrices rencontrée en jeu. La confirmation utilise la compilation native et une seconde copie intacte du témoin avant toute intégration.

`python3 replay.py ARBRE résultats.csv --cpu 1` reproduit la comparaison JIT sous Linux. `python3 replay.py ARBRE résultats-natifs.csv --variants control all --aot osx-arm64` compile et compare les exécutables natifs sur Mac avec .NET 10.
