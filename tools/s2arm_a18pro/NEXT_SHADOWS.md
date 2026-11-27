# Ombres NVN2 sur A18 Pro

[Cartographie, contre-expertise et protocole](../../docs/evidence/s2arm-shadows/README.md)

- Le diagnostic de l’IPA 824 attribue 382 Mio logiques aux quatre niveaux du grand atlas. Les compteurs GPU de cette capture donnent quelques dizaines de microsecondes par passe. Mesurer d’abord les copies réellement déclenchées et la durée des passes de profondeur.
- 0518 corrige les tailles logiques des plans D16 et D32S8, détaille les snapshots avec `S2A_RB_SHADOW_TRACE=1` et distingue les passes depth-only du profil GPU.
- 0519 teste `S2A_RB_SHADOW_MIP_CACHE=1`. Seuls les clears Metal natifs dont le niveau et les couches sont validés peuvent garder un snapshot du même objet pour un sous-ensemble disjoint. À 0, les invalidations historiques s’appliquent.
- 0520 étend la protection des lectures en cours de passe aux dessins qui utilisent une cible de profondeur sans cible couleur. Le témoin `S2A_RB_SHADOW_DEPTH_FEEDBACK=0` permet d’isoler la correction.
- Lancer le Banc d’essai à 1× avec la génération d’images désactivée et conserver `S2A_RB_SHADOW_SCALE=1`. Le profil GPU est une capture à part. Les comparaisons longues gardent la trace désactivée et la même résolution.
