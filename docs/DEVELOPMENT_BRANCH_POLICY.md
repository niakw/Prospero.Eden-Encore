# Eden Encore — branche de développement unique

**Branche unique et branche GitHub par défaut :** `dev/ps5-sparse-jit`.

Tous les prochains changements (performances PS5, rendu Vulkan, corrections de sécurité, documentation et tests) s'effectuent directement sur cette branche, avec vérification de son SHA avant chaque écriture. **Ne pas créer de branches temporaires** `work/*`, `security/*`, `fix/*` ou `feature/*`.

## Nettoyage validé le 13 octobre 2026

- Les correctifs R419 à R427 avaient déjà été consolidés sur `dev/ps5-sparse-jit`.
- Le portage R428 de ProsperoEden v1.001.000 a été intégré par **fast-forward** depuis sa branche de préparation, sans écraser les modifications existantes.
- Les 10 branches secondaires ont été supprimées après vérification exacte de leurs SHA. Exécution GitHub Actions : https://github.com/niakw/Prospero.Eden-Encore/actions/runs/38380839924 (succès).
- Le workflow temporaire ayant réalisé cette suppression est lui-même retiré du dépôt dans le commit de clôture.
- Vérification via l'API GitHub : **une seule branche distante demeure**, `dev/ps5-sparse-jit`.

Les anciens objets Git restent dans l'historique normal ; supprimer une branche ne supprime ni le code fusionné ni les commits inclus dans `dev`.

## Contrôles

- `[core-ready]` déclenche le préflight source ; `[full-build]` et les contrôles du pipeline natif n'ont pas à être déclenchés pour un simple changement de documentation.
- Les modifications des dépendances pinées passent par des dérivations CMake vérifiées et restent séparées des archives immuables.
- Les workflows CodeQL, CI, compilation et releases doivent cibler exclusivement `dev/ps5-sparse-jit`.
