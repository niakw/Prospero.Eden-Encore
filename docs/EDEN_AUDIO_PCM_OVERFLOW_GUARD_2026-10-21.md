# Eden Encore — validation PCM sans dépassement arithmétique

**21 octobre 2026.**

Dans la source native `vendor/encore-active/eden-core/src/audio_core/renderer/voice/voice_info.cpp`, les tailles PCM16 et PCMFloat étaient contrôlées avec `offset * bytes_per_sample > buffer_size` avant le test explicite des offsets négatifs. Selon les promotions de types, cette opération pouvait introduire un dépassement ou une conversion signée non souhaitée avant que l'adresse invalide soit rejetée.

`PcmOffsetsWithinBuffer` valide `sample_bytes != 0`, les deux offsets signés non négatifs, puis `static_cast<u64>(offset) <= size / sample_bytes`. Cette comparaison rejette les offsets trop grands sans multiplication ni conversion précoce d'un entier négatif. Les chemins ADPCM, le gestionnaire de pools, et les mises à jour DSP restent inchangés.

Le test `tools/check-native-audio-pcm-offsets-host.py` extrait cette véritable fonction constexpr, la compile avec Clang C++20 ASan/UBSan et exerce offsets valides/invalides, échantillonnages 2 et 4 octets, `INT32_MIN`, `INT32_MAX`, stride nul et buffers de grande taille.

**Compteur : 415/491 sources prises en charge ; 14 fichiers moteur/runtime restant à examiner ; 62 fichiers interface séparés ; 76 globalement.** Aucun résultat de fluidité, audio console ou freeze n'est encore validé.
