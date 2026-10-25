# Build500 — RPCS3 et catalogue PS1 actuel

Cette livraison rassemble le Core RPCS3 de la499 validée et le catalogue PS1 actuel, sans modifier le code produit.

- Core : source `0b18a23460b0a9840406fda2e3d6da4c5cdb7273`, run `39472233521`, ABI30 ; binaire original SHA-256 `87bd77794232fc44b61d421e55d71bae3b2829a58b87ee36b2a176730d78004f`.
- Catalogue : `2026-10-20.56904c72933f`, SHA-256 `cd05e0ebd8c1783768f7dbc94f94abe9adce61b376ecc058961ca2e39a2c48a7` ;37 références PS1,8 téléchargements vérifiés,29 pages manuelles. Catalogue global424 familles installables,509 profils.
- Preuves réutilisées par identité : publication39484361864 (187 contrôles Foundation), porte39484758626, Core et produit natif déjà livrés en499. Les tests Flutter inchangés ne sont pas rejoués.
- La recette500 est séparée ; la499 reste figée. Seuls les deux indices PS1 peuvent différer dans les entrées produit. La construction et le contrôle de l’IPA finale sont requis ; aucun nouveau Core n’est compilé.
- Aucun rendu iPhone physique ni gain FPS supplémentaire n’est attesté. Aucune release publique.

Le reçu final contiendra source figée, exécutionCI, empreinte de l’IPA, identités Core et catalogue.

## Livraison vérifiée

Source figée `76cb22f155188908345796ae504958e26eba1427`, workflow `c5ac1161b8b44e1607b8692ffee0152a60fbbd53`, [exécution39487947573 réussie](https://github.com/TarbleFR/neostation-ios/actions/runs/39487947573).

IPA **0.0.8 (500)**, **168389597 octets**, SHA-256 `0c91d716c51c60391219cc1ce54e30fe7ab980faf39e8ea53f7f82c451b9d625`. Six bundles portent500. Le Core signé SHA-256 `49033f06bcbe5bfb635a956783f87e35934f21d9be5fd3d84b4d902adb190a63` est identique à celui de499 ; les37 références PS1 et les8 plans téléchargeables sont dans le manifeste embarqué exact. Aucun nouveau Core ni test Flutter inchangé exécuté. Les29 pages manuelles ne gagnent aucun plan d’installation.

Reçu : `docs/evidence/ps1rpcs3500-delivery.json`. La500 est figée ; ne pas réutiliser ce numéro pour une autre source. Signature Apple via SideStore/AltStore requise. Aucun test physique ni nouveau gain FPS attesté.
