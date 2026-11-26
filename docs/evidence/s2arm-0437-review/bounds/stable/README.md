# Bornes effectives des buffers uniformes

Le chemin de dessin fournit un tableau de plafonds non nul. La longueur peut changer avec une copie réécrite ou un changement d’arène, même à adresse invitée constante. Certaines restaurations de tout l’état de dessin recopient les liaisons sans passer par les compteurs individuels. Chaque vérification conserve donc les bornes effectives et la génération.

Le candidat calcule les quatorze mots et les compare au fil de l’eau aux bornes déjà publiées. Le coût CPU apparié du hit stable, plafonds présents, augmente de 13,53 % dans une disposition du binaire Linux et de 10,82 % dans la seconde. Le témoin A/A varie de 7,16 %. Ce candidat a été écarté. [Médianes et intervalles](summary.txt).

Le contrôle renforcé distingue hits et misses. Une permutation des deux compteurs est bien détectée. Il inclut le cas où une nouvelle allocation est faite dans un autre bloc de la même génération. Sur 2 048 appels, 1 557 hits ramènent une adresse du bloc précédent toujours valide. La référence et le candidat ont les mêmes octets, adresses et compteurs sur les scénarios testés. [Contrôle des compteurs](counter-proof.txt) et [changement de bloc](same-generation.txt).

Sous Linux, depuis ce dossier, exécuter les commandes suivantes en précisant l’arbre du moteur 0449, le dossier parent et un dossier de travail libre.

```sh
python3 prepare.py "$ENGINE" .. "$OUT"
python3 "$OUT/compare_ubolen.py" "$ENGINE" "$OUT/candidate" "$OUT/results"
python3 "$OUT/report.py" "$OUT/results/forward.tsv" "$OUT/results/reverse.tsv" "$OUT/results/control.tsv"
python3 counter_check.py "$ENGINE" .. "$OUT"
python3 same_generation.py "$ENGINE" .. "$OUT"
```
