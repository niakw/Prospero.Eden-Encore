# Eden Encore — journal silencieux sans formatage inutile

**21 octobre 2026 — HEAD initial e6588728e.**

Dans la branche native `__OPENORBIS__`, `Common::Log::Impl::ForEachBackend` ne référence ni fichier, ni Logcat, ni debugger : seule la sortie couleur est configurée. Son indicateur `enabled` est atomique et faux par défaut. Jusqu'alors, `FmtLogMessageImpl` formatte les messages acceptés par le filtre même lorsque cette sortie est désactivée.

Correctif `vendor/encore-active/eden-core/src/common/logging.cpp` : sortie anticipée sur le seul backend natif désactivé, AVANT `fmt::vformat_to_n`. Les écritures n'ont jamais lieu dans ce cas. Quand le backend est activé, le comportement de formatage, filtre et diffusion est inchangé. Les autres plateformes restent inchangées.

Contrôle `tools/check-ps5-quiet-log-filter-host.py` : extraction exacte de la garde maintenue, compilation C++20 sous ASan/UBSan et séquence off/on/off pour vérifier l'absence de formatage quand la console native est silencieuse. Ajouté au préflight du dépôt.

**Bilan : 407/491 maintenus pris en charge ; 22 moteur/runtime restant à examiner ; 62 fichiers de l'interface séparés ; 84 globalement.** Une source modifiée, aucun gain FPS ou correctif de freeze démontré sur PS5.
