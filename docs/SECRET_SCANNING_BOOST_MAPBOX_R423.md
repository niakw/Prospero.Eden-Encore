# R423 — GitHub Secret Scanning #1: Boost / Plotly Mapbox public demo token

**Verdict:** A third-party **public** Mapbox `pk.` token appears in six copied Boost 1.90.0 **math documentation HTML** files, as part of Plotly graph export options. It is the same Plotly-publisher token in all ten HTML occurrences (five in the generated overview and five individual graph fragments). The embedded token's public payload identifies the upstream user `chriddyp`; this is not an Eden Encore Mapbox credential.

Mapbox's official documentation distinguishes public `pk.` tokens (designed for browsers and read-only public scopes) from secret `sk.` tokens (for server-side private scopes). A public token can nonetheless incur billable map requests: ownership, current validity, restrictions and misuse are **not verified**. We must not claim it is revoked, and cannot rotate a third party's key.

## Repository decision

1. **Keep upstream `vendor/sources/eden-cpm/boost/boost-1.90.0` pristine**. These source trees mirror pinned archives, and rewriting six HTML outputs would invalidate reproducibility against our immutable `vendor/objects` source packs.
2. **Do not use the user-created `MAPBOX_TOKEN` secret for Boost**. The emulator, renderer, first-party Python utilities, source preflight and PS5 packaging have no Mapbox integration requiring this secret. Injecting it into vendor documentation or CI would expose a separate credential.
3. The core preflight `tools/check-pinned-boost-mapbox-demo.py` verifies that every one of the ten occurrences is public, located in the six approved third-party HTML files, and contains the same upstream Plotly identity. The test never prints the token or makes network requests. It also ensures workflows don't reference `MAPBOX_TOKEN`.
4. The GitHub alert **cannot be closed by a source-only commit**; the matching string is in upstream docs and Git history. An authorized maintainer should close Secret scanning alert #1 as **Won't fix** with a comment: *“Intentional upstream Plotly public pk. token in pinned Boost 1.90.0 generated math documentation; third-party-owned, not Eden Encore credential; no private scopes; upstream source checksum preservation required; CI explicitly forbids use of repo MAPBOX_TOKEN.”*
5. Only mark **Revoked** if the actual credential owner confirms revocation. An alert about a real intentionally public token should not be mislabeled as a confirmed revoked secret or a known invalid fake.

Security reference: https://docs.mapbox.com/help/dive-deeper/access-tokens/ and https://docs.github.com/en/code-security/how-tos/manage-security-alerts/manage-secret-scanning-alerts/resolving-alerts

No changes to CPU/GPU code, shader cache, PS5 packaging, vendored binaries or graphics timing. This classification is distinct from the R419 CodeQL **source scanning** triage.
